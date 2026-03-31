"""
RetirementCalculatorTool — compound growth projections, FIRE number,
4% safe withdrawal rule, and time-to-target calculator.

No external API calls — pure financial math.
Personalised using the investor profile injected into the system prompt,
but also accepts explicit overrides as tool parameters.
"""

import math
from typing import Optional

from tools.base import BaseTool


def _fv_monthly(
    present_value: float,
    monthly_contribution: float,
    annual_return_pct: float,
    years: float,
) -> float:
    """Future value with monthly compounding and regular contributions."""
    r = annual_return_pct / 100 / 12  # monthly rate
    n = years * 12
    if r == 0:
        return present_value + monthly_contribution * n
    fv_lump = present_value * (1 + r) ** n
    fv_contrib = monthly_contribution * (((1 + r) ** n - 1) / r)
    return fv_lump + fv_contrib


def _years_to_target(
    present_value: float,
    monthly_contribution: float,
    annual_return_pct: float,
    target: float,
) -> Optional[float]:
    """Binary-search the number of years to reach target. Returns None if unreachable."""
    if present_value >= target:
        return 0.0
    if monthly_contribution <= 0 and annual_return_pct <= 0:
        return None
    lo, hi = 0.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        fv = _fv_monthly(present_value, monthly_contribution, annual_return_pct, mid)
        if fv >= target:
            hi = mid
        else:
            lo = mid
        if hi - lo < 0.01:
            break
    return round(hi, 1) if hi < 200 else None


def _monthly_needed(
    present_value: float,
    annual_return_pct: float,
    target: float,
    years: float,
) -> float:
    """Monthly contribution required to reach target in exactly `years`."""
    r = annual_return_pct / 100 / 12
    n = years * 12
    fv_lump = present_value * (1 + r) ** n
    remaining = target - fv_lump
    if remaining <= 0:
        return 0.0
    if r == 0:
        return remaining / n
    return remaining / (((1 + r) ** n - 1) / r)


