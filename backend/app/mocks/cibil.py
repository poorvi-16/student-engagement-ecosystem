"""Mock credit bureau (CIBIL-style). Deterministic per PAN so a tester sees the same score every time.

Not a real bureau: the score is derived from a hash of the PAN, nudged by income and existing EMIs.
Most students have no credit history ("NH"), which lenders handle by relying on the co-applicant.
"""

import hashlib
from datetime import datetime, timezone


def _band(score: int) -> str:
    if score >= 750:
        return "Excellent"
    if score >= 700:
        return "Good"
    if score >= 650:
        return "Fair"
    return "Poor"


def pull(pan: str, *, monthly_income: float = 0.0, existing_emi: float = 0.0, is_student: bool = False) -> dict:
    """Returns {score|None, band, factors, report_id, pulled_at}. score None = no credit history."""
    pan = (pan or "").strip().upper()
    h = int(hashlib.sha256(pan.encode()).hexdigest(), 16)
    report_id = f"MCB{h % 10**8:08d}"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if is_student and h % 10 < 7:  # ~70% of students have no credit file yet
        return {"score": None, "band": "No history (NH)", "report_id": report_id, "pulled_at": now,
                "factors": ["No credit cards or loans yet, which is normal for students; the co-applicant's score is used."]}
    score = 640 + h % 181  # 640..820
    factors = []
    if monthly_income and existing_emi / monthly_income > 0.4:
        score -= 40
        factors.append("High existing EMIs relative to income")
    if h % 7 == 0:
        score -= 30
        factors.append("A late payment in the last 24 months")
    if h % 5 == 0:
        factors.append("Long, clean repayment history")
    if not factors:
        factors.append("Regular repayments, low credit utilisation")
    score = max(300, min(900, score))
    return {"score": score, "band": _band(score), "factors": factors, "report_id": report_id, "pulled_at": now}
