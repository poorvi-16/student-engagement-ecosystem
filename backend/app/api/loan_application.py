"""Loan copilot application: draft → documents (vision auto-fill) → consent → submit → mock LOS tracker."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app import storage
from app.auth import current_user
from app.db.models import LoanApplication, LoanDocument, StudentProfile, User, utcnow
from app.db.session import get_session
from app.events import log_event
from app.rules.loan_docs import DOC_TYPES
from app.services import loan_application as svc
from app.services.loan import default_course
from app.services.programs import get_program

router = APIRouter(prefix="/loan/applications", tags=["loan-application"])

START_XP = 20
DOC_XP = 10
SUBMIT_XP = 100
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


class StartIn(BaseModel):
    product_id: str
    course_id: int | None = None
    amount_lakhs: float | None = None


class UpdateIn(BaseModel):
    applicant: dict | None = None
    co_applicant: dict | None = None
    academics: dict | None = None
    collateral: dict | None = None
    amount_lakhs: float | None = None


class SubmitIn(BaseModel):
    consent_kyc: bool
    consent_bureau: bool
    consent_dpdp: bool


def _profile(session: Session, user: User) -> StudentProfile:
    p = session.get(StudentProfile, user.id)
    if p is None:
        raise HTTPException(400, "Complete the onboarding quiz first.")
    return p


def _app(session: Session, user: User, app_id: int) -> LoanApplication:
    app = session.get(LoanApplication, app_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(404, "Application not found")
    return app


def _draft(app: LoanApplication) -> None:
    if app.status != "draft":
        raise HTTPException(409, "This application has been submitted and can't be edited.")


@router.get("")
def list_applications(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    rows = session.exec(select(LoanApplication).where(LoanApplication.user_id == user.id, LoanApplication.status != "withdrawn")
                        .order_by(col(LoanApplication.id).desc())).all()
    out = []
    for a in rows:
        prod = svc.product(a.product_id) or {}
        tracker = svc.nbfc_los.status(a.los) if a.status == "submitted" else None
        out.append({"id": a.id, "status": a.status, "lender": prod.get("lender"), "product": prod.get("name"),
                    "amount_lakhs": a.amount_lakhs, "course_id": a.course_id, "updated_at": a.updated_at,
                    "stage": tracker["stage"] if tracker else None, "finished": tracker["finished"] if tracker else None,
                    "outcome": (tracker["decision"] or {}).get("outcome") if tracker else None})
    return {"applications": out}


@router.post("")
def start(body: StartIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    if svc.product(body.product_id) is None:
        raise HTTPException(404, "Unknown loan product")
    course_id = body.course_id or default_course(session, user, p)
    if not course_id or get_program(course_id) is None:
        raise HTTPException(404, "Choose a program first")
    app = svc.create_or_resume(session, user, p, body.product_id, course_id, body.amount_lakhs)
    log_event(session, user, "loan_application_started", {"application_id": app.id, "product_id": body.product_id},
              xp=START_XP, once=True)
    session.commit()
    return svc.view(session, p, app)


@router.get("/{app_id}")
def get_application(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    return svc.view(session, p, _app(session, user, app_id))


@router.patch("/{app_id}")
def update(app_id: int, body: UpdateIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    app = _app(session, user, app_id)
    _draft(app)
    svc.update(app, body.model_dump(exclude_none=True))
    session.add(app)
    session.commit()
    session.refresh(app)
    return svc.view(session, p, app)


@router.post("/{app_id}/documents")
async def upload(app_id: int, doc_type: str = Form(...), file: UploadFile = File(...),
                 user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    app = _app(session, user, app_id)
    _draft(app)
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, "Unknown document type")
    mime = (file.content_type or "").lower()
    if mime not in ALLOWED_MIME:
        raise HTTPException(415, "Upload a JPG, PNG, WebP or PDF.")
    data = await file.read(storage.MAX_BYTES + 1)
    if len(data) > storage.MAX_BYTES:
        raise HTTPException(413, "Files must be 5 MB or smaller.")
    doc, filled, notice = svc.add_document(session, user, app, doc_type, file.filename or doc_type, data, mime)
    # XP once per document type (event type includes it so `once` applies per type)
    log_event(session, user, f"doc_uploaded:{doc_type}", {"application_id": app.id, "auto_filled": len(filled)},
              xp=DOC_XP, once=True)
    session.commit()
    session.refresh(app)
    return {"filled": filled, "notice": notice, "application": svc.view(session, p, app)}


@router.delete("/{app_id}/documents/{doc_id}")
def delete_document(app_id: int, doc_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    app = _app(session, user, app_id)
    _draft(app)
    doc = session.get(LoanDocument, doc_id)
    if doc is None or doc.application_id != app.id:
        raise HTTPException(404, "Document not found")
    if doc.storage_path:
        storage.delete([doc.storage_path])
    session.delete(doc)
    session.commit()
    return svc.view(session, p, app)


@router.get("/{app_id}/documents/{doc_id}/url")
def document_url(app_id: int, doc_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    app = _app(session, user, app_id)
    doc = session.get(LoanDocument, doc_id)
    if doc is None or doc.application_id != app.id or not doc.storage_path:
        raise HTTPException(404, "File not available (not stored, or deleted after 30 days)")
    url = storage.signed_url(doc.storage_path)
    if not url:
        raise HTTPException(503, "Storage unavailable")
    return {"url": url, "expires_in": 300}


@router.post("/{app_id}/submit")
def submit(app_id: int, body: SubmitIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    app = _app(session, user, app_id)
    _draft(app)
    if not (body.consent_kyc and body.consent_bureau and body.consent_dpdp):
        raise HTTPException(422, "All three consents are needed to submit.")
    current = svc.view(session, p, app)
    if current["missing"]:
        raise HTTPException(422, "Complete these first: " + "; ".join(current["missing"][:6]))
    if any(c["level"] == "error" for c in current["checks"]):
        raise HTTPException(422, "Fix the errors in the copilot check first.")
    app.consent = {"kyc": True, "bureau": True, "dpdp": True, "at": utcnow().isoformat(timespec="seconds")}
    svc.submit(session, p, app)
    log_event(session, user, "loan_application_submitted",
              {"application_id": app.id, "product_id": app.product_id, "amount_lakhs": app.amount_lakhs,
               "decision": app.los["decision"]["outcome"]}, xp=SUBMIT_XP, once=True)
    if p.journey_stage != "funding":
        p.journey_stage = "funding"
        session.add(p)
    session.commit()
    session.refresh(app)
    return svc.view(session, p, app)


@router.post("/{app_id}/withdraw")
def withdraw(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    app = _app(session, user, app_id)
    app.status, app.updated_at = "withdrawn", utcnow()
    session.add(app)
    log_event(session, user, "loan_application_withdrawn", {"application_id": app.id})
    session.commit()
    return {"ok": True}
