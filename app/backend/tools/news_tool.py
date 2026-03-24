"""
StockNewsTool — recent news headlines via yfinance.

Returns the latest news items for a ticker: title, publisher, date, and URL.
No API key required. Used by the agent to add real-time market sentiment and
event context (earnings, analyst upgrades, macro news) to its analysis.
"""
import json
from datetime import datetime, timezone

import yfinance as yf

from tools.base import BaseTool


class StockNewsTool(BaseTool):
    name = "get_stock_news"
    description = (
        "Fetch recent news headlines for a stock ticker. "
        "Use to capture current market sentiment, recent earnings announcements, "
        "analyst upgrades/downgrades, product launches, regulatory events, or "
        "macro news affecting the stock. Call this alongside technical and fundamental "
        "analysis for a complete picture."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. AAPL, MSFT, TSLA",
            },
            "max_items": {
                "type": "integer",
                "description": "Number of news items to return (default 8, max 15)",
                "default": 8,
            },
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, max_items: int = 8) -> str:
        max_items = min(max_items, 15)
        try:
            stock = yf.Ticker(ticker.upper())
            raw_news = stock.news or []

            if not raw_news:
                return f"No recent news found for {ticker.upper()}."

            items = []
            for article in raw_news[:max_items]:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown source")
                link = article.get("link", "")

                ts = article.get("providerPublishTime", 0)
                if ts:
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                else:
                    date_str = "date unknown"

                items.append({
                    "date": date_str,
                    "headline": title,
                    "source": publisher,
                    "url": link,
                })

            result = {
                "ticker": ticker.upper(),
                "news_count": len(items),
                "retrieved_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "articles": items,
            }
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error fetching news for {ticker}: {e}"
