"""Financial Calculator Tool.

All investment-metric calculations are deterministic and INR-based,financial calculations be tool-based, never
LLM-based. No function here calls an LLM.
"""

from __future__ import annotations

from typing import Any

MONTHS_PER_YEAR = 12

# Typical Indian residential buy-to-let financing assumptions, used to model
# EMI-driven cash flow (Indian rental yields are well known to rarely cover
# full-leverage EMI; appreciation, not rental cash flow, drives most returns).
DEFAULT_LOAN_TO_VALUE_RATIO = 0.80
DEFAULT_INTEREST_RATE_PCT = 9.0
DEFAULT_LOAN_TENURE_YEARS = 20
DEFAULT_OPERATING_EXPENSE_RATIO = 0.25  # property tax, maintenance, vacancy loss
DEFAULT_STAMP_DUTY_REGISTRATION_PCT = 6.0  # of price, paid upfront from the buyer's equity


def calculate_emi(principal_inr: float, annual_interest_rate_pct: float, tenure_years: int) -> float:
    """Standard reducing-balance EMI formula. Returns 0 if principal is 0."""
    if principal_inr <= 0:
        return 0.0
    monthly_rate = (annual_interest_rate_pct / 100) / MONTHS_PER_YEAR
    n_months = tenure_years * MONTHS_PER_YEAR
    if monthly_rate == 0:
        return round(principal_inr / n_months, 2)
    factor = (1 + monthly_rate) ** n_months
    emi = principal_inr * monthly_rate * factor / (factor - 1)
    return round(emi, 2)


def calculate_rental_yield(annual_rent_inr: float, price_inr: float) -> float:
    """Gross rental yield as a percentage."""
    if price_inr <= 0:
        return 0.0
    return round((annual_rent_inr / price_inr) * 100, 2)


def calculate_cap_rate(annual_net_operating_income_inr: float, price_inr: float) -> float:
    """Net operating income / price, as a percentage."""
    if price_inr <= 0:
        return 0.0
    return round((annual_net_operating_income_inr / price_inr) * 100, 2)


def calculate_cash_flow(
    annual_rent_inr: float,
    annual_operating_expenses_inr: float,
    annual_debt_service_inr: float = 0.0,
) -> float:
    """Annual cash flow in INR after operating expenses and any debt service."""
    return round(annual_rent_inr - annual_operating_expenses_inr - annual_debt_service_inr, 2)


def calculate_roi(total_gain_inr: float, total_investment_inr: float) -> float:
    """Simple ROI as a percentage over the holding period."""
    if total_investment_inr <= 0:
        return 0.0
    return round((total_gain_inr / total_investment_inr) * 100, 2)


def calculate_outstanding_balance(
    principal_inr: float, annual_interest_rate_pct: float, monthly_emi_inr: float, months_paid: int
) -> float:
    """Loan balance after `months_paid` EMIs (reducing-balance amortisation)."""
    if principal_inr <= 0:
        return 0.0
    r = (annual_interest_rate_pct / 100) / MONTHS_PER_YEAR
    if r == 0:
        return round(max(0.0, principal_inr - monthly_emi_inr * months_paid), 2)
    growth = (1 + r) ** months_paid
    balance = principal_inr * growth - monthly_emi_inr * (growth - 1) / r
    return round(max(0.0, balance), 2)


def calculate_annualised_return(total_return_pct: float, years: int) -> float | None:
    """Compound annual rate equivalent to a total return over `years`.

    None when the total loss is 100% or more (no real annualised rate exists).
    """
    if years <= 0 or total_return_pct <= -100:
        return None
    return round(((1 + total_return_pct / 100) ** (1 / years) - 1) * 100, 2)


def calculate_irr_annualised(monthly_cash_flows: list[float]) -> float | None:
    """Annualised IRR (%) of monthly cash flows, flow 0 at month 0.

    Solved by bisection on the monthly rate; None when the flows don't change
    sign (no IRR exists) or no root lies in (-99%, +100%) per month.
    """
    if not any(cf < 0 for cf in monthly_cash_flows) or not any(cf > 0 for cf in monthly_cash_flows):
        return None

    def npv(rate: float) -> float:
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(monthly_cash_flows))

    lo, hi = -0.99, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    monthly = (lo + hi) / 2
    return round(((1 + monthly) ** MONTHS_PER_YEAR - 1) * 100, 2)


