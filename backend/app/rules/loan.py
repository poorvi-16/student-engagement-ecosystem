"""Education-loan eligibility, offers and repayment planning. Pure rules; money is never decided by the LLM.

Products are the fictional NBFC products in data/loan_products.json. For each product we check, in order:
country and university tier, co-applicant income floor, collateral cover (secured) or an income-based
cap (unsecured), margin money, and FOIR (existing EMIs + this loan's EMI vs co-applicant income plus a
tier-based share of the student's expected salary).
Rates start at the product's floor and add transparent risk premiums. APR includes the processing fee.
Everything here is a soft, indicative estimate: no credit bureau is hit and final sanction is a human
credit decision.
"""

from dataclasses import dataclass, field

from app.catalog import get_catalog
from app.rules.finance import emi

MORATORIUM_EXTRA = {"course duration + 12 months": 12, "course duration + 6 months": 6}
UNSECURED_INCOME_MULTIPLE = {1: 8, 2: 6, 3: 4}  # unsecured cap = multiple × co-applicant annual income
FOIR_LIMIT = {"secured": 0.70, "unsecured": 0.60}
# Lenders count part of the student's expected salary as repayment income for strong universities
STUDENT_INCOME_SHARE = {1: 0.5, 2: 0.35, 3: 0.0}
TIER_PREMIUM = {1: 0.0, 2: 0.5, 3: 1.0}
TAX_RATE_OLD_REGIME = 0.312  # 30% slab + 4% cess; 80E is not available in the new regime
SEC_80E_YEARS = 8


@dataclass(frozen=True)
class LoanCase:
    country: str
    uni_tier: int
    stem: bool
    duration_months: int
    amount_lakhs: float  # what the student wants to borrow
    total_cost_lakhs: float
    co_applicant_income_lpa: float = 0.0
    co_applicant_emi_monthly: float = 0.0  # existing EMIs, ₹ per month
    collateral_value_lakhs: float = 0.0
    admitted: bool = False
    expected_salary_lakhs: float = 0.0  # student's predicted starting salary (ROI)


@dataclass
class Offer:
    product_id: str
    lender: str
    name: str
    type: str
    eligible: bool
    reasons: list[str] = field(default_factory=list)  # why not eligible / what limits the amount
    conditions: list[str] = field(default_factory=list)
    max_amount_lakhs: float = 0.0
    amount_lakhs: float = 0.0
    rate_pct: float = 0.0
    rate_breakdown: list[str] = field(default_factory=list)
    processing_fee_lakhs: float = 0.0
    apr_pct: float = 0.0
    tenure_years: int = 0
    moratorium_months: int = 0
    emi_lakhs: float = 0.0
    total_interest_lakhs: float = 0.0
    foir_pct: int = 0
    emi_pct_of_salary: int = 0
    margin_money_lakhs: float = 0.0


def _r(x: float, n: int = 1) -> float:
    return round(x, n)


def moratorium_months(product: dict, duration_months: int) -> int:
    return duration_months + MORATORIUM_EXTRA.get(product.get("moratorium", ""), 6)


def capitalised_principal(amount: float, rate_pct: float, duration_months: int, moratorium: int) -> float:
    """Simple interest accrues during the moratorium; disbursed evenly over the course (average outstanding ~ half
    the course), then the whole amount accrues until repayment starts. Unpaid interest is added to the principal."""
    avg_months = duration_months / 2 + (moratorium - duration_months)
    return amount * (1 + rate_pct / 100 * avg_months / 12)


def apr_pct(amount: float, fee: float, rate_pct: float, tenure_years: int) -> float:
    """Annual percentage rate incl. the processing fee (Key Fact Statement style): the IRR of receiving
    amount − fee and repaying the standard EMI on `amount` over the tenure. Always >= the interest rate."""
    n = tenure_years * 12
    pay = emi(amount, rate_pct, tenure_years)
    net = amount - fee
    lo, hi = 0.0, 0.05
    for _ in range(80):
        mid = (lo + hi) / 2
        pv = pay * (1 - (1 + mid) ** -n) / mid if mid else pay * n
        if pv > net:
            lo = mid
        else:
            hi = mid
    return round(lo * 1200, 2)


