"""Reads loan documents with a vision model (Gemini) and returns normalised fields.

PDFs are rendered to an image (first page) with pypdfium2. The model is told to return only the Aadhaar's
last 4 digits; `rules.loan_docs.clean_extracted` enforces that anyway. If the LLM is unavailable the
upload still succeeds and the student types the fields in.
"""

import io
import logging

from pydantic import BaseModel, Field
from sqlmodel import Session

from app import llm
from app.db.models import User
from app.rules.loan_docs import DOC_TYPES, clean_extracted

log = logging.getLogger(__name__)
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class DocFields(BaseModel):
    readable: bool = Field(description="False if the image is blurry, cut off or not this kind of document")
    detected_type: str = Field(description="What the document actually is, e.g. 'PAN card', 'salary slip'")
    name: str | None = Field(None, description="Person's full name as printed")
    father_name: str | None = None
    dob: str | None = Field(None, description="Date of birth as YYYY-MM-DD")
    pan_number: str | None = Field(None, description="10-character PAN")
    aadhaar_last4: str | None = Field(None, description="ONLY the last 4 digits of the Aadhaar number, never the full number")
    address: str | None = None
    pincode: str | None = None
    expiry_date: str | None = Field(None, description="Passport expiry as YYYY-MM-DD")
    university: str | None = None
    program: str | None = None
    start_date: str | None = Field(None, description="Course start as YYYY-MM-DD")
    employer: str | None = None
    month: str | None = Field(None, description="Salary month, e.g. 2026-09")
    gross_monthly_inr: float | None = None
    net_monthly_inr: float | None = None
    assessment_year: str | None = None
    annual_income_inr: float | None = Field(None, description="Gross total income from the ITR")
    bank_name: str | None = None
    average_balance_inr: float | None = None
    owner_name: str | None = None
    property_address: str | None = None


SYSTEM = """You read Indian KYC, income and admission documents for an education-loan application.
Extract only what is clearly printed on the document. Use null for anything missing or unreadable. Never guess.
For Aadhaar, return ONLY the last 4 digits in aadhaar_last4. Never output the full Aadhaar number or a full passport number.
Amounts in rupees as plain numbers."""


def to_image(data: bytes, mime: str) -> tuple[str, bytes]:
    if mime in IMAGE_TYPES:
        return mime, data
    if mime == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            page = pdf[0]
            pil = page.render(scale=2).to_pil()
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, format="JPEG", quality=85)
            return "image/jpeg", buf.getvalue()
        finally:
            pdf.close()
    raise ValueError("Unsupported file type")


def extract(session: Session, user: User, doc_type: str, data: bytes, mime: str) -> tuple[dict, str | None]:
    """Returns (cleaned fields, notice). Empty fields + notice when the AI can't read it."""
    try:
        image = to_image(data, mime)
    except Exception as e:  # noqa: BLE001 - corrupt PDFs etc.
        log.warning("Could not render %s: %s", mime, e)
        return {}, "Couldn't open this file. Try a clear JPG or PNG photo."
    prompt = f"Document type expected: {DOC_TYPES.get(doc_type, doc_type)}. Extract the fields."
    try:
        out = llm.parse(session, user, feature="doc_extract", system=SYSTEM, prompt=prompt, output=DocFields,
                        tier="fast", max_tokens=1500, images=[image])
    except llm.LLMUnavailable as e:
        return {}, f"{e.user_message} Please type the details in yourself."
    fields = clean_extracted(doc_type, out.model_dump(exclude={"readable", "detected_type"}))
    notice = None if out.readable else f"This looks like a {out.detected_type} or is hard to read. Check the details."
    fields["_detected_type"] = out.detected_type
    return fields, notice
