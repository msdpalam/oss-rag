"""
TechnicalAnalysisTool — calculates common technical indicators using pandas.

No external TA library dependency — pure pandas/numpy calculations.
Indicators: RSI-14, MACD(12,26,9), Bollinger Bands(20,2), SMA 20/50/200,
            EMA 12/26, Average True Range, On-Balance Volume trend.
"""

import json

import pandas as pd
import yfinance as yf

from tools.base import BaseTool

# ── Indicator helpers ─────────────────────────────────────────────────────────


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss.replace(0, float("inf"))
    return float(100 - 100 / (1 + rs.iloc[-1]))


def _macd(close: pd.Series, fast=12, slow=26, signal=9) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return {
        "macd_line": round(float(macd.iloc[-1]), 4),
        "signal_line": round(float(sig.iloc[-1]), 4),
        "histogram": round(float(hist.iloc[-1]), 4),
        "crossover": "bullish" if macd.iloc[-1] > sig.iloc[-1] else "bearish",
        "momentum": "increasing" if hist.iloc[-1] > hist.iloc[-2] else "decreasing",
    }


def _bollinger(close: pd.Series, period=20, num_std=2) -> dict:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    current = float(close.iloc[-1])
    bandwidth = float((upper.iloc[-1] - lower.iloc[-1]) / sma.iloc[-1])
    pct_b = float((current - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]))
    return {
        "upper": round(float(upper.iloc[-1]), 2),
        "middle": round(float(sma.iloc[-1]), 2),
        "lower": round(float(lower.iloc[-1]), 2),
        "bandwidth": round(bandwidth, 4),
        "percent_b": round(pct_b, 4),
        "position": (
            "above_upper"
            if current > upper.iloc[-1]
            else "below_lower"
            if current < lower.iloc[-1]
            else "within_bands"
        ),
    }


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> float:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return round(float(tr.ewm(span=period, adjust=False).mean().iloc[-1]), 4)


def _obv_trend(close: pd.Series, volume: pd.Series, lookback=10) -> str:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * volume).cumsum()
    recent = obv.tail(lookback)
    slope = float(recent.iloc[-1] - recent.iloc[0])
    return "rising" if slope > 0 else "falling"


def _support_resistance(close: pd.Series, window=20) -> dict:
    recent = close.tail(window)
    return {
        "resistance": round(float(recent.max()), 2),
        "support": round(float(recent.min()), 2),
    }


# ── Tool ──────────────────────────────────────────────────────────────────────


class TechnicalAnalysisTool(BaseTool):
    name = "technical_analysis"
    description = (
        "Calculate technical indicators for a stock ticker: RSI (overbought/oversold), "
        "MACD (momentum/trend direction), Bollinger Bands (volatility), moving averages "
        "(SMA 20/50/200), ATR (volatility), OBV trend, and near-term support/resistance. "
        "Use for timing signals and trend assessment. Requires at least 6 months of history."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol",
            },
            "period": {
                "type": "string",
                "description": "Historical data window — use 1y or 2y for reliable SMA-200",
                "enum": ["6mo", "1y", "2y"],
                "default": "1y",
            },
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, period: str = "1y") -> str:
        try:
            stock = yf.Ticker(ticker.upper())
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 30:
                return f"Insufficient price history for technical analysis of {ticker.upper()}."

            close = hist["Close"]
            high = hist["High"]
            low = hist["Low"]
            volume = hist["Volume"]
            current = float(close.iloc[-1])

            # Moving averages
            sma = {}
            for n in [20, 50, 200]:
                if len(close) >= n:
                    val = float(close.rolling(n).mean().iloc[-1])
                    sma[f"sma_{n}"] = round(val, 2)
                    sma[f"price_vs_sma{n}"] = "above" if current > val else "below"

            ema_12 = round(float(close.ewm(span=12, adjust=False).mean().iloc[-1]), 2)
            ema_26 = round(float(close.ewm(span=26, adjust=False).mean().iloc[-1]), 2)

            rsi_val = _rsi(close)
            result = {
                "ticker": ticker.upper(),
                "current_price": round(current, 2),
                "as_of": str(hist.index[-1].date()),
                "rsi": {
                    "value": round(rsi_val, 2),
                    "signal": (
                        "overbought (>70)"
                        if rsi_val > 70
                        else "oversold (<30)"
                        if rsi_val < 30
                        else "neutral (30-70)"
                    ),
                },
                "macd": _macd(close),
                "bollinger_bands": _bollinger(close),
                "moving_averages": {
                    **sma,
                    "ema_12": ema_12,
                    "ema_26": ema_26,
                    "golden_cross": (
                        sma.get("sma_50") is not None
                        and sma.get("sma_200") is not None
                        and sma["sma_50"] > sma["sma_200"]
                    ),
                },
                "volatility": {
                    "atr_14": _atr(high, low, close),
                    "atr_pct_of_price": round(_atr(high, low, close) / current * 100, 2),
                },
                "volume": {
                    "obv_trend": _obv_trend(close, volume),
                    "avg_volume_20d": int(volume.tail(20).mean()),
                    "last_volume": int(volume.iloc[-1]),
                    "volume_vs_avg": round(float(volume.iloc[-1] / volume.tail(20).mean()), 2),
                },
                "support_resistance_20d": _support_resistance(close),
                "overall_trend": _infer_trend(current, sma, rsi_val),
            }
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error calculating technical analysis for {ticker}: {e}"


def _infer_trend(price: float, sma: dict, rsi: float) -> str:
    signals = []
    if sma.get("price_vs_sma20") == "above":
        signals.append("short_term_bullish")
    if sma.get("price_vs_sma50") == "above":
        signals.append("mid_term_bullish")
    if sma.get("price_vs_sma200") == "above":
        signals.append("long_term_bullish")
    if rsi > 70:
        signals.append("overbought")
    elif rsi < 30:
        signals.append("oversold")

    bullish = sum(1 for s in signals if "bullish" in s)
    bearish = sum(1 for s in signals if "bearish" in s)
    if bullish >= 2:
        return "bullish"
    if bearish >= 2:
        return "bearish"
    return "mixed"
