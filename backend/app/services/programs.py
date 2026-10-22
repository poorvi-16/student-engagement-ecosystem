"""Program deep-dive: admit odds with what-if levers + ROI with an India-vs-abroad comparison.

Shared by the /programs API and the mentor's `analyze_program` tool, so both always agree.
"""

from app.catalog import Course, University, get_catalog
from app.db.models import StudentProfile
from app.ml.admit import admit_chances, explain
from app.ml.features import Applicant
from app.rules.roi import RoiAssumptions, compute_roi
from app.services.navigator import TIER_WEIGHT


def get_program(course_id: int) -> tuple[Course, University] | None:
    cat = get_catalog()
    c = next((c for c in cat.courses if c.id == course_id), None)
    return (c, cat.universities[c.university_id]) if c else None


def program_info(c: Course, u: University) -> dict:
    return {
        "course_id": c.id, "university": u.name, "country": u.country, "city": u.city, "tier": u.tier,
        "qs_rank": u.qs_rank, "program": c.program, "field": c.field, "level": c.level,
        "duration_months": c.duration_months, "stem": c.stem, "deadline_month": c.deadline_month,
        "acceptance_rate": c.acceptance_rate, "entrance_exam": c.entrance_exam,
    }


def alternative(p: StudentProfile, c: Course, u: University) -> tuple[Course, University] | None:
    """For an abroad program, the best-value program in India in the same field (and vice versa)."""
    cat = get_catalog()
    want_india = u.country != "India"
    abroad_countries = [x for x in p.target_countries if x != "India"] or ["USA"]

    def ok(oc: Course, ou: University) -> bool:
        if (ou.country == "India") != want_india or oc.level != c.level:
            return False
        return want_india or ou.country in abroad_countries

    pool = [(oc, cat.universities[oc.university_id]) for oc in cat.courses]
    pool = [(oc, ou) for oc, ou in pool if ok(oc, ou)]
    same_field = [(oc, ou) for oc, ou in pool if oc.field == c.field]
    pool = same_field or pool
    if not pool:
        return None

    def value(pair: tuple[Course, University]) -> float:
        oc, ou = pair
        cost = cat.to_inr(oc.tuition_total_local + oc.living_total_local, ou.currency)
        return TIER_WEIGHT[ou.tier] * cat.to_inr(oc.median_salary_local, ou.currency) / cost

    return max(pool, key=value)


def roi_with_alternative(p: StudentProfile, c: Course, u: University, a: RoiAssumptions,
                         self_fund_lakhs: float | None = None) -> dict:
    budget = (p.budget_lakhs or 0) if self_fund_lakhs is None else self_fund_lakhs
    out = {"roi": compute_roi(c, u, a, budget), "alternative": None}
    alt = alternative(p, c, u)
    if alt:
        oc, ou = alt
        # Same personal assumptions, but the scholarship belongs to the chosen program
        alt_a = RoiAssumptions(**{**a.__dict__, "scholarship_lakhs": 0.0})
        out["alternative"] = {
            "program": program_info(oc, ou),
            "chance": admit_chances(Applicant.from_profile(p), [(oc, ou)])[0],
            "roi": compute_roi(oc, ou, alt_a, budget),
        }
    return out


def admit_view(p: StudentProfile, c: Course, u: University, overrides: dict | None = None) -> dict:
    base = Applicant.from_profile(p)
    view = explain(base.with_(**(overrides or {})), c, u)
    if overrides:
        view["baseline_chance"] = admit_chances(base, [(c, u)])[0]
    return view
