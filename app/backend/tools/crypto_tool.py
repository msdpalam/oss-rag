"""
CryptoTool — real-time cryptocurrency data.

Sources:
  • CoinGecko free public API (no key) — BTC/ETH/altcoins
  • yfinance — crypto ETFs: IBIT, FBTC, GBTC, ETHA, ARKB, BRRR

tool name: get_crypto_data
"""

import asyncio
from typing import List

import requests
import yfinance as yf

from tools.base import BaseTool

# ── CoinGecko coin ID lookup ──────────────────────────────────────────────────

_SYMBOL_TO_ID = {
    "BTC":   "bitcoin",
    "ETH":   "ethereum",
    "BNB":   "binancecoin",
    "SOL":   "solana",
    "XRP":   "ripple",
    "ADA":   "cardano",
    "AVAX":  "avalanche-2",
    "DOT":   "polkadot",
    "MATIC": "matic-network",
    "LINK":  "chainlink",
    "LTC":   "litecoin",
    "DOGE":  "dogecoin",
    "SHIB":  "shiba-inu",
    "UNI":   "uniswap",
    "ATOM":  "cosmos",
    "TRX":   "tron",
    "TON":   "the-open-network",
    "APT":   "aptos",
    "ARB":   "arbitrum",
    "OP":    "optimism",
}

# Crypto ETF tickers — fetched via yfinance instead of CoinGecko
_CRYPTO_ETFS = {"IBIT", "FBTC", "GBTC", "ETHA", "ARKB", "BRRR", "BTCO", "HODL"}

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_TIMEOUT = 10  # seconds


def _fetch_coingecko(coin_ids: List[str]) -> dict:
    """Fetch price, 24h change, market cap, and volume for a list of CoinGecko IDs."""
    url = f"{_COINGECKO_BASE}/simple/price"
    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _fetch_crypto_etfs(tickers: List[str]) -> List[str]:
    """Fetch crypto ETF prices via yfinance. Returns formatted lines."""
    lines = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)
            if price and prev_close:
                chg_pct = (price - prev_close) / prev_close * 100
                lines.append(
                    f"{ticker} (Crypto ETF): ${price:,.2f}  "
                    f"({chg_pct:+.2f}% today)"
                )
            elif price:
                lines.append(f"{ticker} (Crypto ETF): ${price:,.2f}")
        except Exception as e:
            lines.append(f"{ticker}: data unavailable ({e})")
    return lines


def _fmt_large(n: float) -> str:
    if n >= 1e12:
        return f"${n / 1e12:.2f}T"
    if n >= 1e9:
        return f"${n / 1e9:.2f}B"
    if n >= 1e6:
        return f"${n / 1e6:.2f}M"
    return f"${n:,.0f}"


def _build_crypto_report(symbols: List[str]) -> str:
    symbols_upper = [s.strip().upper() for s in symbols]

    etf_tickers = [s for s in symbols_upper if s in _CRYPTO_ETFS]
    coin_symbols = [s for s in symbols_upper if s not in _CRYPTO_ETFS]

    sections: List[str] = []

    # ── CoinGecko coins ───────────────────────────────────────────────────────
    if coin_symbols:
        coin_ids = []
        unmapped: List[str] = []
        for sym in coin_symbols:
            cid = _SYMBOL_TO_ID.get(sym)
            if cid:
                coin_ids.append(cid)
            else:
                # treat unknown as a CoinGecko ID directly (e.g. user typed "bitcoin")
                coin_ids.append(sym.lower())

        try:
            data = _fetch_coingecko(coin_ids)
        except Exception as e:
            sections.append(f"CoinGecko error: {e}")
            data = {}

        id_to_sym = {v: k for k, v in _SYMBOL_TO_ID.items()}
        rows: List[str] = []
        for cid in coin_ids:
            info = data.get(cid)
            if not info:
                rows.append(f"  {cid.upper()}: no data returned")
                continue
            sym = id_to_sym.get(cid, cid.upper())
            price = info.get("usd", 0)
            chg = info.get("usd_24h_change", 0) or 0
            mcap = info.get("usd_market_cap", 0) or 0
            vol = info.get("usd_24h_vol", 0) or 0
            rows.append(
                f"  {sym} ({cid})\n"
                f"    Price:       ${price:,.4f}" + (f"  [{price:,.2f}]" if price > 1 else "") + "\n"
                f"    24h change:  {chg:+.2f}%\n"
                f"    Market cap:  {_fmt_large(mcap)}\n"
                f"    24h volume:  {_fmt_large(vol)}"
            )
        sections.append("CRYPTOCURRENCY PRICES (CoinGecko)\n" + "\n\n".join(rows))

    # ── Crypto ETFs ───────────────────────────────────────────────────────────
    if etf_tickers:
        etf_lines = _fetch_crypto_etfs(etf_tickers)
        sections.append("CRYPTO ETFs (NYSE/NASDAQ via yfinance)\n" + "\n".join(f"  {l}" for l in etf_lines))

    if not sections:
        return "No recognised crypto symbols provided. Try BTC, ETH, SOL, or ETF tickers IBIT/FBTC."

    return "\n\n".join(sections)


class CryptoTool(BaseTool):
    name = "get_crypto_data"
    description = (
        "Fetch real-time cryptocurrency prices and market data. "
        "Supports major coins (BTC, ETH, SOL, XRP, ADA, AVAX, DOT, MATIC, LINK, LTC, DOGE, UNI, ATOM, TRX, etc.) "
        "via CoinGecko, and crypto ETFs (IBIT, FBTC, GBTC, ETHA, ARKB, BRRR) via yfinance. "
        "Returns price, 24-hour change, market cap, and volume."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of crypto ticker symbols or ETF tickers. "
                    "Examples: ['BTC', 'ETH', 'SOL'] or ['IBIT', 'FBTC'] or mixed."
                ),
            },
        },
        "required": ["symbols"],
    }

    async def execute(self, symbols: List[str]) -> str:  # type: ignore[override]
        return await asyncio.to_thread(_build_crypto_report, symbols)
