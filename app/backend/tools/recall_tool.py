"""
RecallAnalysesTool — lets the agent search its own episodic memory.

The agent calls this tool to retrieve semantically similar past analyses.
Useful for:
  - Comparing current metrics to a prior analysis ("RSI was 45 three days ago")
  - Detecting trend drift across sessions
  - Avoiding redundant work when the same ticker was recently analysed
"""

import json

from tools.base import BaseTool


class RecallAnalysesTool(BaseTool):
    name = "recall_past_analyses"
    description = (
        "Search your own memory for past stock analyses similar to the current query. "
        "Use this at the start of an analysis to check if you've previously analysed "
        "the same ticker or a related question. Returns prior conclusions, dates, and "
        "key metrics so you can compare against current data and identify changes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in past analyses, e.g. 'AAPL momentum analysis' or 'Tesla valuation'",
            },
            "ticker": {
                "type": "string",
                "description": "Optional: filter results to a specific ticker symbol, e.g. AAPL",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of past analyses to return (default 3, max 5)",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, ticker: str = None, top_k: int = 3) -> str:
        from agents.episodic_memory import episodic_memory  # deferred to break circular import

        top_k = min(top_k, 5)
        episodes = await episodic_memory.search(
            query=query,
            top_k=top_k,
            ticker_filter=ticker,
        )

        if not episodes:
            return "No relevant past analyses found in memory."

        results = []
        for ep in episodes:
            results.append(
                {
                    "date": ep.get("date_str", "unknown"),
                    "tickers": ep.get("tickers", []),
                    "question": ep.get("question", ""),
                    "summary": ep.get("answer_summary", ""),
                    "tools_used": ep.get("tools_used", []),
                    "relevance_score": ep.get("relevance_score", 0),
                }
            )

        return json.dumps(
            {
                "memory_hits": len(results),
                "past_analyses": results,
            },
            indent=2,
        )
