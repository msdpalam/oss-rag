"""
Stock data tools — price history and fundamentals via yfinance.

Two tools:
  StockPriceTool      — OHLCV history, 52-week range, volume
  FundamentalTool     — valuation, profitability, growth, analyst consensus
"""
import json
from typing import Any

import yfinance as yf

from tools.base import BaseTool


def _safe(info: dict, key: str, decimals: int = 4) -> Any:
    val = info.get(key)
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, decimals)
    return val


class StockPriceTool(BaseTool):
    name = "get_stock_price"
    description = (
        "Fetch historical OHLCV price data for a stock ticker. "
        "Returns current price, period high/low, percentage change, average volume, "
        "and the most recent trading sessions. Use for price trend analysis."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. AAPL, MSFT, TSLA",
            },
            "period": {
                "type": "string",
                "description": "Lookback period",
                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"],
                "default": "3mo",
            },
            "interval": {
                "type": "string",
                "description": "Bar interval",
                "enum": ["1d", "1wk", "1mo"],
                "default": "1d",
            },
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, period: str = "3mo", interval: str = "1d") -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            hist = stock.history(period=period, interval=interval)

            if hist.empty:
                return f"No price data found for {ticker.upper()}. Check the ticker symbol."

            current = float(hist["Close"].iloc[-1])
            start = float(hist["Close"].iloc[0])
            change_pct = round((current - start) / start * 100, 2)

            recent = hist.tail(10)
            result = {
                "ticker": ticker.upper(),
                "period": period,
                "current_price": round(current, 2),
                "period_change_pct": change_pct,
                "period_high": round(float(hist["High"].max()), 2),
                "period_low": round(float(hist["Low"].min()), 2),
                "avg_daily_volume": int(hist["Volume"].mean()),
                "data_points": len(hist),
                "recent_sessions": [
                    {
                        "date": str(idx.date()),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row["Volume"]),
                    }
                    for idx, row in recent.iterrows()
                ],
            }
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error fetching price data for {ticker}: {e}"


class FundamentalTool(BaseTool):
    name = "get_fundamentals"
    description = (
        "Fetch fundamental financial data for a stock: valuation ratios (P/E, P/B, EV/EBITDA), "
        "profitability metrics (margins, ROE, ROA), growth rates, balance sheet health "
        "(debt/equity, current ratio), dividends, and analyst price targets. "
        "Use for fundamental analysis and valuation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol",
            },
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str) -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            info = stock.info

            if not info or not info.get("symbol"):
                return f"No fundamental data found for {ticker.upper()}. Check the ticker symbol."

            result = {
                "ticker": ticker.upper(),
                "name": _safe(info, "longName"),
                "sector": _safe(info, "sector"),
                "industry": _safe(info, "industry"),
                "country": _safe(info, "country"),
                "market_cap": _safe(info, "marketCap", 0),
                "enterprise_value": _safe(info, "enterpriseValue", 0),
                "valuation": {
                    "pe_trailing": _safe(info, "trailingPE", 2),
                    "pe_forward": _safe(info, "forwardPE", 2),
                    "peg_ratio": _safe(info, "pegRatio", 2),
                    "price_to_book": _safe(info, "priceToBook", 2),
                    "price_to_sales_ttm": _safe(info, "priceToSalesTrailing12Months", 2),
                    "ev_to_ebitda": _safe(info, "enterpriseToEbitda", 2),
                    "ev_to_revenue": _safe(info, "enterpriseToRevenue", 2),
                },
                "profitability": {
                    "gross_margin": _safe(info, "grossMargins"),
                    "operating_margin": _safe(info, "operatingMargins"),
                    "net_margin": _safe(info, "profitMargins"),
                    "return_on_equity": _safe(info, "returnOnEquity"),
                    "return_on_assets": _safe(info, "returnOnAssets"),
                    "eps_ttm": _safe(info, "trailingEps", 2),
                    "eps_forward": _safe(info, "forwardEps", 2),
                    "revenue_ttm": _safe(info, "totalRevenue", 0),
                    "ebitda": _safe(info, "ebitda", 0),
                },
                "growth": {
                    "revenue_growth_yoy": _safe(info, "revenueGrowth"),
                    "earnings_growth_yoy": _safe(info, "earningsGrowth"),
                    "earnings_quarterly_growth": _safe(info, "earningsQuarterlyGrowth"),
                },
                "financial_health": {
                    "total_cash": _safe(info, "totalCash", 0),
                    "total_debt": _safe(info, "totalDebt", 0),
                    "debt_to_equity": _safe(info, "debtToEquity", 2),
                    "current_ratio": _safe(info, "currentRatio", 2),
                    "quick_ratio": _safe(info, "quickRatio", 2),
                    "free_cash_flow": _safe(info, "freeCashflow", 0),
                    "operating_cash_flow": _safe(info, "operatingCashflow", 0),
                },
                "dividends": {
                    "yield_annual": _safe(info, "dividendYield"),
                    "rate": _safe(info, "dividendRate", 2),
                    "payout_ratio": _safe(info, "payoutRatio"),
                    "ex_dividend_date": str(info.get("exDividendDate", "")),
                },
                "analyst_consensus": {
                    "recommendation": _safe(info, "recommendationKey"),
                    "mean_target_price": _safe(info, "targetMeanPrice", 2),
                    "high_target_price": _safe(info, "targetHighPrice", 2),
                    "low_target_price": _safe(info, "targetLowPrice", 2),
                    "number_of_analysts": _safe(info, "numberOfAnalystOpinions", 0),
                },
                "shares": {
                    "shares_outstanding": _safe(info, "sharesOutstanding", 0),
                    "float_shares": _safe(info, "floatShares", 0),
                    "short_ratio": _safe(info, "shortRatio", 2),
                    "short_percent_of_float": _safe(info, "shortPercentOfFloat"),
                    "insider_ownership": _safe(info, "heldPercentInsiders"),
                    "institutional_ownership": _safe(info, "heldPercentInstitutions"),
                },
            }
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error fetching fundamental data for {ticker}: {e}"
