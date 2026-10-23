"""Loan copilot: one application per student, pre-filled from the profile, auto-filled from documents,
cross-checked before submission, then sent to the mock bureau + mock NBFC LOS.
"""

import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app import storage
from app.catalog import Course, University, get_catalog
from app.db.models import LoanApplication, LoanDocument, StudentProfile, User, utcnow
from app.mocks import cibil, nbfc_los
from app.rules import loan as loan_rules
from app.rules import loan_docs as rules
from app.services import documents
from app.services.loan import build_case
from app.services.programs import get_program

RETENTION_DAYS = 30


def product(product_id: str) -> dict | None:
    return next((p for p in get_catalog().loan_products["products"] if p["id"] == product_id), None)


def _program(app: LoanApplication) -> tuple[Course, University]:
    prog = get_program(app.course_id)
    assert prog is not None
    return prog


def _flags(app: LoanApplication) -> dict:
    c, u = _program(app)
    prod = product(app.product_id) or {}
    return {"secured": prod.get("type") == "secured", "abroad": u.country != "India",
            "admitted": app.academics.get("admit_status") == "admitted"}


def active(session: Session, user: User) -> LoanApplication | None:
    return session.exec(select(LoanApplication).where(LoanApplication.user_id == user.id, LoanApplication.status != "withdrawn")
                        .order_by(col(LoanApplication.id).desc())).first()


def create_or_resume(session: Session, user: User, p: StudentProfile, product_id: str, course_id: int,
                     amount_lakhs: float | None) -> LoanApplication:
    """Resumes the student's draft (switching product/course if asked) or starts a new pre-filled one."""
    c, u = get_program(course_id) or (None, None)
    case, _ = build_case(p, c, u, amount_lakhs=amount_lakhs)
    app = active(session, user)
    if app and app.status == "draft":
        app.product_id, app.course_id, app.amount_lakhs = product_id, course_id, case.amount_lakhs
        app.academics = {**app.academics, "university": u.name, "program": c.program, "country": u.country}
    elif app is None or app.status != "draft":
        app = LoanApplication(
            user_id=user.id, product_id=product_id, course_id=course_id, amount_lakhs=case.amount_lakhs,
            applicant={"full_name": user.full_name or "", "email": user.email},
            co_applicant={"monthly_income": round((p.co_applicant_income_lpa or 0) * 1e5 / 12) or None},
            academics={"university": u.name, "program": c.program, "country": u.country, "intake": p.target_intake,
                       "cgpa": p.cgpa, "gre": p.gre, "gmat": p.gmat, "ielts": p.ielts, "toefl": p.toefl,
                       "admit_status": "admitted" if p.journey_stage in ("admitted", "funding") else "applied"},
            collateral={"value_lakhs": p.collateral_value_lakhs, "type": "Residential property"} if p.has_collateral else {},
        )
    app.updated_at = utcnow()
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def docs(session: Session, app: LoanApplication) -> list[LoanDocument]:
    return list(session.exec(select(LoanDocument).where(LoanDocument.application_id == app.id).order_by(col(LoanDocument.id))).all())


def _extracted_by_type(doc_rows: list[LoanDocument]) -> dict[str, dict]:
    return {d.doc_type: d.extracted for d in doc_rows}  # latest upload of each type wins (ordered by id)


def _course_end(app: LoanApplication) -> date:
    c, _ = _program(app)
    start = app.academics.get("start_date")
    try:
        d = date.fromisoformat(str(start)) if start else date.today() + timedelta(days=300)
    except ValueError:
        d = date.today() + timedelta(days=300)
    return d + timedelta(days=round(c.duration_months * 30.4))


def offer_for(p: StudentProfile, app: LoanApplication, monthly_income: float | None = None) -> loan_rules.Offer:
    c, u = _program(app)
    co = app.co_applicant
    income = monthly_income if monthly_income is not None else float(co.get("monthly_income") or 0)
    try:
        emi_existing = float(co.get("existing_emi") or 0)
    except (TypeError, ValueError):
        emi_existing = 0.0
    try:
        collateral = float(app.collateral.get("value_lakhs") or 0)
    except (TypeError, ValueError):
        collateral = 0.0
    case, _ = build_case(p, c, u, amount_lakhs=app.amount_lakhs, co_applicant_income_lpa=income * 12 / 1e5,
                         co_applicant_emi_monthly=emi_existing, collateral_value_lakhs=collateral,
                         admitted=app.academics.get("admit_status") == "admitted")
    return loan_rules.evaluate(case, product(app.product_id))


