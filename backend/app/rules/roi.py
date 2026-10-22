"""ROI calculator: total cost of a program vs what it pays back. Deterministic; all money in ₹ lakhs.

Cost = tuition + living (by lifestyle) + rupee-depreciation buffer + one-time costs − scholarship.
Anything beyond the family's self-funding is assumed to be borrowed: simple interest accrues during
the moratorium (course + 6 months) and is capitalised, then repaid as EMIs. Payback counts years of
savings (a share of salary, growing yearly) needed to recover the cost plus all loan interest.
The funding gap computed here is what the Day 3 loan estimator starts from.
"""

import math
from dataclasses import asdict, dataclass

from app.catalog import Course, University, get_catalog
from app.rules.finance import emi, moratorium_interest, yearly_interest

LIVING_STYLES = {"frugal": 0.85, "standard": 1.0, "comfortable": 1.2}
MORATORIUM_EXTRA_MONTHS = 6
HORIZON_YEARS = 10
RETURNEE_PREMIUM = 1.25  # foreign degree holders returning to India vs the India median for the field


@dataclass(frozen=True)
class RoiAssumptions:
    scholarship_lakhs: float = 0.0
    living_style: str = "standard"
    inr_depreciation_pct: float = 3.0  # per year, abroad only
    salary_adjust_pct: float = 0.0  # vs program median
    work_in: str = "abroad"  # abroad | india (ignored for programs in India)
    savings_rate_pct: float = 35.0  # share of gross salary that goes to recovering the cost
    salary_growth_pct: float = 7.0
    loan_rate_pct: float = 11.0  # indicative; real offers come from the loan planner
    loan_tenure_years: int = 10


def _r(x: float) -> float:
    return round(x, 1)


def india_median_salary_lakhs(field: str, level: str) -> float:
    cat = get_catalog()
    india = [c for c in cat.courses if cat.universities[c.university_id].country == "India"]
    same = [c for c in india if c.field == field] or [c for c in india if c.level == level] or india
    return sum(c.median_salary_local for c in same) / len(same) / 1e5


def _year_chunks(years: float) -> list[float]:
    """Fractions of the course paid in each year: 1.5 years → [1, 0.5]."""
    full = math.floor(years)
    rest = years - full
    return [1.0] * full + ([rest] if rest > 1e-9 else [])


def compute_roi(course: Course, uni: University, a: RoiAssumptions, self_fund_lakhs: float = 0.0) -> dict:
    cat = get_catalog()
    india = uni.country == "India"
    years = course.duration_months / 12
    tuition = cat.to_inr(course.tuition_total_local, uni.currency) / 1e5
    living = cat.to_inr(course.living_total_local, uni.currency) / 1e5 * LIVING_STYLES.get(a.living_style, 1.0)

    # Costs are paid year by year; a weakening rupee makes later years dearer
    chunks = _year_chunks(years)
    d = 0.0 if india else a.inr_depreciation_pct / 100
    per_year = (tuition + living) / years
    fx_buffer = sum(per_year * w * ((1 + d) ** i - 1) for i, w in enumerate(chunks))
    one_time = cat.meta["countries"][uni.country].get("one_time_lakhs", 0.0)
    gross = tuition + living + fx_buffer + one_time
    scholarship = min(max(0.0, a.scholarship_lakhs), tuition)
    total = gross - scholarship

    # Funding: self-funded first, the rest borrowed and disbursed with each year's costs
    self_fund = min(max(0.0, self_fund_lakhs), total)
    gap = total - self_fund
    yearly_cost = [(one_time if i == 0 else 0.0) + per_year * w * (1 + d) ** i - scholarship * w / years
                   for i, w in enumerate(chunks)]
    own_left, disbursals = self_fund, []
    for i, cost in enumerate(yearly_cost):  # own money is spent first, then the loan is disbursed
        borrowed = max(0.0, cost - own_left)
        own_left = max(0.0, own_left - cost)
        if borrowed:
            disbursals.append((borrowed, i * 12))
    moratorium_months = course.duration_months + MORATORIUM_EXTRA_MONTHS
    m_interest = moratorium_interest(disbursals, a.loan_rate_pct, moratorium_months)
    principal = gap + m_interest
    tenure = max(1, int(a.loan_tenure_years))
    monthly_emi = emi(principal, a.loan_rate_pct, tenure)
    repay_interest = yearly_interest(principal, a.loan_rate_pct, tenure) if principal > 0 else []

    # Salary after graduation
    working_in_india = india or a.work_in == "india"
    median = cat.to_inr(course.median_salary_local, uni.currency) / 1e5
    if working_in_india and not india:
        median = min(median, india_median_salary_lakhs(course.field, course.level) * RETURNEE_PREMIUM)
    salary = median * (1 + a.salary_adjust_pct / 100)
    s, g = a.savings_rate_pct / 100, a.salary_growth_pct / 100

    # Cumulative net position at graduation (year 0) and each year after
    to_recover = total + m_interest
    net, cum_savings, cum_interest, series, payback = -to_recover, 0.0, 0.0, [], None
    series.append({"year": 0, "net_lakhs": _r(net), "salary_lakhs": _r(salary)})
    for t in range(1, HORIZON_YEARS + 1):
        yr_salary = salary * (1 + g) ** (t - 1)
        yr_interest = repay_interest[t - 1] if t <= len(repay_interest) else 0.0
        prev = net
        cum_savings += yr_salary * s
        cum_interest += yr_interest
        net = cum_savings - to_recover - cum_interest
        if payback is None and net >= 0:
            payback = t - 1 + (-prev) / (net - prev) if net != prev else t
        series.append({"year": t, "net_lakhs": _r(net), "salary_lakhs": _r(yr_salary)})

    total_interest = m_interest + sum(repay_interest)
    return {
        "cost": {
            "tuition_lakhs": _r(tuition), "living_lakhs": _r(living), "fx_buffer_lakhs": _r(fx_buffer),
            "one_time_lakhs": _r(one_time), "scholarship_lakhs": _r(scholarship), "total_lakhs": _r(total),
            "duration_months": course.duration_months,
        },
        "funding": {"self_fund_lakhs": _r(self_fund), "gap_lakhs": _r(gap)},
        "loan": {
            "principal_lakhs": _r(gap), "rate_pct": a.loan_rate_pct, "moratorium_months": moratorium_months,
            "moratorium_interest_lakhs": _r(m_interest), "emi_lakhs": round(monthly_emi, 2), "tenure_years": tenure,
            "total_interest_lakhs": _r(total_interest),
            "emi_pct_of_salary": round(monthly_emi / (salary / 12) * 100) if salary > 0 and monthly_emi else 0,
        },
        "salary": {"start_lakhs": _r(salary), "location": "India" if working_in_india else uni.country,
                   "program_median_lakhs": _r(cat.to_inr(course.median_salary_local, uni.currency) / 1e5)},
        "outcome": {
            "payback_years": round(payback, 1) if payback is not None else None,
            "ten_year_savings_lakhs": _r(cum_savings),
            "ten_year_net_lakhs": _r(net),
            "roi_multiple": round(cum_savings / (to_recover + cum_interest), 1) if to_recover > 0 else None,
        },
        "series": series,
        "assumptions": asdict(a),
    }
