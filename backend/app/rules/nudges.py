"""Smart nudges: rule-picked next actions from the student's state. Each has a stable key for de-duplication.

Priority 0-100 decides order; >= PUSH_PRIORITY may also go out on the (mock) WhatsApp/email channel.
The loan triggers (funding gap → offers → copilot → finish application) are the conversion path.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date

PUSH_PRIORITY = 80


@dataclass
class State:
    today: date
    stage: str
    counts: dict[str, int]
    shortlisted: int
    has_timeline: bool
    overdue: list[tuple[str, date]] = field(default_factory=list)  # (title, due)
    due_soon: list[tuple[str, date]] = field(default_factory=list)
    funding_gap_lakhs: float = 0.0
    loan_draft_id: int | None = None
    loan_draft_missing: int = 0
    loan_submitted_id: int | None = None
    loan_outcome: str | None = None  # set once the decision is visible
    strength_tip: str | None = None
    days_inactive: int = 0
    streak_days: int = 0


@dataclass
class Nudge:
    key: str
    title: str
    body: str
    cta_label: str
    cta_href: str
    priority: int


def _c(s: State, t: str) -> int:
    return s.counts.get(t, 0)


def candidates(s: State) -> list[Nudge]:
    out: list[Nudge] = []

    def add(*args):
        out.append(Nudge(*args))

    # Loan funnel (highest value)
    if s.loan_submitted_id and s.loan_outcome:
        add(f"loan_decision:{s.loan_submitted_id}", "Your loan decision is ready",
            "The simulated lender has finished reviewing your application. See the outcome and next steps.",
            "View decision", f"/loan/apply?id={s.loan_submitted_id}", 95)
        if s.loan_outcome in ("sanctioned", "revised") and not _c(s, "visa_mock_done"):
            add("after_sanction_visa", "Funding sorted? Prepare for your visa",
                "Officers ask how you'll pay. Practise explaining your loan and costs in a mock interview.",
                "Practise now", "/visa", 70)
    if s.loan_draft_id and not s.loan_submitted_id:
        add(f"loan_finish:{s.loan_draft_id}", "Finish your loan application",
            f"{s.loan_draft_missing} item(s) left. Upload your documents and the copilot fills the form for you."
            if s.loan_draft_missing else "Everything's in. Review and submit to get a decision in minutes.",
            "Continue", f"/loan/apply?id={s.loan_draft_id}", 88)
    if s.funding_gap_lakhs > 0 and not _c(s, "loan_estimate"):
        add("loan_gap", f"Your funding gap is about ₹{s.funding_gap_lakhs:g}L",
            "See which lenders could cover it, with EMI and moratorium. It's a soft check, so there's no impact on credit scores.",
            "See loan offers", "/loan", 82)
    elif _c(s, "loan_estimate") and not s.loan_draft_id and not s.loan_submitted_id:
        add("loan_copilot", "Pre-fill your loan application in 5 minutes",
            "Upload your PAN and income proof; our copilot reads them and fills the form.", "Start application", "/loan", 75)

    # Timeline
    if s.overdue:
        title, _ = s.overdue[0]
        add("tasks_overdue", f"{len(s.overdue)} task(s) overdue", f"Start with: {title}.", "Open timeline", "/timeline", 90)
    elif s.due_soon:
        title, due = s.due_soon[0]
        add(f"due_soon:{title[:40]}", "Due this week", f"{title}, by {due:%d %b}.", "Open timeline", "/timeline", 85)
    if not s.has_timeline and (s.shortlisted or _c(s, "navigator_run")):
        add("make_timeline", "Turn your shortlist into a plan", "Get a month-by-month plan for tests, SOPs, deadlines, loan and visa.",
            "Build my plan", "/timeline", 65)

    # Discovery and preparation
    if not _c(s, "navigator_run"):
        add("navigator", "See universities that fit you", "AI-matched programs in Ambitious, Target and Safe buckets, with costs and payback.",
            "Open Navigator", "/navigator", 70)
    elif not s.shortlisted:
        add("shortlist", "Save the programs you like", "Shortlisting unlocks your personalised timeline and loan estimates.",
            "Open Navigator", "/navigator", 55)
    if not _c(s, "sop_reviewed") and (s.has_timeline or s.stage in ("applicant", "admitted")):
        add("sop_review", "Get instant SOP feedback", "A rubric score, the fixes that matter and a stronger opening.", "Review my SOP", "/sop", 60)
    if not _c(s, "visa_mock_done") and s.stage in ("admitted", "funding"):
        add("visa_practice", "Practise your visa interview", "An AI officer asks real questions and coaches each answer.", "Start", "/visa", 72)
    if s.strength_tip:
        add(f"tip:{hashlib.md5(s.strength_tip.encode()).hexdigest()[:8]}", "Boost your profile strength", s.strength_tip, "Edit profile", "/onboarding", 45)
    if not _c(s, "mentor_message"):
        add("mentor", "Ask the AI Mentor anything", "Visas, tests, scholarships and loans, with answers cited from our guides.",
            "Ask a question", "/mentor", 40)
    return sorted(out, key=lambda n: -n.priority)


def push_message(n: Nudge, name: str | None, site: str) -> str:
    """Text for the mock WhatsApp/email channel."""
    hi = f"Hi {name.split()[0]}! " if name else "Hi! "
    return f"{hi}{n.title}. {n.body} {n.cta_label}: {site.rstrip('/')}{n.cta_href}"