def calculate_break_even_years(total_investment_inr: float, annual_cash_flow_inr: float) -> float | None:
    """Years to recover the initial investment from cash flow alone.

    Returns None if cash flow is non-positive (break-even is never reached
    on cash flow alone).
    """
    if annual_cash_flow_inr <= 0:
        return None
    return round(total_investment_inr / annual_cash_flow_inr, 1)


def _cash_flow_severity(annual_cash_flow_inr: float, price_inr: float) -> str:
    """Classify cash-flow health.

    IMPORTANT: this must be fed the *unlevered* (operating) cash flow, not the
    fully-leveraged figure. Indian gross rental yields (~2-6%) never cover an
    80%-LTV (default) EMI, so a leveraged cash flow is deeply negative for essentially
    every property — using it here mislabels the entire market as
    "significantly_negative" and is what previously biased recommendations
    toward AVOID. The operating cash flow reflects whether the asset itself is
    income-positive (financing-independent), which is the meaningful signal.
    """
    if price_inr <= 0:
        return "unknown"
    ratio_pct = (annual_cash_flow_inr / price_inr) * 100
    if ratio_pct >= 0:
        return "positive"
    if ratio_pct >= -3.0:
        return "mildly_negative"
    return "significantly_negative"


# Thresholds for what counts as "extremely strong appreciation evidence" — the
# one thing that can justify a BUY despite significantly negative cash flow.
# Both must hold: the underlying market appreciation rate itself must be high
# (not just a high ROI driven by leverage math), AND the resulting 5-year ROI
# must clear a wide margin, not just barely positive.
STRONG_APPRECIATION_RATE_THRESHOLD_PCT = 8.0
STRONG_APPRECIATION_ROI_THRESHOLD_PCT = 15.0


def _is_strong_appreciation_evidence(appreciation_pct: float, roi_pct: float) -> bool:
    return (
        appreciation_pct >= STRONG_APPRECIATION_RATE_THRESHOLD_PCT
        and roi_pct >= STRONG_APPRECIATION_ROI_THRESHOLD_PCT
    )


# Metrics that depend on rent or appreciation, i.e. on market data. Without it
# they would be computed from zero rent and zero growth, which is meaningless.
MARKET_DEPENDENT_METRICS = (
    "monthly_rent_inr",
    "annual_rent_inr",
    "annual_operating_expenses_inr",
    "unlevered_annual_cash_flow_inr",
    "annual_cash_flow_inr",
    "operating_cash_flow_inr",
    "cash_flow_after_emi_inr",
    "monthly_shortfall_after_emi_inr",
    "shortfall_pct_of_emi",
    "rental_yield_pct",
    "cap_rate_pct",
    "projected_value_inr",
    "cumulative_cash_flow_inr",
    "roi_pct",
    "equity_gain_inr",
    "roe_pct",
    "roe_annualised_pct",
    "irr_annualised_pct",
    "irr_minus_hurdle_pct",
    "break_even_years",
)


def _without_market_data(metrics: dict[str, Any]) -> dict[str, Any]:
    """Mark market-dependent metrics unavailable and clear the flags that drive
    the cash-flow, leverage and hurdle rules. Price- and loan-only figures
    (EMI, equity invested, principal repaid) stay."""
    return {
        **metrics,
        **{key: None for key in MARKET_DEPENDENT_METRICS},
        "unavailable_metrics": list(MARKET_DEPENDENT_METRICS),
        "cash_flow_severity": "unknown",
        "negative_cash_flow": False,
        "levered_cash_flow_negative": False,
        "irr_below_hurdle": False,
        "strong_appreciation_evidence": False,
    }