def view(session: Session, p: StudentProfile, app: LoanApplication) -> dict:
    rows = docs(session, app)
    flags = _flags(app)
    c, u = _program(app)
    by_type = _extracted_by_type(rows)
    out = {
        "id": app.id, "status": app.status, "product": product(app.product_id), "course_id": app.course_id,
        "program": {"university": u.name, "program": c.program, "country": u.country},
        "amount_lakhs": app.amount_lakhs, "applicant": app.applicant, "co_applicant": app.co_applicant,
        "academics": app.academics, "collateral": app.collateral, "consent": app.consent,
        "checklist": [{**item, "uploaded": item["doc_type"] in by_type}
                      for item in rules.checklist(**flags)],
        "documents": [{"id": d.id, "doc_type": d.doc_type, "filename": d.filename, "status": d.status,
                       "stored": d.storage_path is not None, "extracted": {k: v for k, v in d.extracted.items() if not k.startswith("_")},
                       "expires_at": d.expires_at, "created_at": d.created_at} for d in rows],
        "missing": rules.missing(asdict_sections(app), list(by_type), **flags),
        "checks": rules.cross_checks(asdict_sections(app), by_type, university=u.name, course_end=_course_end(app),
                                     today=date.today()),
        "offer": asdict(offer_for(p, app)),
        "secured": flags["secured"],
        "storage": storage.configured(),
    }
    if app.status == "submitted":
        out["tracker"] = nbfc_los.status(app.los)
        out["cibil"] = app.cibil
    return out


def asdict_sections(app: LoanApplication) -> dict:
    return {"applicant": dict(app.applicant), "co_applicant": dict(app.co_applicant), "academics": dict(app.academics),
            "collateral": dict(app.collateral)}


def update(app: LoanApplication, changes: dict) -> None:
    for section in ("applicant", "co_applicant", "academics", "collateral"):
        if section in changes and changes[section] is not None:
            merged = {**getattr(app, section), **changes[section]}
            if "aadhaar_last4" in merged:
                merged["aadhaar_last4"] = rules.mask_aadhaar(merged["aadhaar_last4"])
            if "pan" in merged and merged["pan"]:
                merged["pan"] = str(merged["pan"]).replace(" ", "").upper()
            setattr(app, section, merged)  # reassign so the JSON column change is saved
    if changes.get("amount_lakhs"):
        app.amount_lakhs = float(changes["amount_lakhs"])
    app.updated_at = utcnow()


def add_document(session: Session, user: User, app: LoanApplication, doc_type: str, filename: str, data: bytes,
                 mime: str) -> tuple[LoanDocument, list[str], str | None]:
    fields, notice = documents.extract(session, user, doc_type, data, mime)
    path = None
    if doc_type not in rules.NOT_STORED:
        candidate = f"{user.id}/{app.id}/{doc_type}-{uuid.uuid4().hex[:8]}"
        if storage.upload(candidate, data, mime):
            path = candidate
    doc = LoanDocument(user_id=user.id, application_id=app.id, doc_type=doc_type, filename=filename[:120], mime=mime,
                       size=len(data), storage_path=path, extracted=fields,
                       status="extracted" if any(not k.startswith("_") for k in fields) else "manual",
                       expires_at=datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS) if path else None)
    sections = asdict_sections(app)
    filled = rules.autofill(sections, doc_type, fields)
    for k, v in sections.items():
        setattr(app, k, v)
    app.updated_at = utcnow()
    session.add(doc)
    session.add(app)
    return doc, filled, notice


def submit(session: Session, p: StudentProfile, app: LoanApplication) -> None:
    rows = docs(session, app)
    by_type = _extracted_by_type(rows)
    prod = product(app.product_id)
    declared = offer_for(p, app)
    verified = offer_for(p, app, rules.verified_monthly_income(asdict_sections(app), by_type))
    co, a = app.co_applicant, app.applicant
    co_income = rules.verified_monthly_income(asdict_sections(app), by_type)
    co_report = cibil.pull(co.get("pan", ""), monthly_income=co_income, existing_emi=float(co.get("existing_emi") or 0))
    st_report = cibil.pull(a.get("pan", ""), is_student=True)
    app.cibil = {"co_applicant": co_report, "student": st_report, "type": "hard enquiry (simulated, with consent)"}
    app.los = nbfc_los.submit(product=prod, amount_lakhs=app.amount_lakhs, offer=asdict(declared), verified_offer=asdict(verified),
                              co_score=co_report["score"], student_score=st_report["score"])
    app.status, app.submitted_at, app.updated_at = "submitted", utcnow(), utcnow()
    session.add(app)
