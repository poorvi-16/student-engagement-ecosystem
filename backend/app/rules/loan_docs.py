"""Loan application rules: document checklist, required fields, auto-fill mapping and pre-submission cross-checks.

Deterministic so the copilot's advice is predictable and testable; the LLM only reads documents.
Aadhaar is reduced to its last 4 digits everywhere (DPDP: collect the minimum).
"""

import re
from datetime import date

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

DOC_TYPES = {
    "pan": "Your PAN card",
    "aadhaar": "Your Aadhaar (masked)",
    "passport": "Your passport (photo page)",
    "admit_letter": "Admit / offer letter",
    "co_pan": "Co-applicant PAN card",
    "co_aadhaar": "Co-applicant Aadhaar (masked)",
    "salary_slip": "Co-applicant salary slip (latest)",
    "itr": "Co-applicant ITR (latest year)",
    "bank_statement": "Co-applicant bank statement (6 months)",
    "property_doc": "Property document (collateral)",
}
NOT_STORED = {"aadhaar", "co_aadhaar"}  # read and discarded: only the last 4 digits are kept

REQUIRED_FIELDS = {
    "applicant": {"full_name": "Full name (as on PAN)", "dob": "Date of birth", "pan": "PAN", "aadhaar_last4": "Aadhaar last 4 digits",
                  "mobile": "Mobile number", "address": "Address", "pincode": "PIN code"},
    "co_applicant": {"name": "Co-applicant name", "relation": "Relation", "pan": "Co-applicant PAN",
                     "occupation": "Occupation", "monthly_income": "Monthly income (₹)"},
    "collateral": {"type": "Collateral type", "value_lakhs": "Collateral value (₹ lakh)", "address": "Collateral address"},
}

# doc_type -> [(section, field, extracted key)]
AUTOFILL = {
    "pan": [("applicant", "full_name", "name"), ("applicant", "pan", "pan_number"), ("applicant", "dob", "dob")],
    "aadhaar": [("applicant", "aadhaar_last4", "aadhaar_last4"), ("applicant", "address", "address"),
                ("applicant", "pincode", "pincode"), ("applicant", "dob", "dob")],
    "passport": [("applicant", "passport_expiry", "expiry_date")],
    "co_pan": [("co_applicant", "name", "name"), ("co_applicant", "pan", "pan_number")],
    "co_aadhaar": [("co_applicant", "aadhaar_last4", "aadhaar_last4")],
    "salary_slip": [("co_applicant", "employer", "employer"), ("co_applicant", "monthly_income", "gross_monthly_inr")],
    "itr": [("co_applicant", "annual_income", "annual_income_inr")],
    "admit_letter": [("academics", "university_on_letter", "university"), ("academics", "program_on_letter", "program"),
                     ("academics", "start_date", "start_date")],
    "property_doc": [("collateral", "address", "property_address"), ("collateral", "owner_name", "owner_name")],
    "bank_statement": [("co_applicant", "bank_average_balance", "average_balance_inr")],
}


def checklist(*, secured: bool, abroad: bool, admitted: bool) -> list[dict]:
    items = [("pan", True, ""), ("aadhaar", True, "Only the last 4 digits are kept; the image is not stored."),
             ("co_pan", True, ""), ("co_aadhaar", False, ""),
             ("salary_slip", False, "Upload a salary slip or an ITR."), ("itr", False, "Upload a salary slip or an ITR."),
             ("bank_statement", False, "Speeds up verification.")]
    if abroad:
        items.insert(2, ("passport", False, "Needed before disbursal."))
    items.insert(3, ("admit_letter", admitted, "" if admitted else "Needed before sanction; add it when you get an admit."))
    if secured:
        items.append(("property_doc", True, "Sale deed or title document for the collateral."))
    return [{"doc_type": t, "label": DOC_TYPES[t], "required": req, "note": note} for t, req, note in items]


def mask_aadhaar(value) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else None


def clean_extracted(doc_type: str, fields: dict) -> dict:
    """Normalises model output; never lets a full Aadhaar or passport number through."""
    out = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    for k in ("aadhaar_number", "aadhaar"):
        if k in out:
            out.setdefault("aadhaar_last4", mask_aadhaar(out.pop(k)))
    if "aadhaar_last4" in out:
        out["aadhaar_last4"] = mask_aadhaar(out["aadhaar_last4"])
    if "passport_number" in out:
        pn = str(out.pop("passport_number"))
        out["passport_last4"] = pn[-4:]
    if "pan_number" in out:
        out["pan_number"] = re.sub(r"\s", "", str(out["pan_number"])).upper()
    for k in ("gross_monthly_inr", "net_monthly_inr", "annual_income_inr", "average_balance_inr"):
        if k in out:
            try:
                out[k] = round(float(re.sub(r"[^\d.]", "", str(out[k]))))
            except ValueError:
                out.pop(k)
    return {k: v for k, v in out.items() if v not in (None, "")}


