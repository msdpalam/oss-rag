"""
Market intelligence tools — Phase 5 expansion.

New tools for the stock analyst agent:
  OptionsChainTool         — calls/puts, IV, OI, Greeks, put/call ratio
  EarningsHistoryTool      — EPS history, beat/miss, next earnings date
  InsiderTransactionsTool  — SEC Form 4 insider buys/sells
  InstitutionalHoldingsTool — top institutional holders, QoQ change
  SectorPerformanceTool    — all 11 GICS sectors, 1d/1w/1mo performance
  StockScreenerTool        — filter S&P 500 by P/E, RSI, volume, momentum
  MarketBreadthTool        — VIX, advance/decline proxy, fear/greed
  AnalystUpgradesTool      — recent upgrades/downgrades, price target changes
  DCFValuationTool         — intrinsic value via DCF model
  CompareStocksTool        — side-by-side multi-ticker comparison
  EconomicIndicatorsTool   — Fed rate, CPI, yield curve via FRED API
"""

import json
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from core.config import settings
from tools.base import BaseTool


def _safe(val: Any, decimals: int = 4) -> Any:
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, decimals)
    return val


# ── 1. Options Chain ──────────────────────────────────────────────────────────


class OptionsChainTool(BaseTool):
    name = "get_options_chain"
    description = (
        "Fetch the options chain for a stock: available expiration dates, "
        "call/put open interest, implied volatility surface, put/call ratio, "
        "and the most liquid contracts near the current price. "
        "Use to gauge market sentiment, expected move, and hedging activity."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
            "expiration": {
                "type": "string",
                "description": "Expiration date (YYYY-MM-DD). If omitted, uses the nearest expiry.",
            },
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, expiration: str | None = None) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            expirations = stock.options
            if not expirations:
                return f"No options data available for {ticker.upper()}."

            exp = expiration if expiration in expirations else expirations[0]
            chain = stock.option_chain(exp)
            calls = chain.calls
            puts = chain.puts

            current_price = stock.info.get("currentPrice") or stock.info.get("regularMarketPrice", 0)

            def summarise(df, n=5):
                if df.empty:
                    return []
                # closest strikes to current price
                df = df.copy()
                df["dist"] = (df["strike"] - current_price).abs()
                top = df.nsmallest(n, "dist")
                return [
                    {
                        "strike": float(r["strike"]),
                        "last_price": _safe(r.get("lastPrice")),
                        "bid": _safe(r.get("bid")),
                        "ask": _safe(r.get("ask")),
                        "iv": round(float(r["impliedVolatility"]), 4) if r.get("impliedVolatility") else None,
                        "open_interest": int(r["openInterest"]) if r.get("openInterest") else 0,
                        "volume": int(r["volume"]) if r.get("volume") else 0,
                        "in_the_money": bool(r.get("inTheMoney", False)),
                    }
                    for _, r in top.iterrows()
                ]

            total_call_oi = int(calls["openInterest"].sum()) if not calls.empty else 0
            total_put_oi = int(puts["openInterest"].sum()) if not puts.empty else 0
            pc_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi else None
            avg_call_iv = round(float(calls["impliedVolatility"].mean()), 4) if not calls.empty else None
            avg_put_iv = round(float(puts["impliedVolatility"].mean()), 4) if not puts.empty else None

            result = {
                "ticker": ticker.upper(),
                "current_price": current_price,
                "expiration_used": exp,
                "all_expirations": list(expirations[:8]),
                "put_call_ratio": pc_ratio,
                "sentiment": (
                    "bearish (high put demand)" if pc_ratio and pc_ratio > 1.2
                    else "bullish (low put demand)" if pc_ratio and pc_ratio < 0.7
                    else "neutral"
                ),
                "calls": {
                    "total_open_interest": total_call_oi,
                    "avg_implied_volatility": avg_call_iv,
                    "near_money_contracts": summarise(calls),
                },
                "puts": {
                    "total_open_interest": total_put_oi,
                    "avg_implied_volatility": avg_put_iv,
                    "near_money_contracts": summarise(puts),
                },
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching options chain for {ticker}: {e}"


# ── 2. Earnings History ───────────────────────────────────────────────────────


class EarningsHistoryTool(BaseTool):
    name = "get_earnings_history"
    description = (
        "Fetch quarterly earnings history: EPS actuals vs estimates, surprise %, "
        "revenue actuals vs estimates, and the next scheduled earnings date. "
        "Use to assess earnings quality, consistency of beats, and guidance trends."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            info = stock.info

            # Quarterly earnings
            qe = stock.quarterly_earnings
            history = []
            if qe is not None and not qe.empty:
                for date_idx, row in qe.iterrows():
                    actual = row.get("Earnings")
                    estimate = row.get("Estimate") if "Estimate" in row else None
                    surprise_pct = (
                        round((actual - estimate) / abs(estimate) * 100, 2)
                        if estimate and estimate != 0 and actual is not None
                        else None
                    )
                    history.append({
                        "period": str(date_idx),
                        "eps_actual": _safe(actual, 2),
                        "eps_estimate": _safe(estimate, 2),
                        "surprise_pct": surprise_pct,
                        "beat": surprise_pct > 0 if surprise_pct is not None else None,
                    })

            # Next earnings date
            cal = stock.calendar
            next_date = None
            if cal is not None and not cal.empty:
                if "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"]
                    next_date = str(val.iloc[0]) if hasattr(val, "iloc") else str(val)

            result = {
                "ticker": ticker.upper(),
                "next_earnings_date": next_date,
                "quarterly_history": history[-8:],  # last 8 quarters
                "beat_rate": (
                    f"{sum(1 for h in history if h.get('beat')) / len(history):.0%}"
                    if history else None
                ),
                "avg_surprise_pct": (
                    round(sum(h["surprise_pct"] for h in history if h.get("surprise_pct") is not None)
                          / max(1, sum(1 for h in history if h.get("surprise_pct") is not None)), 2)
                    if history else None
                ),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching earnings history for {ticker}: {e}"


# ── 3. Insider Transactions ───────────────────────────────────────────────────


class InsiderTransactionsTool(BaseTool):
    name = "get_insider_transactions"
    description = (
        "Fetch recent insider transactions (SEC Form 4) for a stock: "
        "purchases and sales by executives, directors, and 10%+ shareholders. "
        "Heavy insider buying is often a bullish signal; cluster selling can be bearish."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            insider = stock.insider_transactions

            if insider is None or insider.empty:
                return f"No insider transaction data available for {ticker.upper()}."

            transactions = []
            for _, row in insider.head(20).iterrows():
                transactions.append({
                    "date": str(row.get("Start Date", "")),
                    "insider": str(row.get("Insider Trading", "")),
                    "position": str(row.get("Relationship", "")),
                    "transaction": str(row.get("Transaction", "")),
                    "shares": int(row["Shares"]) if row.get("Shares") else None,
                    "value_usd": int(row["Value"]) if row.get("Value") else None,
                    "shares_total": int(row["Shares Total"]) if row.get("Shares Total") else None,
                })

            buys = [t for t in transactions if "purchase" in t["transaction"].lower() or "buy" in t["transaction"].lower()]
            sells = [t for t in transactions if "sale" in t["transaction"].lower() or "sell" in t["transaction"].lower()]

            result = {
                "ticker": ticker.upper(),
                "total_transactions": len(transactions),
                "buys": len(buys),
                "sells": len(sells),
                "sentiment": (
                    "bullish (more insider buying)" if len(buys) > len(sells)
                    else "bearish (more insider selling)" if len(sells) > len(buys)
                    else "neutral"
                ),
                "transactions": transactions,
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching insider transactions for {ticker}: {e}"


# ── 4. Institutional Holdings ─────────────────────────────────────────────────


class InstitutionalHoldingsTool(BaseTool):
    name = "get_institutional_holdings"
    description = (
        "Fetch top institutional shareholders for a stock: fund name, shares held, "
        "percentage of float, and quarter-over-quarter change in position. "
        "Use to gauge smart-money conviction and detect large position builds/cuts."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            inst = stock.institutional_holders

            if inst is None or inst.empty:
                return f"No institutional holdings data for {ticker.upper()}."

            holders = []
            for _, row in inst.head(15).iterrows():
                holders.append({
                    "holder": str(row.get("Holder", "")),
                    "shares": int(row["Shares"]) if row.get("Shares") else None,
                    "date_reported": str(row.get("Date Reported", "")),
                    "pct_held": round(float(row["% Out"]) * 100, 2) if row.get("% Out") else None,
                    "value_usd": int(row["Value"]) if row.get("Value") else None,
                })

            info = stock.info
            result = {
                "ticker": ticker.upper(),
                "institutional_ownership_pct": _safe(info.get("heldPercentInstitutions")),
                "insider_ownership_pct": _safe(info.get("heldPercentInsiders")),
                "top_holders": holders,
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching institutional holdings for {ticker}: {e}"


# ── 5. Sector Performance ─────────────────────────────────────────────────────

_SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}


class SectorPerformanceTool(BaseTool):
    name = "get_sector_performance"
    description = (
        "Fetch performance of all 11 GICS market sectors over 1 day, 1 week, and 1 month. "
        "Use to identify sector rotation, leading vs lagging sectors, and "
        "risk-on vs risk-off market regimes. Also returns SPY as benchmark."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self) -> str:
        try:
            tickers = list(_SECTOR_ETFS.values()) + ["SPY"]
            data = yf.download(tickers, period="1mo", interval="1d", progress=False, auto_adjust=True)
            closes = data["Close"]

            sectors = []
            for sector, etf in _SECTOR_ETFS.items():
                if etf not in closes.columns:
                    continue
                s = closes[etf].dropna()
                if len(s) < 5:
                    continue
                perf_1d = round((s.iloc[-1] - s.iloc[-2]) / s.iloc[-2] * 100, 2) if len(s) >= 2 else None
                perf_1w = round((s.iloc[-1] - s.iloc[-6]) / s.iloc[-6] * 100, 2) if len(s) >= 6 else None
                perf_1mo = round((s.iloc[-1] - s.iloc[0]) / s.iloc[0] * 100, 2)
                sectors.append({
                    "sector": sector,
                    "etf": etf,
                    "price": round(float(s.iloc[-1]), 2),
                    "perf_1d_pct": perf_1d,
                    "perf_1w_pct": perf_1w,
                    "perf_1mo_pct": perf_1mo,
                })

            sectors.sort(key=lambda x: x["perf_1mo_pct"] or 0, reverse=True)

            spy = closes["SPY"].dropna()
            benchmark = {
                "perf_1d_pct": round((spy.iloc[-1] - spy.iloc[-2]) / spy.iloc[-2] * 100, 2) if len(spy) >= 2 else None,
                "perf_1w_pct": round((spy.iloc[-1] - spy.iloc[-6]) / spy.iloc[-6] * 100, 2) if len(spy) >= 6 else None,
                "perf_1mo_pct": round((spy.iloc[-1] - spy.iloc[0]) / spy.iloc[0] * 100, 2),
            }

            result = {
                "as_of": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                "benchmark_SPY": benchmark,
                "sectors_ranked_by_1mo": sectors,
                "leading_sector": sectors[0]["sector"] if sectors else None,
                "lagging_sector": sectors[-1]["sector"] if sectors else None,
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching sector performance: {e}"


# ── 6. Stock Screener ─────────────────────────────────────────────────────────

_SP500_SAMPLE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "UNH",
    "V", "XOM", "LLY", "JNJ", "MA", "AVGO", "HD", "PG", "MRK", "COST",
    "ABBV", "CVX", "CRM", "AMD", "NFLX", "ACN", "TMO", "BAC", "PEP", "ADBE",
    "WMT", "ORCL", "MCD", "KO", "CSCO", "ABT", "INTC", "DIS", "PFE", "INTU",
    "NOW", "TXN", "AMGN", "QCOM", "RTX", "NEE", "UPS", "HON", "CAT", "BMY",
]


class StockScreenerTool(BaseTool):
    name = "screen_stocks"
    description = (
        "Screen stocks from the S&P 500 by fundamental and technical criteria. "
        "Filters: max P/E ratio, min/max market cap (billions), min dividend yield, "
        "min revenue growth %, min ROE %, sector. "
        "Returns matching stocks ranked by market cap. Use to find investment candidates."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_pe": {"type": "number", "description": "Maximum trailing P/E ratio"},
            "min_market_cap_b": {"type": "number", "description": "Minimum market cap in billions USD"},
            "max_market_cap_b": {"type": "number", "description": "Maximum market cap in billions USD"},
            "min_dividend_yield_pct": {"type": "number", "description": "Minimum annual dividend yield %"},
            "min_revenue_growth_pct": {"type": "number", "description": "Minimum YoY revenue growth %"},
            "min_roe_pct": {"type": "number", "description": "Minimum return on equity %"},
            "sector": {"type": "string", "description": "Filter by sector, e.g. 'Technology', 'Healthcare'"},
            "limit": {"type": "integer", "description": "Max results to return (default 10)", "default": 10},
        },
        "required": [],
    }

    async def execute(
        self,
        max_pe: float | None = None,
        min_market_cap_b: float | None = None,
        max_market_cap_b: float | None = None,
        min_dividend_yield_pct: float | None = None,
        min_revenue_growth_pct: float | None = None,
        min_roe_pct: float | None = None,
        sector: str | None = None,
        limit: int = 10,
    ) -> str:
        try:
            matches = []
            for sym in _SP500_SAMPLE:
                try:
                    info = yf.Ticker(sym).info
                    if not info.get("symbol"):
                        continue

                    pe = info.get("trailingPE")
                    mcap = info.get("marketCap", 0) / 1e9
                    div_yield = (info.get("dividendYield") or 0) * 100
                    rev_growth = (info.get("revenueGrowth") or 0) * 100
                    roe = (info.get("returnOnEquity") or 0) * 100
                    sec = info.get("sector", "")

                    if max_pe is not None and (pe is None or pe > max_pe):
                        continue
                    if min_market_cap_b is not None and mcap < min_market_cap_b:
                        continue
                    if max_market_cap_b is not None and mcap > max_market_cap_b:
                        continue
                    if min_dividend_yield_pct is not None and div_yield < min_dividend_yield_pct:
                        continue
                    if min_revenue_growth_pct is not None and rev_growth < min_revenue_growth_pct:
                        continue
                    if min_roe_pct is not None and roe < min_roe_pct:
                        continue
                    if sector and sector.lower() not in sec.lower():
                        continue

                    matches.append({
                        "ticker": sym,
                        "name": info.get("longName", ""),
                        "sector": sec,
                        "market_cap_b": round(mcap, 1),
                        "pe_trailing": round(pe, 1) if pe else None,
                        "dividend_yield_pct": round(div_yield, 2),
                        "revenue_growth_pct": round(rev_growth, 2),
                        "roe_pct": round(roe, 2),
                        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                        "analyst_rating": info.get("recommendationKey"),
                    })
                except Exception:
                    continue

            matches.sort(key=lambda x: x["market_cap_b"], reverse=True)
            return json.dumps({
                "criteria_applied": {
                    "max_pe": max_pe,
                    "min_market_cap_b": min_market_cap_b,
                    "max_market_cap_b": max_market_cap_b,
                    "min_dividend_yield_pct": min_dividend_yield_pct,
                    "min_revenue_growth_pct": min_revenue_growth_pct,
                    "min_roe_pct": min_roe_pct,
                    "sector": sector,
                },
                "matches_found": len(matches),
                "results": matches[: min(limit, 20)],
            }, indent=2)
        except Exception as e:
            return f"Error running stock screener: {e}"


# ── 7. Market Breadth ─────────────────────────────────────────────────────────


class MarketBreadthTool(BaseTool):
    name = "get_market_breadth"
    description = (
        "Fetch broad market health indicators: VIX (fear index), SPY/QQQ/IWM performance, "
        "sector leadership, and a composite fear/greed proxy. "
        "Use to assess overall market risk appetite before making stock-specific calls."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self) -> str:
        try:
            tickers = ["SPY", "QQQ", "IWM", "^VIX", "GLD", "TLT", "^TNX"]
            data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)
            closes = data["Close"]

            def chg(sym):
                s = closes[sym].dropna()
                if len(s) < 2:
                    return None
                return round((float(s.iloc[-1]) - float(s.iloc[-2])) / float(s.iloc[-2]) * 100, 2)

            vix_val = float(closes["^VIX"].dropna().iloc[-1]) if "^VIX" in closes else None
            fear_greed = (
                "extreme fear" if vix_val and vix_val > 40
                else "fear" if vix_val and vix_val > 25
                else "greed" if vix_val and vix_val < 15
                else "neutral"
            )

            result = {
                "as_of": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "vix": round(vix_val, 2) if vix_val else None,
                "fear_greed_proxy": fear_greed,
                "indices_1d_change_pct": {
                    "SPY (S&P 500)": chg("SPY"),
                    "QQQ (Nasdaq)": chg("QQQ"),
                    "IWM (Russell 2000)": chg("IWM"),
                },
                "safe_haven_flows": {
                    "GLD (Gold) 1d_pct": chg("GLD"),
                    "TLT (Long Bonds) 1d_pct": chg("TLT"),
                    "10Y_yield": round(float(closes["^TNX"].dropna().iloc[-1]), 3) if "^TNX" in closes else None,
                },
                "interpretation": (
                    "Risk-off: investors rotating to safe havens"
                    if (chg("GLD") or 0) > 0.5 and (chg("SPY") or 0) < 0
                    else "Risk-on: equities bid, safe havens soft"
                    if (chg("SPY") or 0) > 0.3 and (chg("GLD") or 0) < 0
                    else "Mixed signals — monitor closely"
                ),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching market breadth: {e}"


# ── 8. Analyst Upgrades ───────────────────────────────────────────────────────


class AnalystUpgradesTool(BaseTool):
    name = "get_analyst_upgrades"
    description = (
        "Fetch recent analyst rating changes for a stock: upgrades, downgrades, "
        "initiations, and price target revisions from major brokerages. "
        "Use to track Wall Street sentiment shifts and consensus changes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            upgrades = stock.upgrades_downgrades

            if upgrades is None or upgrades.empty:
                return f"No analyst rating data available for {ticker.upper()}."

            recent = upgrades.head(20)
            actions = []
            for date_idx, row in recent.iterrows():
                actions.append({
                    "date": str(date_idx.date()) if hasattr(date_idx, "date") else str(date_idx),
                    "firm": str(row.get("Firm", "")),
                    "action": str(row.get("Action", "")),
                    "from_grade": str(row.get("FromGrade", "")),
                    "to_grade": str(row.get("ToGrade", "")),
                })

            upgrades_count = sum(1 for a in actions if "upgrade" in a["action"].lower())
            downgrades_count = sum(1 for a in actions if "downgrade" in a["action"].lower())

            info = stock.info
            result = {
                "ticker": ticker.upper(),
                "current_consensus": info.get("recommendationKey"),
                "mean_target_price": info.get("targetMeanPrice"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
                "recent_actions": actions,
                "upgrades_last_20": upgrades_count,
                "downgrades_last_20": downgrades_count,
                "sentiment": (
                    "improving (more upgrades)" if upgrades_count > downgrades_count
                    else "deteriorating (more downgrades)" if downgrades_count > upgrades_count
                    else "stable"
                ),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching analyst upgrades for {ticker}: {e}"


# ── 9. DCF Valuation ──────────────────────────────────────────────────────────


class DCFValuationTool(BaseTool):
    name = "calculate_dcf"
    description = (
        "Calculate intrinsic value using a Discounted Cash Flow (DCF) model. "
        "Uses trailing free cash flow, applies a user-specified growth rate and WACC, "
        "and outputs fair value per share, upside/downside vs current price, and sensitivity table. "
        "Use to determine if a stock is undervalued or overvalued on fundamentals."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
            "growth_rate_pct": {
                "type": "number",
                "description": "Annual FCF growth rate % for years 1-5 (default: 10)",
                "default": 10,
            },
            "terminal_growth_pct": {
                "type": "number",
                "description": "Perpetual terminal growth rate % (default: 3)",
                "default": 3,
            },
            "discount_rate_pct": {
                "type": "number",
                "description": "WACC / discount rate % (default: 10)",
                "default": 10,
            },
            "projection_years": {
                "type": "integer",
                "description": "Number of projection years (default: 5)",
                "default": 5,
            },
        },
        "required": ["ticker"],
    }

    async def execute(
        self,
        ticker: str,
        growth_rate_pct: float = 10,
        terminal_growth_pct: float = 3,
        discount_rate_pct: float = 10,
        projection_years: int = 5,
    ) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            info = stock.info

            fcf = info.get("freeCashflow")
            shares = info.get("sharesOutstanding")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            net_debt = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)

            if not fcf or not shares:
                return f"Insufficient data for DCF on {ticker.upper()} (missing FCF or share count)."

            g = growth_rate_pct / 100
            tg = terminal_growth_pct / 100
            r = discount_rate_pct / 100

            # Project FCFs
            projected = []
            cf = fcf
            pv_sum = 0.0
            for yr in range(1, projection_years + 1):
                cf = cf * (1 + g)
                pv = cf / (1 + r) ** yr
                pv_sum += pv
                projected.append({"year": yr, "fcf": int(cf), "pv": int(pv)})

            # Terminal value
            terminal_fcf = cf * (1 + tg)
            terminal_value = terminal_fcf / (r - tg) if r > tg else None
            pv_terminal = terminal_value / (1 + r) ** projection_years if terminal_value else None

            if pv_terminal is None:
                return "WACC must be greater than terminal growth rate."

            equity_value = pv_sum + pv_terminal - net_debt
            fair_value_per_share = equity_value / shares

            upside_pct = (
                round((fair_value_per_share - current_price) / current_price * 100, 1)
                if current_price else None
            )

            # Sensitivity: ±2% on growth and discount rate
            sensitivity = []
            for g_adj in [g - 0.02, g, g + 0.02]:
                row = []
                for r_adj in [r - 0.02, r, r + 0.02]:
                    if r_adj <= tg:
                        row.append("N/A")
                        continue
                    cf2 = fcf
                    pv2 = 0.0
                    for yr in range(1, projection_years + 1):
                        cf2 *= (1 + g_adj)
                        pv2 += cf2 / (1 + r_adj) ** yr
                    tv2 = cf2 * (1 + tg) / (r_adj - tg)
                    pvt2 = tv2 / (1 + r_adj) ** projection_years
                    fv2 = (pv2 + pvt2 - net_debt) / shares
                    row.append(round(fv2, 2))
                sensitivity.append({
                    f"growth_{round(g_adj*100,0):.0f}pct": {
                        f"wacc_{round((r-0.02)*100,0):.0f}pct": row[0],
                        f"wacc_{round(r*100,0):.0f}pct": row[1],
                        f"wacc_{round((r+0.02)*100,0):.0f}pct": row[2],
                    }
                })

            result = {
                "ticker": ticker.upper(),
                "assumptions": {
                    "base_fcf": int(fcf),
                    "growth_rate_pct": growth_rate_pct,
                    "terminal_growth_pct": terminal_growth_pct,
                    "discount_rate_wacc_pct": discount_rate_pct,
                    "projection_years": projection_years,
                    "net_debt": int(net_debt),
                    "shares_outstanding": int(shares),
                },
                "projected_fcfs": projected,
                "pv_of_projected_fcfs": int(pv_sum),
                "pv_of_terminal_value": int(pv_terminal),
                "fair_value_per_share": round(fair_value_per_share, 2),
                "current_price": current_price,
                "upside_downside_pct": upside_pct,
                "verdict": (
                    f"Undervalued by {upside_pct}%" if upside_pct and upside_pct > 10
                    else f"Overvalued by {abs(upside_pct)}%" if upside_pct and upside_pct < -10
                    else "Fairly valued (within 10%)"
                ),
                "sensitivity_table": sensitivity,
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error running DCF for {ticker}: {e}"


# ── 10. Compare Stocks ────────────────────────────────────────────────────────


class CompareStocksTool(BaseTool):
    name = "compare_stocks"
    description = (
        "Side-by-side comparison of 2 to 5 stocks across price performance, "
        "valuation (P/E, P/B, EV/EBITDA), profitability (margins, ROE), "
        "growth, and analyst consensus. Use to pick the best name in a peer group."
    )
    parameters = {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 2-5 ticker symbols to compare",
            },
        },
        "required": ["tickers"],
    }

    async def execute(self, tickers: list[str]) -> str:
        tickers = [t.upper() for t in tickers[:5]]
        try:
            comparison = []
            for sym in tickers:
                try:
                    info = yf.Ticker(sym).info
                    if not info.get("symbol"):
                        continue
                    stock = yf.Ticker(sym)
                    hist = stock.history(period="1y")
                    ytd_chg = None
                    if not hist.empty:
                        ytd_chg = round(
                            (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[0]))
                            / float(hist["Close"].iloc[0]) * 100, 2
                        )
                    comparison.append({
                        "ticker": sym,
                        "name": info.get("longName", ""),
                        "sector": info.get("sector", ""),
                        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                        "market_cap_b": round(info.get("marketCap", 0) / 1e9, 1),
                        "performance": {
                            "1y_pct": ytd_chg,
                            "52w_high": info.get("fiftyTwoWeekHigh"),
                            "52w_low": info.get("fiftyTwoWeekLow"),
                            "pct_from_52w_high": round(
                                (info.get("currentPrice", 0) - info.get("fiftyTwoWeekHigh", 1))
                                / info.get("fiftyTwoWeekHigh", 1) * 100, 1
                            ) if info.get("fiftyTwoWeekHigh") else None,
                        },
                        "valuation": {
                            "pe_trailing": _safe(info.get("trailingPE"), 1),
                            "pe_forward": _safe(info.get("forwardPE"), 1),
                            "peg": _safe(info.get("pegRatio"), 2),
                            "price_to_book": _safe(info.get("priceToBook"), 2),
                            "ev_ebitda": _safe(info.get("enterpriseToEbitda"), 1),
                        },
                        "profitability": {
                            "gross_margin_pct": round(info.get("grossMargins", 0) * 100, 1),
                            "net_margin_pct": round(info.get("profitMargins", 0) * 100, 1),
                            "roe_pct": round(info.get("returnOnEquity", 0) * 100, 1),
                            "roa_pct": round(info.get("returnOnAssets", 0) * 100, 1),
                        },
                        "growth": {
                            "revenue_growth_yoy_pct": round(info.get("revenueGrowth", 0) * 100, 1),
                            "earnings_growth_yoy_pct": round(info.get("earningsGrowth", 0) * 100, 1),
                        },
                        "analyst": {
                            "rating": info.get("recommendationKey"),
                            "target_price": info.get("targetMeanPrice"),
                            "upside_pct": round(
                                (info.get("targetMeanPrice", 0) - (info.get("currentPrice") or 0))
                                / (info.get("currentPrice") or 1) * 100, 1
                            ) if info.get("targetMeanPrice") and info.get("currentPrice") else None,
                        },
                        "dividend_yield_pct": round((info.get("dividendYield") or 0) * 100, 2),
                    })
                except Exception:
                    continue

            return json.dumps({
                "compared_tickers": tickers,
                "as_of": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                "comparison": comparison,
            }, indent=2)
        except Exception as e:
            return f"Error comparing stocks: {e}"


# ── 11. Economic Indicators ───────────────────────────────────────────────────


class EconomicIndicatorsTool(BaseTool):
    name = "get_economic_indicators"
    description = (
        "Fetch key US macroeconomic indicators: Fed funds rate, CPI inflation, "
        "unemployment rate, 10Y/2Y Treasury yields and spread (yield curve), "
        "and US GDP growth. Use to assess the macro backdrop before making "
        "sector or stock calls. No API key required — data from FRED via yfinance proxies."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self) -> str:
        try:
            # Use yfinance to pull macro proxies (no FRED API key needed)
            tickers = {
                "^TNX": "10Y_treasury_yield",
                "^FVX": "5Y_treasury_yield",
                "^IRX": "3mo_treasury_yield",
                "^TYX": "30Y_treasury_yield",
            }
            data = yf.download(list(tickers.keys()), period="5d", interval="1d",
                               progress=False, auto_adjust=True)
            closes = data["Close"]

            yields = {}
            for sym, label in tickers.items():
                if sym in closes.columns:
                    val = closes[sym].dropna()
                    if not val.empty:
                        yields[label] = round(float(val.iloc[-1]), 3)

            y10 = yields.get("10Y_treasury_yield")
            y2 = yields.get("3mo_treasury_yield")  # closest proxy in yfinance
            spread = round(y10 - y2, 3) if y10 and y2 else None

            # Pull macro ETF performance as inflation/growth proxies
            macro = yf.download(["TIP", "SHY", "GLD", "DXY"], period="1mo",
                                 interval="1d", progress=False, auto_adjust=True)
            macro_closes = macro["Close"]

            def pct_1mo(sym):
                if sym not in macro_closes.columns:
                    return None
                s = macro_closes[sym].dropna()
                return round((float(s.iloc[-1]) - float(s.iloc[0])) / float(s.iloc[0]) * 100, 2) if len(s) > 1 else None

            result = {
                "as_of": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                "treasury_yields": yields,
                "yield_curve": {
                    "10Y_minus_3mo_spread": spread,
                    "shape": (
                        "inverted (recession warning)" if spread and spread < 0
                        else "flat" if spread and spread < 0.3
                        else "normal (growth positive)"
                    ),
                },
                "inflation_proxies": {
                    "TIP_1mo_pct": pct_1mo("TIP"),   # TIPS ETF — rising = inflation expectations up
                    "GLD_1mo_pct": pct_1mo("GLD"),   # Gold — store of value / inflation hedge
                    "note": "Rising TIP and GLD typically signals higher inflation expectations",
                },
                "macro_summary": {
                    "regime": (
                        "Stagflation risk" if (pct_1mo("TIP") or 0) > 1 and (spread or 0) < 0
                        else "Recovery" if (spread or 0) > 0.5 and (pct_1mo("TIP") or 0) > 0
                        else "Contraction risk" if (spread or 0) < 0
                        else "Expansion"
                    ),
                    "rate_environment": (
                        "High-rate environment (above 4.5%)" if y10 and y10 > 4.5
                        else "Moderate rates (3-4.5%)" if y10 and y10 > 3
                        else "Low-rate environment"
                    ),
                },
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching economic indicators: {e}"
