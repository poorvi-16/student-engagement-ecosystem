"""Mock NBFC Loan Origination System. Receives a submitted application and moves it through stages.

The decision is computed once at submission (rules/loan with verified income + mock bureau score) and
revealed stage by stage as time passes, so testers can watch the tracker move. Nothing here is a
real credit decision: the last step is always a human credit review, and the sanction is provisional.
"""

import hashlib
from datetime import datetime, timedelta, timezone

# (key, label, minutes after submission when it completes)
STAGES = [
    ("submitted", "Application received", 0),
    ("documents", "Documents verified", 1),
    ("bureau", "Credit bureau check", 2),
    ("underwriting", "Underwriting (policy rules)", 4),
    ("credit_review", "Human credit review", 7),
    ("sanction", "Decision", 10),
]


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def submit(*, product: dict, amount_lakhs: float, offer: dict, verified_offer: dict, co_score: int | None,
           student_score: int | None, now: datetime | None = None) -> dict:
    """offer = rules evaluation with declared data; verified_offer = with income read from documents."""
    now = now or datetime.now(timezone.utc)
    ref = f"{product['id'][:3].upper()}-{now:%y%m}-{int(hashlib.sha1(f'{now.timestamp()}{amount_lakhs}'.encode()).hexdigest(), 16) % 100000:05d}"
    notes: dict[str, str] = {
        "submitted": f"Reference {ref} created with {product['lender']}.",
        "documents": "KYC, academic and income documents matched the application.",
    }
    score = co_score
    notes["bureau"] = (f"Co-applicant score {score}." if score else "Co-applicant has no credit history.") + (
        f" Student score {student_score}." if student_score else " Student has no credit history (normal).")

    decision, sanctioned, conditions = "sanctioned", amount_lakhs, list(verified_offer.get("conditions", []))
    reasons: list[str] = []
    if score is not None and score < 650:
        decision, sanctioned = "declined", 0.0
        reasons.append("Co-applicant credit score is below the lender's 650 minimum.")
    elif not verified_offer.get("eligible"):
        cap = verified_offer.get("max_amount_lakhs", 0.0)
        if cap >= product["min_amount_lakhs"] and not any("FOIR" in r or "Needs" in r or "Only" in r for r in verified_offer["reasons"]):
            decision, sanctioned = "revised", round(cap, 1)
            reasons.append(f"Verified documents support up to ₹{cap}L.")
        else:
            decision, sanctioned = "declined", 0.0
            reasons.extend(verified_offer.get("reasons", [])[:2])
    elif verified_offer["amount_lakhs"] < amount_lakhs:
        decision, sanctioned = "revised", verified_offer["amount_lakhs"]
        reasons.append(f"Verified income supports ₹{verified_offer['amount_lakhs']}L of the ₹{amount_lakhs}L requested.")
    if score is not None and 650 <= score < 700 and decision != "declined":
        conditions.append("Additional co-applicant or collateral may be requested (fair credit score)")

    notes["underwriting"] = {"sanctioned": "Meets policy: income, FOIR, tier and bureau checks passed.",
                             "revised": "Meets policy at a revised amount. " + " ".join(reasons),
                             "declined": "Does not meet policy. " + " ".join(reasons)}[decision]
    notes["credit_review"] = "A credit officer reviews the file before any sanction (simulated)."
    rate = verified_offer.get("rate_pct") or offer.get("rate_pct")
    notes["sanction"] = {
        "sanctioned": f"Provisional sanction of ₹{sanctioned}L at {rate}% (simulated).",
        "revised": f"Provisional sanction of ₹{sanctioned}L at {rate}% (revised, simulated).",
        "declined": "Not sanctioned. See the reasons and tips to improve your application.",
    }[decision]
    return {
        "reference": ref, "lender": product["lender"], "product": product["name"], "submitted_at": _iso(now),
        "timeline": [{"key": k, "label": label, "due_at": _iso(now + timedelta(minutes=m)), "note": notes[k]}
                     for k, label, m in STAGES],
        "decision": {"outcome": decision, "amount_lakhs": sanctioned, "rate_pct": rate if sanctioned else None,
                     "tenure_years": verified_offer.get("tenure_years"), "moratorium_months": verified_offer.get("moratorium_months"),
                     "emi_lakhs": verified_offer.get("emi_lakhs") if decision == "sanctioned" else None,
                     "processing_fee_pct": product["processing_fee_pct"], "reasons": reasons, "conditions": conditions},
    }


def status(los: dict, now: datetime | None = None) -> dict:
    """Timeline with done/current flags; the decision is hidden until its stage completes."""
    now = now or datetime.now(timezone.utc)
    steps, current = [], None
    for st in los.get("timeline", []):
        done = datetime.fromisoformat(st["due_at"]) <= now
        steps.append({**st, "done": done, "note": st["note"] if done else ""})
        if not done and current is None:
            current = st["key"]
    finished = current is None
    return {"reference": los.get("reference"), "lender": los.get("lender"), "product": los.get("product"),
            "submitted_at": los.get("submitted_at"), "stage": current or "sanction", "finished": finished,
            "timeline": steps, "decision": los.get("decision") if finished else None}