def compute_investment_metrics(
    property_data: dict[str, Any],
    market_data: dict[str, Any],
    budget: float,
    horizon_years: int,
    operating_expense_ratio: float = DEFAULT_OPERATING_EXPENSE_RATIO,
    loan_to_value_ratio: float = DEFAULT_LOAN_TO_VALUE_RATIO,
    interest_rate_pct: float = DEFAULT_INTEREST_RATE_PCT,
    loan_tenure_years: int = DEFAULT_LOAN_TENURE_YEARS,
    stamp_duty_registration_pct: float = DEFAULT_STAMP_DUTY_REGISTRATION_PCT,
    hurdle_rate_pct: float | None = None,
) -> dict[str, Any]:
    """Aggregate all deterministic investment metrics for the financial calculation step."""
    price_inr = float(property_data.get("price_inr", budget) or budget)
    area_sqft = float(property_data.get("area_sqft", 0) or 0)
    rent_per_sqft = float(market_data.get("avg_monthly_rent_per_sqft_inr", 0) or 0)
    appreciation_pct = float(market_data.get("appreciation_rate_5yr_pct", 0) or 0)

    monthly_rent_inr = rent_per_sqft * area_sqft
    annual_rent_inr = monthly_rent_inr * MONTHS_PER_YEAR
    annual_operating_expenses_inr = annual_rent_inr * operating_expense_ratio
    annual_net_operating_income_inr = annual_rent_inr - annual_operating_expenses_inr

    loan_principal_inr = price_inr * loan_to_value_ratio
    monthly_emi_inr = calculate_emi(loan_principal_inr, interest_rate_pct, loan_tenure_years)
    annual_debt_service_inr = round(monthly_emi_inr * MONTHS_PER_YEAR, 2)

    unlevered_cash_flow_inr = calculate_cash_flow(annual_rent_inr, annual_operating_expenses_inr)
    annual_cash_flow_inr = calculate_cash_flow(
        annual_rent_inr, annual_operating_expenses_inr, annual_debt_service_inr
    )

    rental_yield_pct = calculate_rental_yield(annual_rent_inr, price_inr)
    cap_rate_pct = calculate_cap_rate(annual_net_operating_income_inr, price_inr)

    projected_value_inr = price_inr * ((1 + appreciation_pct / 100) ** horizon_years)
    cumulative_cash_flow_inr = round(annual_cash_flow_inr * horizon_years, 2)
    total_gain_inr = (projected_value_inr - price_inr) + cumulative_cash_flow_inr
    roi_pct = calculate_roi(total_gain_inr, price_inr)
    break_even_years = calculate_break_even_years(price_inr, unlevered_cash_flow_inr)
    # a volatile HPI rate (windowed vs longest-available differ a lot) can't count as strong evidence
    strong_appreciation_evidence = _is_strong_appreciation_evidence(appreciation_pct, roi_pct) and not market_data.get(
        "hpi_volatile", False
    )
    monthly_shortfall_inr = round(max(0.0, -annual_cash_flow_inr) / MONTHS_PER_YEAR, 2)
    shortfall_pct_of_emi = round(monthly_shortfall_inr / monthly_emi_inr * 100, 1) if monthly_emi_inr else 0.0

    # Return on equity: what the buyer actually puts in (down payment + stamp
    # duty & registration) versus appreciation, cash flow after EMI, and the
    # loan principal repaid by the end of the horizon (equity built up), minus
    # stamp duty & registration, which is spent and never recovered.
    down_payment_inr = price_inr - loan_principal_inr
    stamp_duty_registration_inr = price_inr * stamp_duty_registration_pct / 100
    equity_invested_inr = down_payment_inr + stamp_duty_registration_inr
    months_paid = min(horizon_years, loan_tenure_years) * MONTHS_PER_YEAR
    outstanding_loan_inr = calculate_outstanding_balance(loan_principal_inr, interest_rate_pct, monthly_emi_inr, months_paid)
    principal_repaid_inr = round(loan_principal_inr - outstanding_loan_inr, 2)
    equity_gain_inr = (
        (projected_value_inr - price_inr) + cumulative_cash_flow_inr + principal_repaid_inr - stamp_duty_registration_inr
    )
    roe_pct = calculate_roi(equity_gain_inr, equity_invested_inr)
    roe_annualised_pct = calculate_annualised_return(roe_pct, horizon_years)

    # IRR on the buyer's actual monthly flows: equity in at month 0, cash flow
    # after EMI every month, and sale price minus outstanding loan at the end
    # (no selling costs or capital gains tax).
    monthly_cash_flow_after_emi_inr = annual_cash_flow_inr / MONTHS_PER_YEAR
    horizon_months = horizon_years * MONTHS_PER_YEAR
    irr_flows = [-equity_invested_inr] + [monthly_cash_flow_after_emi_inr] * horizon_months
    irr_flows[-1] += projected_value_inr - outstanding_loan_inr
    irr_annualised_pct = calculate_irr_annualised(irr_flows) if horizon_months else None

    # Hurdle: the return the equity must beat; by default the cost of debt.
    hurdle_is_cost_of_debt = hurdle_rate_pct is None
    hurdle_rate_pct = interest_rate_pct if hurdle_is_cost_of_debt else hurdle_rate_pct
    irr_below_hurdle = irr_annualised_pct is not None and irr_annualised_pct < hurdle_rate_pct

    metrics = {
        "price_inr": price_inr,
        "market_data_available": bool(market_data),
        "monthly_rent_inr": round(monthly_rent_inr, 2),
        "annual_rent_inr": round(annual_rent_inr, 2),
        "annual_operating_expenses_inr": round(annual_operating_expenses_inr, 2),
        "loan_assumptions": {
            "loan_to_value_ratio": loan_to_value_ratio,
            "interest_rate_pct": interest_rate_pct,
            "loan_tenure_years": loan_tenure_years,
            "monthly_emi_inr": monthly_emi_inr,
            "annual_debt_service_inr": annual_debt_service_inr,
        },
        "unlevered_annual_cash_flow_inr": unlevered_cash_flow_inr,
        "annual_cash_flow_inr": annual_cash_flow_inr,
        # Explicitly named copies of the two figures above. "annual_cash_flow_inr"
        # is AFTER the EMI; these names leave no room to confuse the two.
        "operating_cash_flow_inr": unlevered_cash_flow_inr,
        "cash_flow_after_emi_inr": annual_cash_flow_inr,
        "monthly_shortfall_after_emi_inr": monthly_shortfall_inr,
        "shortfall_pct_of_emi": shortfall_pct_of_emi,
        # Severity / negative_cash_flow describe the property's OPERATING
        # (unlevered) economics — the financing-independent measure of whether
        # the asset itself earns money. The leveraged shortfall is reported
        # separately as levered_cash_flow_negative so it can be weighed as a
        # financing caveat without disqualifying every leveraged Indian rental.
        "cash_flow_severity": _cash_flow_severity(unlevered_cash_flow_inr, price_inr),
        "rental_yield_pct": rental_yield_pct,
        "cap_rate_pct": cap_rate_pct,
        "projected_value_inr": round(projected_value_inr, 2),
        "cumulative_cash_flow_inr": cumulative_cash_flow_inr,
        # "Total return on price": (appreciation + cumulative cash flow after EMI) / price
        "roi_pct": roi_pct,
        "down_payment_inr": round(down_payment_inr, 2),
        "stamp_duty_registration_inr": round(stamp_duty_registration_inr, 2),
        "equity_invested_inr": round(equity_invested_inr, 2),
        "principal_repaid_inr": principal_repaid_inr,
        "outstanding_loan_after_horizon_inr": outstanding_loan_inr,
        "equity_gain_inr": round(equity_gain_inr, 2),
        # "Return on equity": equity_gain / equity_invested, total and compound-annualised
        "roe_pct": roe_pct,
        "roe_annualised_pct": roe_annualised_pct,
        "irr_annualised_pct": irr_annualised_pct,
        "hurdle_rate_pct": hurdle_rate_pct,
        "hurdle_is_cost_of_debt": hurdle_is_cost_of_debt,
        "irr_minus_hurdle_pct": round(irr_annualised_pct - hurdle_rate_pct, 2) if irr_annualised_pct is not None else None,
        "irr_below_hurdle": irr_below_hurdle,
        "break_even_years": break_even_years,
        "horizon_years": horizon_years,
        "negative_cash_flow": unlevered_cash_flow_inr < 0,
        "levered_cash_flow_negative": annual_cash_flow_inr < 0,
        "strong_appreciation_evidence": strong_appreciation_evidence,
        # capped further by the market data's own confidence (e.g. city-level HPI appreciation)
        "data_quality_confidence": min(
            1.0 if (price_inr and rent_per_sqft) else 0.3,
            float(market_data.get("data_quality_confidence", 1.0)),
        ),
    }
    return metrics if market_data else _without_market_data(metrics)
