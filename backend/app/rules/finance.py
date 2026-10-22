"""Loan arithmetic shared by the ROI calculator and (Day 3) the EMI/moratorium planner. Pure functions, ₹ lakhs."""


def emi(principal: float, annual_rate_pct: float, years: float) -> float:
    """Monthly instalment for a standard reducing-balance loan."""
    n = round(years * 12)
    if principal <= 0 or n <= 0:
        return 0.0
    r = annual_rate_pct / 1200
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def moratorium_interest(disbursals: list[tuple[float, float]], annual_rate_pct: float, moratorium_end_months: float) -> float:
    """Simple interest accrued from each disbursal (amount, month disbursed) until repayment starts."""
    return sum(amt * annual_rate_pct / 100 * max(0.0, moratorium_end_months - month) / 12 for amt, month in disbursals)


def yearly_interest(principal: float, annual_rate_pct: float, years: int) -> list[float]:
    """Interest portion of the EMIs paid in each repayment year."""
    pay, r, bal, out = emi(principal, annual_rate_pct, years), annual_rate_pct / 1200, principal, []
    for _ in range(years):
        paid = 0.0
        for _ in range(12):
            i = bal * r
            paid += i
            bal -= pay - i
        out.append(paid)
    return out
