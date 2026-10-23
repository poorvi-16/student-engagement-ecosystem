import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app import llm, storage
from app.mocks import cibil, nbfc_los
from app.rules import loan_docs
from app.services import documents
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100

FAKE = {
    "pan": {"name": "ASHA RAO", "pan_number": "abcde1234f", "dob": "2004-05-06"},
    "aadhaar": {"aadhaar_last4": "1234 5678 9012", "address": "12 MG Road, Pune", "pincode": "411001"},
    "co_pan": {"name": "RAVI RAO", "pan_number": "PQRSX6789K"},
    "salary_slip": {"employer": "Tata Motors", "gross_monthly_inr": "₹1,50,000"},
}


@pytest.fixture
def fake_docs(monkeypatch):
    def fake_extract(session, user, doc_type, data, mime):
        return loan_docs.clean_extracted(doc_type, dict(FAKE.get(doc_type, {}))), None

    monkeypatch.setattr(documents, "extract", fake_extract)
    uploads = []
    monkeypatch.setattr(storage, "upload", lambda path, data, mime: uploads.append(path) or True)
    return uploads


def _setup(client):
    h = auth(make_token())
    client.put("/me/profile", json=QUIZ, headers=h)
    cid = client.get("/loan", headers=h).json()["default_course_id"]
    return h, cid


def _upload(client, h, app_id, doc_type, data=PNG, mime="image/png"):
    return client.post(f"/loan/applications/{app_id}/documents", data={"doc_type": doc_type},
                       files={"file": (f"{doc_type}.png", data, mime)}, headers=h)


def test_rules_masking_and_checklist():
    assert loan_docs.mask_aadhaar("1234 5678 9012") == "9012"
    cleaned = loan_docs.clean_extracted("aadhaar", {"aadhaar_number": "123456789012", "passport_number": "Z1234567"})
    assert cleaned == {"aadhaar_last4": "9012", "passport_last4": "4567"}
    types = {i["doc_type"]: i["required"] for i in loan_docs.checklist(secured=True, abroad=True, admitted=False)}
    assert types["pan"] and types["property_doc"] and not types["admit_letter"] and "passport" in types
    assert "property_doc" not in {i["doc_type"] for i in loan_docs.checklist(secured=False, abroad=False, admitted=True)}


def test_pdf_is_rendered_for_vision():
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), "white").save(buf, format="PDF")
    mime, img = documents.to_image(buf.getvalue(), "application/pdf")
    assert mime == "image/jpeg" and img[:2] == b"\xff\xd8"


def test_vision_extraction_skips_text_only_providers(engine, monkeypatch):
    from sqlmodel import Session
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "groq_api_key", "q")  # only Groq configured → no vision provider
    with Session(engine) as s:
        fields, notice = documents.extract(s, None, "pan", PNG, "image/png")
    assert fields == {} and "type the details" in notice

    seen = {}

    def fake_parse(session, user, **kw):
        seen.update(kw)
        return documents.DocFields(readable=True, detected_type="PAN card", name="ASHA RAO", pan_number="ABCDE 1234F")

    monkeypatch.setattr(llm, "parse", fake_parse)
    with Session(engine) as s:
        fields, notice = documents.extract(s, None, "pan", PNG, "image/png")
    assert fields["pan_number"] == "ABCDE1234F" and seen["images"][0][0] == "image/png" and notice is None


def test_full_application_flow(client, fake_docs):
    h, cid = _setup(client)
    app = client.post("/loan/applications", json={"product_id": "aarohan-unsecured-premier", "course_id": cid}, headers=h).json()
    aid = app["id"]
    assert app["status"] == "draft" and app["academics"]["university"] and app["co_applicant"]["monthly_income"] == 100000
    assert any(m.startswith("Upload") for m in app["missing"])

    r = _upload(client, h, aid, "pan").json()
    assert r["filled"] == ["applicant pan", "applicant dob"]  # name was pre-filled from the account, so kept
    assert r["application"]["applicant"]["pan"] == "ABCDE1234F"
    assert not any("Name on PAN" in c["message"] for c in r["application"]["checks"])  # "Asha Rao" matches "ASHA RAO"
    r = client.patch(f"/loan/applications/{aid}", json={"applicant": {"full_name": "Priya Sharma"}}, headers=h).json()
    assert any("Name on PAN" in c["message"] and c["level"] == "warn" for c in r["checks"])
    client.patch(f"/loan/applications/{aid}", json={"applicant": {"full_name": "Asha Rao"}}, headers=h)
    r = _upload(client, h, aid, "aadhaar").json()
    assert r["application"]["applicant"]["aadhaar_last4"] == "9012"
    assert not any("aadhaar" in p for p in fake_docs)  # Aadhaar images are never stored
    _upload(client, h, aid, "co_pan")
    r = _upload(client, h, aid, "salary_slip").json()
    assert r["application"]["co_applicant"]["employer"] == "Tata Motors"
    assert any("salary slip" in c["message"] for c in r["application"]["checks"])  # 1.5L vs declared 1L

    assert client.post(f"/loan/applications/{aid}/submit", json={"consent_kyc": True, "consent_bureau": True, "consent_dpdp": True},
                       headers=h).status_code == 422  # mobile, relation, occupation still missing
    client.patch(f"/loan/applications/{aid}", json={
        "applicant": {"mobile": "9876543210"}, "co_applicant": {"relation": "Father", "occupation": "Salaried"}}, headers=h)
    assert client.post(f"/loan/applications/{aid}/submit", json={"consent_kyc": True, "consent_bureau": False, "consent_dpdp": True},
                       headers=h).status_code == 422
    done = client.post(f"/loan/applications/{aid}/submit", json={"consent_kyc": True, "consent_bureau": True, "consent_dpdp": True},
                       headers=h).json()
    assert done["status"] == "submitted" and done["tracker"]["reference"] and done["cibil"]["co_applicant"]["report_id"]
    assert done["tracker"]["decision"] is None and done["tracker"]["timeline"][0]["done"]
    assert client.patch(f"/loan/applications/{aid}", json={"amount_lakhs": 5}, headers=h).status_code == 409

    me = client.get("/me", headers=h).json()
    assert me["profile"]["journey_stage"] == "funding"
    assert me["user"]["xp"] == 100 + 20 + 4 * 10 + 100  # quiz, start, 4 doc types, submit
    listing = client.get("/loan/applications", headers=h).json()["applications"]
    assert listing[0]["status"] == "submitted" and listing[0]["lender"].startswith("Aarohan")