def evaluate(case: LoanCase, product: dict) -> Offer:
    o = Offer(product_id=product["id"], lender=product["lender"], name=product["name"], type=product["type"], eligible=True)
    secured = product["type"] == "secured"
    if case.country not in product["countries"]:
        o.eligible = False
        o.reasons.append(f"Doesn't fund study in {case.country}.")
    if case.uni_tier not in product["eligible_tiers"]:
        o.eligible = False
        o.reasons.append(f"Only funds tier {', '.join(map(str, product['eligible_tiers']))} universities.")
    if case.co_applicant_income_lpa < product["min_co_applicant_income_lpa"]:
        o.eligible = False
        o.reasons.append(f"Needs co-applicant income of at least ₹{product['min_co_applicant_income_lpa']}L a year.")

    # How much this product can lend
    margin = product.get("margin_money_pct", 0) / 100
    cap = min(product["max_amount_lakhs"], case.total_cost_lakhs * (1 - margin))
    if secured:
        if case.collateral_value_lakhs <= 0:
            o.eligible = False
            o.reasons.append("Needs property or FD collateral.")
        else:
            by_collateral = case.collateral_value_lakhs * 100 / max(1, product["collateral_cover_pct"])
            if by_collateral < cap:
                o.reasons.append(f"Limited to ₹{_r(by_collateral)}L by your collateral value.")
            cap = min(cap, by_collateral)
    else:
        by_income = case.co_applicant_income_lpa * UNSECURED_INCOME_MULTIPLE.get(case.uni_tier, 4)
        if by_income < cap:
            o.reasons.append(f"Unsecured limit is about {UNSECURED_INCOME_MULTIPLE.get(case.uni_tier, 4)}× co-applicant income here.")
        cap = min(cap, by_income)
    o.max_amount_lakhs = _r(max(0.0, cap))
    o.amount_lakhs = _r(min(case.amount_lakhs, o.max_amount_lakhs))
    if o.eligible and o.amount_lakhs < product["min_amount_lakhs"]:
        o.eligible = False
        o.reasons.append(f"Minimum loan is ₹{product['min_amount_lakhs']}L.")
    o.margin_money_lakhs = _r(case.total_cost_lakhs * margin) if margin else 0.0

    # Price: product floor + transparent premiums
    lo, hi = product["rate_range_pct"]
    rate, why = lo, [f"Base {lo}%"]
    if TIER_PREMIUM.get(case.uni_tier):
        rate += TIER_PREMIUM[case.uni_tier]
        why.append(f"+{TIER_PREMIUM[case.uni_tier]}% university tier {case.uni_tier}")
    if not case.stem:
        rate += 0.25
        why.append("+0.25% non-STEM course")
    if not secured and case.co_applicant_income_lpa < 2 * product["min_co_applicant_income_lpa"]:
        rate += 0.5
        why.append("+0.5% co-applicant income band")
    if secured and case.collateral_value_lakhs >= 1.25 * max(o.amount_lakhs, 1):
        rate -= 0.25
        why.append("−0.25% strong collateral cover")
    o.rate_pct = _r(min(hi, max(lo, rate)), 2)
    o.rate_breakdown = why

    o.tenure_years = product["max_tenure_years"]
    o.moratorium_months = moratorium_months(product, case.duration_months)
    principal = capitalised_principal(o.amount_lakhs, o.rate_pct, case.duration_months, o.moratorium_months)
    pay = emi(principal, o.rate_pct, o.tenure_years)
    o.emi_lakhs = round(pay, 3)
    o.total_interest_lakhs = _r(pay * o.tenure_years * 12 - o.amount_lakhs)
    o.processing_fee_lakhs = round(o.amount_lakhs * product["processing_fee_pct"] / 100, 2)
    if o.amount_lakhs > 0:
        o.apr_pct = apr_pct(o.amount_lakhs, o.processing_fee_lakhs, o.rate_pct, o.tenure_years)

    # FOIR: repayment capacity = co-applicant income + a tier-based share of the student's expected salary
    student_share = STUDENT_INCOME_SHARE.get(case.uni_tier, 0.0) * case.expected_salary_lakhs
    monthly_income = (case.co_applicant_income_lpa + student_share) * 1e5 / 12
    if monthly_income > 0:
        foir = (case.co_applicant_emi_monthly + pay * 1e5) / monthly_income
        o.foir_pct = round(foir * 100)
        limit = FOIR_LIMIT["secured" if secured else "unsecured"]
        if o.eligible and foir > limit and o.amount_lakhs > 0:
            o.eligible = False
            o.reasons.append(f"FOIR {o.foir_pct}% is above the {round(limit * 100)}% limit (existing EMIs + this EMI vs repayment income).")
    if case.expected_salary_lakhs > 0:
        o.emi_pct_of_salary = round(pay / (case.expected_salary_lakhs / 12) * 100)

    if not case.admitted:
        o.conditions.append("Admit letter needed before sanction")
    if secured:
        o.conditions.append("Property valuation and legal check")
    o.conditions.append("KYC and co-applicant income proof")
    return o