def _build_report(
    annual_expenses: float,
    current_portfolio: float,
    monthly_contribution: float,
    annual_return_pct: float,
    inflation_pct: float,
    years: Optional[float],
) -> str:
    # ── FIRE number ───────────────────────────────────────────────────────────
    fire_number = annual_expenses * 25  # 4% withdrawal rule → 25× expenses
    monthly_withdrawal = annual_expenses / 12

    # Real (inflation-adjusted) return
    real_return = ((1 + annual_return_pct / 100) / (1 + inflation_pct / 100) - 1) * 100

    lines = ["RETIREMENT / FIRE ANALYSIS", "=" * 55]

    # ── Inputs ────────────────────────────────────────────────────────────────
    lines.append("\nINPUTS")
    lines.append(f"  Annual expenses (today's dollars):  ${annual_expenses:>12,.0f}")
    lines.append(f"  Current portfolio:                  ${current_portfolio:>12,.0f}")
    lines.append(f"  Monthly contribution:               ${monthly_contribution:>12,.0f}")
    lines.append(f"  Expected annual return:              {annual_return_pct:.1f}%")
    lines.append(f"  Inflation assumption:                {inflation_pct:.1f}%")
    lines.append(f"  Real (inflation-adjusted) return:    {real_return:.1f}%")

    # ── FIRE number ───────────────────────────────────────────────────────────
    lines.append("\nFIRE NUMBER (4% safe withdrawal rule)")
    lines.append(f"  Target portfolio:   ${fire_number:>12,.0f}")
    lines.append(f"  Safe monthly draw:  ${monthly_withdrawal:>12,.0f}")
    lines.append(f"  Progress:           {min(current_portfolio / fire_number * 100, 100):.1f}%  (${current_portfolio:,.0f} of ${fire_number:,.0f})")

    # ── Time to FIRE ──────────────────────────────────────────────────────────
    yrs_to_fire = _years_to_target(current_portfolio, monthly_contribution, annual_return_pct, fire_number)
    lines.append("\nTIME TO FIRE")
    if yrs_to_fire is not None:
        yrs_int = int(yrs_to_fire)
        months_rem = round((yrs_to_fire - yrs_int) * 12)
        lines.append(f"  At current savings rate: {yrs_int}y {months_rem}m")
    else:
        # How much per month is needed for a 30-year goal?
        needed = _monthly_needed(current_portfolio, annual_return_pct, fire_number, 30)
        lines.append(f"  At current rate: goal unreachable within 200 years")
        lines.append(f"  To retire in 30 years: need ${needed:,.0f}/month")

    # ── Projection table ──────────────────────────────────────────────────────
    horizons = sorted(set(filter(None, [5, 10, 15, 20, 25, 30, years])))
    lines.append(f"\n{'YEAR':>6} {'PORTFOLIO VALUE':>18} {'MONTHLY DRAW (4%)':>20} {'FIRE?':>6}")
    lines.append("-" * 55)
    for yr in horizons:
        fv = _fv_monthly(current_portfolio, monthly_contribution, annual_return_pct, yr)
        draw = fv * 0.04 / 12
        fire_ok = "YES" if fv >= fire_number else "—"
        lines.append(f"{int(yr):>6}   ${fv:>16,.0f}   ${draw:>18,.0f}  {fire_ok:>6}")

    # ── Sensitivity: impact of return assumptions ─────────────────────────────
    if years:
        lines.append(f"\nSENSITIVITY — Portfolio at year {int(years)} under different return rates:")
        lines.append(f"  {'Return':>8}  {'Portfolio':>16}  {'vs Base':>10}")
        base_fv = _fv_monthly(current_portfolio, monthly_contribution, annual_return_pct, years)
        for r in [annual_return_pct - 2, annual_return_pct - 1, annual_return_pct,
                  annual_return_pct + 1, annual_return_pct + 2]:
            if r < 0:
                continue
            fv = _fv_monthly(current_portfolio, monthly_contribution, r, years)
            diff = fv - base_fv
            marker = " ← base" if r == annual_return_pct else ""
            lines.append(f"  {r:>7.1f}%  ${fv:>15,.0f}  {diff:>+10,.0f}{marker}")

    # ── Rule-of-thumb notes ───────────────────────────────────────────────────
    lines.append("\nNOTES")
    lines.append("  • FIRE number = 25× annual expenses (4% rule, Trinity Study)")
    lines.append("  • Returns are nominal; real returns adjust for inflation")
    lines.append(f"  • 7% nominal is a common long-term S&P 500 average")
    lines.append("  • Consider tax-advantaged accounts (401k/Roth IRA) to maximise compounding")
    lines.append("  • This is illustrative modelling, not personalised financial advice")

    return "\n".join(lines)


class RetirementCalculatorTool(BaseTool):
    name = "calculate_retirement"
    description = (
        "Project retirement savings growth, calculate the FIRE number "
        "(Financial Independence, Retire Early — 25× annual expenses via the 4% rule), "
        "estimate time-to-retirement, and show a projection table across horizons. "
        "Use this for any question about retirement planning, savings goals, "
        "FIRE number, when someone can retire, or whether they are on track."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_expenses": {
                "type": "number",
                "description": "Annual living expenses in today's dollars (required). Used to calculate the FIRE number.",
            },
            "current_portfolio": {
                "type": "number",
                "description": "Current total investable portfolio in USD. Default 0.",
            },
            "monthly_contribution": {
                "type": "number",
                "description": "Monthly amount added to investments. Default 0.",
            },
            "annual_return_pct": {
                "type": "number",
                "description": "Expected nominal annual return %. Default 7 (long-run S&P 500 average).",
            },
            "inflation_pct": {
                "type": "number",
                "description": "Expected annual inflation %. Default 3.",
            },
            "years": {
                "type": "number",
                "description": "Optional specific horizon in years for a detailed sensitivity table.",
            },
        },
        "required": ["annual_expenses"],
    }

    async def execute(  # type: ignore[override]
        self,
        annual_expenses: float,
        current_portfolio: float = 0.0,
        monthly_contribution: float = 0.0,
        annual_return_pct: float = 7.0,
        inflation_pct: float = 3.0,
        years: Optional[float] = None,
    ) -> str:
        return _build_report(
            annual_expenses=annual_expenses,
            current_portfolio=current_portfolio,
            monthly_contribution=monthly_contribution,
            annual_return_pct=annual_return_pct,
            inflation_pct=inflation_pct,
            years=years,
        )