def test_validation_privacy_and_withdraw(client, fake_docs):
    h, cid = _setup(client)
    aid = client.post("/loan/applications", json={"product_id": "globalscholar-unsecured", "course_id": cid}, headers=h).json()["id"]
    assert _upload(client, h, aid, "pan", b"hello", "text/plain").status_code == 415
    assert _upload(client, h, aid, "pan", b"0" * (storage.MAX_BYTES + 10)).status_code == 413
    assert _upload(client, h, aid, "selfie").status_code == 422
    r = client.patch(f"/loan/applications/{aid}", json={"applicant": {"pan": "BAD", "aadhaar_last4": "1111 2222 3333"}}, headers=h).json()
    assert r["applicant"]["aadhaar_last4"] == "3333" and any(c["level"] == "error" for c in r["checks"])
    other = auth(make_token(email="other@test.dev"))
    client.put("/me/profile", json=QUIZ, headers=other)
    assert client.get(f"/loan/applications/{aid}", headers=other).status_code == 404
    assert _upload(client, other, aid, "pan").status_code == 404
    # starting again resumes the same draft with the new product
    again = client.post("/loan/applications", json={"product_id": "vidya-secured", "course_id": cid}, headers=h).json()
    assert again["id"] == aid and again["secured"] is True
    assert any(i["doc_type"] == "property_doc" for i in again["checklist"])
    assert client.post(f"/loan/applications/{aid}/withdraw", headers=h).json()["ok"]
    assert client.get("/loan/applications", headers=h).json()["applications"] == []


def test_mock_bureau_and_los_decisions():
    assert cibil.pull("ABCDE1234F") == {**cibil.pull("ABCDE1234F"), "pulled_at": cibil.pull("ABCDE1234F")["pulled_at"]}
    s = cibil.pull("ABCDE1234F")["score"]
    assert 300 <= s <= 900
    product = {"id": "vidya-secured", "lender": "Vidya", "name": "Vidya Secured", "min_amount_lakhs": 10, "processing_fee_pct": 1}
    ok_offer = {"eligible": True, "amount_lakhs": 40, "max_amount_lakhs": 40, "rate_pct": 10, "reasons": [], "conditions": [],
                "tenure_years": 10, "moratorium_months": 30, "emi_lakhs": 0.6}
    t0 = datetime(2026, 10, 23, tzinfo=timezone.utc)
    los = nbfc_los.submit(product=product, amount_lakhs=40, offer=ok_offer, verified_offer=ok_offer, co_score=760,
                          student_score=None, now=t0)
    assert nbfc_los.status(los, t0 + timedelta(minutes=3))["stage"] == "underwriting"
    final = nbfc_los.status(los, t0 + timedelta(minutes=11))
    assert final["finished"] and final["decision"]["outcome"] == "sanctioned" and final["decision"]["amount_lakhs"] == 40
    low = nbfc_los.submit(product=product, amount_lakhs=40, offer=ok_offer, verified_offer=ok_offer, co_score=610, student_score=None, now=t0)
    assert low["decision"]["outcome"] == "declined"
    revised = nbfc_los.submit(product=product, amount_lakhs=40, offer=ok_offer, verified_offer={**ok_offer, "amount_lakhs": 25},
                              co_score=720, student_score=None, now=t0)
    assert revised["decision"]["outcome"] == "revised" and revised["decision"]["amount_lakhs"] == 25