def offers(case: LoanCase) -> dict:
    products = get_catalog().loan_products["products"]
    all_offers = [evaluate(case, p) for p in products]
    eligible = [o for o in all_offers if o.eligible and o.amount_lakhs > 0]
    # Best = covers the most of the need, then cheapest APR
    best = min(eligible, key=lambda o: (-min(o.amount_lakhs, case.amount_lakhs), o.apr_pct)) if eligible else None
    covered = best.amount_lakhs if best else 0.0
    tips = []
    if covered < case.amount_lakhs:
        if case.collateral_value_lakhs <= 0:
            tips.append("Adding property or FD collateral unlocks secured loans with higher limits and lower rates.")
        tips.append("A co-applicant with higher income (or a second co-applicant) raises unsecured limits.")
        if case.uni_tier > 1:
            tips.append("Tier-1 universities get higher unsecured limits and better rates.")
    if any("FOIR" in r for o in all_offers for r in o.reasons):
        tips.append("Closing existing EMIs before applying improves FOIR.")
    return {"offers": all_offers, "best_id": best.product_id if best else None, "covered_lakhs": _r(covered),
            "shortfall_lakhs": _r(max(0.0, case.amount_lakhs - covered)), "tips": tips}


# ---------- repayment planner ----------

def schedule(amount: float, rate_pct: float, tenure_years: int, duration_months: int, moratorium: int,
             pay_interest_during_study: bool = False, extra_monthly_lakhs: float = 0.0, salary_lakhs: float = 0.0,
             old_tax_regime: bool = True) -> dict:
    """Year-by-year repayment with optional interest servicing during study, prepayments and the Sec 80E view."""
    r = rate_pct / 1200
    if pay_interest_during_study:
        principal = amount
        study_interest = capitalised_principal(amount, rate_pct, duration_months, moratorium) - amount  # paid as it accrues
    else:
        principal = capitalised_principal(amount, rate_pct, duration_months, moratorium)
        study_interest = principal - amount  # capitalised, paid later via EMIs
    pay = emi(principal, rate_pct, tenure_years)
    bal, month, rows, total_interest = principal, 0, [], 0.0
    while bal > 1e-6 and month < tenure_years * 12:
        year_interest = year_principal = year_paid = 0.0
        for _ in range(12):
            if bal <= 1e-6:
                break
            i = bal * r
            p = min(bal, pay - i + extra_monthly_lakhs)
            bal -= p
            year_interest += i
            year_principal += p
            year_paid += i + p
            month += 1
        total_interest += year_interest
        y = len(rows) + 1
        saving = year_interest * TAX_RATE_OLD_REGIME if old_tax_regime and y <= SEC_80E_YEARS else 0.0
        rows.append({"year": y, "paid_lakhs": _r(year_paid, 2), "interest_lakhs": _r(year_interest, 2),
                     "principal_lakhs": _r(year_principal, 2), "balance_lakhs": _r(max(0.0, bal), 2),
                     "tax_saving_80e_lakhs": _r(saving, 2)})
    base_months = tenure_years * 12
    base_interest = pay * base_months - principal
    total_interest += study_interest  # paid during study, or capitalised into the EMIs
    base_interest += study_interest
    tax_saving = sum(x["tax_saving_80e_lakhs"] for x in rows)
    return {
        "emi_lakhs": round(pay, 3),
        "study_interest_lakhs": _r(study_interest, 2),
        "study_interest_monthly_lakhs": round(study_interest / moratorium, 3) if pay_interest_during_study else 0.0,
        "repayment_starts_month": moratorium + 1,
        "months_to_repay": month,
        "months_saved": base_months - month,
        "total_interest_lakhs": _r(total_interest, 2),
        "interest_saved_lakhs": _r(max(0.0, base_interest - total_interest), 2),
        "tax_saving_80e_lakhs": _r(tax_saving, 2),
        "emi_pct_of_salary": round(pay / (salary_lakhs / 12) * 100) if salary_lakhs else None,
        "years": rows,
    }
