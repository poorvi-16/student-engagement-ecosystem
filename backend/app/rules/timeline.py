"""Deterministic application timeline: every dated task from intake, program deadlines and the profile.

The LLM (services/timeline.py) only personalises task details and may add a few extra tasks; it never
moves dates. Tasks have stable `key`s so regenerating keeps what the student already ticked off.
Fixed tasks (application deadlines, exam dates) keep their date even if it has passed; preparation
tasks that would be in the past are pulled forward to "this week".
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.catalog import Course, University
from app.db.models import StudentProfile

CATEGORIES = ("research", "tests", "documents", "sop", "lor", "applications", "scholarships", "finance", "visa", "travel")

# Typical programme start month by country for each intake season
START_MONTH = {
    "Fall": {"USA": 8, "Canada": 9, "UK": 9, "Germany": 10, "Ireland": 9, "Australia": 7, "Netherlands": 9, "India": 7},
    "Spring": {"USA": 1, "Canada": 1, "UK": 1, "Germany": 4, "Ireland": 1, "Australia": 2, "Netherlands": 2, "India": 1},
}

VISA_STEPS = {
    "USA": [(4.0, "Receive your I-20 and pay the SEVIS fee", "Your university issues the I-20 once you accept and show funds; the SEVIS I-901 fee comes before the visa interview."),
            (3.5, "Fill the DS-160 and book your F-1 interview", "Slots in India fill up fast in peak season; book as soon as you have the I-20."),
            (3.0, "Practise your visa interview", "Run PathPilot's mock visa interview until you can explain your course, funding and plans clearly."),
            (2.5, "Attend your F-1 visa interview", "Carry your I-20, DS-160 confirmation, SEVIS receipt, admit letter, test scores and loan sanction / bank proofs.")],
    "UK": [(3.0, "Receive your CAS from the university", "You need the CAS number before applying; it follows your unconditional offer and deposit."),
           (2.5, "Apply for the UK Student visa and pay the IHS", "Show maintenance funds held for 28 days, plus the Immigration Health Surcharge.")],
    "Canada": [(5.0, "Get your acceptance letter, PAL and GIC", "Open a GIC for proof of funds and get the provincial attestation letter (PAL) from your college."),
               (4.5, "Apply for your study permit and give biometrics", "Processing can take weeks; apply as soon as your documents are ready.")],
    "Germany": [(6.0, "Get your APS certificate", "Indian applicants need the APS certificate for the visa; it can take several weeks."),
                (4.0, "Open your blocked account", "Deposit the required yearly amount (about €11,904) into a blocked account."),
                (3.0, "Apply for the German national (student) visa", "Book the VFS / embassy appointment early; bring the blocked-account confirmation and admission letter.")],
    "Australia": [(3.5, "Receive your CoE and buy OSHC health cover", "The Confirmation of Enrolment follows your acceptance and tuition deposit."),
                  (3.0, "Apply for the Student visa (subclass 500)", "Show the GS requirement and living-cost funds (about AUD 29,710 per year).")],
    "Ireland": [(3.0, "Apply for the Irish study visa", "Show tuition paid and access to living funds; apply online, then submit documents at VFS.")],
    "Netherlands": [(3.0, "Complete the MVV / residence permit process", "Your university usually applies for you; you'll be asked to show sufficient funds.")],
}


@dataclass
class TaskSpec:
    key: str
    title: str
    detail: str
    category: str
    due: date
    fixed: bool = False  # real deadline/exam date: never pulled forward
    course_id: int | None = None


def _months_before(d: date, months: float) -> date:
    return d - timedelta(days=round(months * 30.4))


def parse_intake(intake: str | None, today: date) -> tuple[str, int]:
    """'Fall 2027' -> ('Fall', 2027). Unknown/empty -> the next Fall at least 9 months away."""
    try:
        season, year = (intake or "").split()
        if season in START_MONTH:
            return season, int(year)
    except ValueError:
        pass
    year = today.year + (1 if today.month <= 3 else 2)
    return "Fall", year


def intake_start(intake: str | None, country: str, today: date) -> date:
    season, year = parse_intake(intake, today)
    return date(year, START_MONTH[season].get(country, 9), 1)


def application_deadline(course: Course, uni: University, start: date, season: str) -> date:
    """Catalog deadline months are for the main (Fall) intake; Spring intakes close ~4 months before start."""
    if season == "Spring":
        return _months_before(start, 4).replace(day=1)
    d = date(start.year, course.deadline_month, 1)
    while d > _months_before(start, 2):
        d = date(d.year - 1, d.month, 1)
    return d


def build_plan(p: StudentProfile, programs: list[tuple[Course, University]], today: date) -> tuple[list[TaskSpec], dict]:
    """Returns (tasks sorted by date, meta {intake, start, warning, main_country})."""
    season, _ = parse_intake(p.target_intake, today)
    countries = [u.country for _, u in programs] or (p.target_countries or ["USA"])
    main_country = max(set(countries), key=countries.count)
    start = intake_start(p.target_intake, main_country, today)
    deadlines = [(c, u, application_deadline(c, u, start, season)) for c, u in programs]
    upcoming = [d for _, _, d in deadlines if d >= today]
    first = min(upcoming) if upcoming else max(today + timedelta(days=45), _months_before(start, 6))
    last = max([d for _, _, d in deadlines] + [first])
    abroad = main_country != "India"
    t: list[TaskSpec] = []

    def add(key, title, detail, category, due, **kw):
        t.append(TaskSpec(key, title, detail, category, due, **kw))

    add("research:shortlist", "Finalise your shortlist of 5–8 programs",
        "Mix ambitious, target and safe picks; check each program's deadline and requirements on its website.",
        "research", _months_before(first, 4))
    if abroad:
        add("docs:passport", "Check your passport is valid", "It should be valid for at least 6 months beyond your course end date; renewals can take weeks.",
            "documents", _months_before(first, 4))

    # Tests
    # GRE is mainly expected by US programs; UK/Canada/Europe rarely require it
    needs_gre = any(u.country == "USA" and c.avg_gre and not c.avg_gmat for c, u in programs) and not p.gre
    needs_gmat = abroad and any(c.avg_gmat for c, _ in programs) and not (p.gmat or p.gre)
    if needs_gre or needs_gmat:
        test = "GMAT" if needs_gmat else "GRE"
        add(f"test:{test.lower()}:book", f"Book your {test} date", f"Pick a date at least 6–8 weeks before your first deadline so there's time for a retake.",
            "tests", _months_before(first, 4))
        add(f"test:{test.lower()}:take", f"Take the {test}", "Send official scores to each program when you register or right after the test.",
            "tests", _months_before(first, 2.5))
    if abroad and not (p.ielts or p.toefl):
        add("test:english:book", "Book IELTS or TOEFL", "Most programs need IELTS 6.5–7.0 (or TOEFL ~90–100); check each program's minimum.",
            "tests", _months_before(first, 3.5))
        add("test:english:take", "Take IELTS / TOEFL", "Results take about 1–2 weeks; book a retake early if you fall short.",
            "tests", _months_before(first, 2))
    india_exams = {c.entrance_exam for c, u in programs if u.country == "India" and c.entrance_exam}
    for exam in sorted(india_exams):
        if p.entrance_percentile and p.entrance_exam == exam:
            continue
        exam_month, reg_month, year = {"CAT": (11, 8, start.year - 1), "GATE": (2, 9, start.year)}.get(exam, (12, 9, start.year - 1))
        reg_year = year if reg_month < exam_month else year - 1
        add(f"test:{exam.lower()}:register", f"Register for {exam}", f"{exam} registration usually opens around {date(2000, reg_month, 1):%B}.",
            "tests", date(reg_year, reg_month, 15), fixed=True)
        add(f"test:{exam.lower()}:take", f"Take {exam}", f"{exam} is usually held in {date(2000, exam_month, 1):%B}; your percentile decides shortlists.",
            "tests", date(year, exam_month, 25), fixed=True)

    # SOP, LORs, documents
    add("sop:draft", "Write your first SOP draft", "Start with why this field, what you've done (projects, internships, results) and what you want next.",
        "sop", _months_before(first, 3))
    add("lor:ask", "Ask 2–3 recommenders for LORs", "Pick professors or managers who know your work; share your CV, SOP draft and deadlines.",
        "lor", _months_before(first, 2.5))
    add("sop:review", "Get your SOP reviewed", "Run it through PathPilot's SOP reviewer, then ask a mentor or senior for feedback.",
        "sop", _months_before(first, 2))
    add("docs:transcripts", "Collect transcripts and degree documents",
        "Get official transcripts from your college; some US/Canada programs need a WES or ECE evaluation." if abroad else
        "Keep mark sheets, degree / provisional certificate and category certificates ready.",
        "documents", _months_before(first, 2))
    add("sop:final", "Tailor and finalise your SOP for each program", "Name specific courses, labs or faculty for each program; keep within its word limit.",
        "sop", _months_before(first, 1))
    add("lor:remind", "Send polite reminders to recommenders", "Check every recommendation shows as submitted in each portal.",
        "lor", first - timedelta(days=14))

    # Applications (one per program, real deadlines)
    for c, u, d in sorted(deadlines, key=lambda x: x[2]):
        add(f"apply:{c.id}", f"Submit application: {c.program}, {u.name}", "Deadline month from our catalogue; confirm the exact date on the program website.",
            "applications", d, fixed=True, course_id=c.id)
    add("scholarships:apply", "Apply for scholarships", "Many university and external scholarships close with or before the application deadline.",
        "scholarships", first)
    if not abroad:
        add("india:interviews", "Prepare for interviews / counselling rounds",
            "IIM WAT-PI rounds run around Feb–Apr; GATE-based M.Tech admissions use COAP / CCMT rounds in spring.",
            "applications", date(start.year, 3, 1), fixed=True)

    # Finance (the loan funnel)
    add("finance:estimate", "Estimate your loan eligibility", "Use your ROI funding gap to see how much you may need to borrow and whether you'll need collateral.",
        "finance", _months_before(first, 1))
    if abroad:  # decisions follow the main country's deadlines and must come before its visa steps
        main_last = max([d for _, u, d in deadlines if u.country == main_country] or [last])
        first_visa = max((m for m, _, _ in VISA_STEPS.get(main_country, []) if m <= 5), default=3.0)  # APS-style prep excluded
        decisions = min(max(main_last + timedelta(days=60), _months_before(start, 5)), _months_before(start, first_visa + 0.25))
    else:
        decisions = date(start.year, 4, 15)
    add("decide:accept", "Compare admits and accept an offer", "Weigh admit, total cost, ROI and loan EMI; pay the deposit to confirm your seat.",
        "applications", decisions)
    add("finance:apply", "Apply for your education loan", "Apply soon after your first admit; keep the admit letter, KYC, academics and co-applicant income proofs ready.",
        "finance", min(decisions, _months_before(start, 3.5)) if abroad else _months_before(start, 2))
    if abroad:
        visa_apply = _months_before(start, min((m for m, _, _ in VISA_STEPS.get(main_country, [])), default=2.5))
        loan_apply = min(decisions, _months_before(start, 3.5))
        sanction = min(max(_months_before(start, 4.5), loan_apply + timedelta(days=21)), visa_apply - timedelta(days=7))
        add("finance:sanction", "Get your loan sanction letter", "Visa officers and universities accept it as proof of funds.",
            "finance", sanction)

    # Visa and travel
    for i, (months, title, detail) in enumerate(VISA_STEPS.get(main_country, []), start=1):
        add(f"visa:{main_country.lower()}:{i}", title, detail, "visa", _months_before(start, months))
    if abroad:
        add("travel:book", "Book flights and accommodation", "Compare university housing with private options; book flights once the visa is approved.",
            "travel", _months_before(start, 1.5))
        add("travel:forex", "Arrange forex and an international card", "Loan disbursements for tuition go directly to the university; plan living money separately.",
            "travel", _months_before(start, 1))
    add("travel:checklist", "Pre-departure checklist" if abroad else "Joining checklist",
        "Keep originals and copies of documents, insurance, offer letter and first-month expenses ready.", "travel", _months_before(start, 0.5))

    # Preparation tasks can't be in the past: spread the overdue ones, in order, over the weeks before the
    # first deadline (fixed dates stay put)
    soon = today + timedelta(days=7)
    late = sorted((x for x in t if not x.fixed and x.due < soon), key=lambda x: x.due)
    if late:  # re-space every prep task before the first deadline so their order is kept
        late = sorted((x for x in t if not x.fixed and x.due < first), key=lambda x: x.due)
        window_end = max(soon, first - timedelta(days=10)) if first > soon else soon + timedelta(days=21)
        step = (window_end - soon) / max(1, len(late) - 1)
        for i, task in enumerate(late):
            task.due = soon + step * i
    t.sort(key=lambda x: (x.due, CATEGORIES.index(x.category)))

    warning = None
    missed = [d for _, _, d in deadlines if d < today]
    if start < today + timedelta(days=150):
        warning = f"Your {p.target_intake or 'chosen'} intake starts very soon. Consider aiming for the next intake."
    elif missed:
        warning = f"{len(missed)} shortlisted deadline(s) have already passed for this intake; check for later rounds or the next intake."
    return t, {"intake": p.target_intake, "start": start, "main_country": main_country, "warning": warning}
