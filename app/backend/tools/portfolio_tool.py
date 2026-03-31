"""
PortfolioSummaryTool — reads the user's virtual portfolio from PostgreSQL,
fetches live prices via yfinance (or CoinGecko for crypto), and returns
a P&L summary with allocation percentages.

The user_id is injected by AgentOrchestrator at construction time.
"""

import asyncio
from typing import Optional

import yfinance as yf

from tools.base import BaseTool


def _fetch_live_price(ticker: str, asset_type: str) -> Optional[float]:
    """Return current price for a ticker. None on failure."""
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        return float(price) if price else None
    except Exception:
        return None


def _build_portfolio_report(positions: list) -> str:
    """
    positions: list of dicts with keys:
        ticker, asset_type, shares, avg_cost_usd, notes
    """
    if not positions:
        return (
            "The portfolio is empty. "
            "Add positions via the Portfolio tab (ticker, shares, avg cost)."
        )

    rows = []
    total_cost = 0.0
    total_value = 0.0
    price_cache = {}

    for p in positions:
        ticker = p["ticker"]
        shares = float(p["shares"])
        avg_cost = float(p["avg_cost_usd"])
        asset_type = p.get("asset_type", "stock")

        # Fetch live price
        price = _fetch_live_price(ticker, asset_type)
        price_cache[ticker] = price

        cost_basis = shares * avg_cost
        total_cost += cost_basis

        if price is not None:
            current_value = shares * price
            total_value += current_value
            pnl = current_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0
            rows.append({
                "ticker": ticker,
                "asset_type": asset_type,
                "shares": shares,
                "avg_cost": avg_cost,
                "price": price,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            })
        else:
            rows.append({
                "ticker": ticker,
                "asset_type": asset_type,
                "shares": shares,
                "avg_cost": avg_cost,
                "price": None,
                "cost_basis": cost_basis,
                "current_value": None,
                "pnl": None,
                "pnl_pct": None,
            })

    # Sort by current value desc (unknowns at end)
    rows.sort(key=lambda r: r["current_value"] or 0, reverse=True)

    lines = ["VIRTUAL PORTFOLIO SUMMARY", "=" * 50]

    # Position table
    lines.append(f"\n{'TICKER':<8} {'TYPE':<10} {'SHARES':>10} {'AVG COST':>10} {'PRICE':>10} {'VALUE':>12} {'P&L':>10} {'P&L%':>7} {'ALLOC':>7}")
    lines.append("-" * 90)

    for r in rows:
        alloc = (r["current_value"] / total_value * 100) if total_value and r["current_value"] else 0
        if r["price"] is not None:
            pnl_str = f"${r['pnl']:+,.0f}"
            lines.append(
                f"{r['ticker']:<8} {r['asset_type']:<10} {r['shares']:>10.4f} "
                f"${r['avg_cost']:>9,.2f} ${r['price']:>9,.2f} "
                f"${r['current_value']:>11,.2f} "
                f"{pnl_str:>10} "
                f"{r['pnl_pct']:>+6.1f}% "
                f"{alloc:>6.1f}%"
            )
        else:
            lines.append(
                f"{r['ticker']:<8} {r['asset_type']:<10} {r['shares']:>10.4f} "
                f"${r['avg_cost']:>9,.2f} {'N/A':>10} {'N/A':>12} {'N/A':>10} {'N/A':>7} {'N/A':>7}"
            )

    lines.append("-" * 90)

    # Portfolio totals
    total_pnl = total_value - total_cost if total_value else None
    total_pnl_pct = (total_pnl / total_cost * 100) if total_pnl is not None and total_cost else None

    lines.append(f"\nPORTFOLIO TOTALS")
    lines.append(f"  Total cost basis:   ${total_cost:>12,.2f}")
    if total_value:
        lines.append(f"  Current value:      ${total_value:>12,.2f}")
        lines.append(
            f"  Unrealised P&L:     "
            f"{'$'+f'{total_pnl:+,.2f}':>13}  ({total_pnl_pct:+.1f}%)"
        )

    # Top winners / losers
    priced = [r for r in rows if r["pnl"] is not None]
    if priced:
        best = max(priced, key=lambda r: r["pnl_pct"])
        worst = min(priced, key=lambda r: r["pnl_pct"])
        lines.append(f"\n  Best performer:  {best['ticker']} ({best['pnl_pct']:+.1f}%)")
        lines.append(f"  Worst performer: {worst['ticker']} ({worst['pnl_pct']:+.1f}%)")

    return "\n".join(lines)


class PortfolioSummaryTool(BaseTool):
    name = "get_portfolio_summary"
    description = (
        "Retrieve the user's virtual portfolio: all positions with live prices, "
        "unrealised P&L (profit/loss), allocation percentages, and a total portfolio value. "
        "Use this before making portfolio-level recommendations or rebalancing suggestions."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    # Injected by AgentOrchestrator at construction time
    _user_id: Optional[str] = None

    async def execute(self) -> str:  # type: ignore[override]
        if not self._user_id:
            return "Portfolio not available — no user context provided."

        # Fetch positions from DB
        from sqlalchemy import select
        from core.database import AsyncSessionLocal
        from core.models import PortfolioPosition
        import uuid as _uuid

        try:
            uid = _uuid.UUID(self._user_id)
        except ValueError:
            return "Invalid user context."

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PortfolioPosition)
                .where(PortfolioPosition.user_id == uid)
                .order_by(PortfolioPosition.added_at)
            )
            positions = [
                {
                    "ticker": p.ticker,
                    "asset_type": p.asset_type,
                    "shares": float(p.shares),
                    "avg_cost_usd": float(p.avg_cost_usd),
                    "notes": p.notes,
                }
                for p in result.scalars().all()
            ]

        return await asyncio.to_thread(_build_portfolio_report, positions)