def autofill(app_sections: dict[str, dict], doc_type: str, extracted: dict) -> list[str]:
    """Fills empty application fields from a document. Returns labels of what was filled."""
    filled = []
    for section, field, key in AUTOFILL.get(doc_type, []):
        value = extracted.get(key)
        if value in (None, "") or app_sections[section].get(field) not in (None, ""):
            continue
        app_sections[section][field] = value
        filled.append(f"{section.replace('_', '-')} {field.replace('_', ' ')}")
    if doc_type == "itr" and extracted.get("annual_income_inr") and not app_sections["co_applicant"].get("monthly_income"):
        app_sections["co_applicant"]["monthly_income"] = round(extracted["annual_income_inr"] / 12)
        filled.append("co-applicant monthly income")
    if doc_type == "admit_letter":
        app_sections["academics"]["admit_status"] = "admitted"
    return filled


def missing(app: dict, docs: list[str], *, secured: bool, abroad: bool, admitted: bool) -> list[str]:
    out = []
    for section, fields in REQUIRED_FIELDS.items():
        if section == "collateral" and not secured:
            continue
        for field, label in fields.items():
            if app.get(section, {}).get(field) in (None, ""):
                out.append(label)
    for item in checklist(secured=secured, abroad=abroad, admitted=admitted):
        if item["required"] and item["doc_type"] not in docs:
            out.append(f"Upload: {item['label']}")
    if not ({"salary_slip", "itr"} & set(docs)):
        out.append("Upload: co-applicant salary slip or ITR")
    return out


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{2,}", (s or "").lower()) if t not in {"of", "the", "and", "university", "institute"}}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def _parse_date(s) -> date | None:
    for pat in (r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"):
        m = re.search(pat, str(s or ""))
        if m:
            g = [int(x) for x in m.groups()]
            y, mo, d = (g[0], g[1], g[2]) if pat.startswith(r"(\d{4})") else (g[2], g[1], g[0])
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    return None


def cross_checks(app: dict, extracted_by_type: dict[str, dict], *, university: str, course_end: date, today: date) -> list[dict]:
    """Copilot pre-submission review: format checks and consistency between the form and the documents."""
    a, co = app.get("applicant", {}), app.get("co_applicant", {})
    out = []

    def add(level, msg):
        out.append({"level": level, "message": msg})

    for who, pan in (("Your", a.get("pan")), ("Co-applicant", co.get("pan"))):
        if pan and not PAN_RE.match(str(pan).upper()):
            add("error", f"{who} PAN '{pan}' doesn't look valid (format ABCDE1234F).")
    if a.get("pan") and co.get("pan") and str(a["pan"]).upper() == str(co["pan"]).upper():
        add("error", "Your PAN and the co-applicant's PAN are the same.")
    pan_doc = extracted_by_type.get("pan", {})
    if pan_doc.get("name") and a.get("full_name") and not _similar(pan_doc["name"], a["full_name"]):
        add("warn", f"Name on PAN ('{pan_doc['name']}') differs from the application ('{a['full_name']}').")
    admit = extracted_by_type.get("admit_letter", {})
    if admit.get("university") and not _similar(admit["university"], university):
        add("warn", f"Admit letter is from '{admit['university']}', not {university}.")
    slip = extracted_by_type.get("salary_slip", {})
    try:
        declared = float(co.get("monthly_income") or 0)
    except (TypeError, ValueError):
        declared = 0
    if slip.get("gross_monthly_inr") and declared and abs(slip["gross_monthly_inr"] - declared) / declared > 0.2:
        add("warn", f"Declared income ₹{declared:,.0f}/month differs from the salary slip (₹{slip['gross_monthly_inr']:,.0f}). "
                    "The lender will use the document.")
    dob = _parse_date(a.get("dob"))
    if dob and (today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))) < 18:
        add("warn", "Applicants under 18 need a guardian as the primary co-applicant.")
    expiry = _parse_date(a.get("passport_expiry"))
    if expiry and expiry < course_end:
        add("warn", f"Your passport expires ({expiry:%b %Y}) before the course ends; renew it before the visa.")
    if not out:
        add("ok", "Everything matches across your form and documents.")
    return out


def verified_monthly_income(app: dict, extracted_by_type: dict[str, dict]) -> float:
    slip = extracted_by_type.get("salary_slip", {}).get("gross_monthly_inr")
    if slip:
        return float(slip)
    itr = extracted_by_type.get("itr", {}).get("annual_income_inr")
    if itr:
        return float(itr) / 12
    try:
        return float(app.get("co_applicant", {}).get("monthly_income") or 0)
    except (TypeError, ValueError):
        return 0.0
