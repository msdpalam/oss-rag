"""
AgentOrchestrator — multi-step agentic pipeline using Claude's tool_use API.

Flow for each request
─────────────────────
1. Send user message + conversation history + available tools to Claude.
2. If Claude returns tool_use blocks → execute tools, append results, repeat.
3. Once Claude returns no tool calls (stop_reason = end_turn) → stream the
   final synthesis answer token by token.

SSE events yielded during stream()
───────────────────────────────────
  {"type": "session",     "session_id": str, "message_id": str}
  {"type": "tool_call",   "tool": str, "input": dict, "step": int}
  {"type": "tool_result", "tool": str, "result": str, "step": int}
  {"type": "delta",       "text": str}
  {"type": "done",        "latency_ms": int, "steps": int, "chunks": [...]}
  {"type": "error",       "message": str}
"""

import time
from typing import AsyncIterator, Dict, List, Optional

import structlog
from anthropic.types import ToolUseBlock

from agents.memory import WorkingMemory
from core.config import settings
from tools import BaseTool, RAGTool, default_tools

log = structlog.get_logger()


# ── Domain system prompts ─────────────────────────────────────────────────────

_DOMAIN_PROMPTS: Dict[str, str] = {
    "stock_analysis": """\
You are a senior equity research analyst and investment strategist. You have:
- Deep expertise in fundamental analysis: DCF, comparables, financial statement analysis
- Technical analysis proficiency: trend identification, momentum indicators, chart patterns
- Understanding of macro factors: interest rates, sector rotation, geopolitical risks
- Access to real-time tools for price data, technical indicators, fundamental metrics,
  and semantic search over uploaded research documents and filings

When analysing a stock or investment question:
1. Use recall_past_analyses first to check if you've recently covered this ticker — note any metric changes
2. Use get_stock_price to understand recent price action and trend
3. Use technical_analysis for momentum, RSI, MACD, and support/resistance
4. Use get_fundamentals for valuation, profitability, and growth metrics
5. Use get_stock_news for recent headlines, earnings, analyst actions, and sentiment
6. Use search_documents to find relevant context from uploaded files (reports, filings, research)
7. Synthesise all data into a clear, structured analysis with a bull/bear case
8. Always cite data sources inline and state clearly this is analysis, not financial advice

Be specific with numbers. If data is unavailable or ambiguous, say so.\
""",
    "general": """\
You are a knowledgeable expert assistant with broad knowledge across many domains.
You have tools to search uploaded documents and retrieve information.
Use them when relevant to ground your answers in specific data.
Combine tool results with your expertise for complete, accurate answers.\
""",
}

_STRICT_RAG_PROMPT = """\
Answer using ONLY the information retrieved by the search_documents tool.
If the documents don't contain enough information, say so clearly.
Do not draw on general knowledge or make assumptions beyond the retrieved content.\
"""

_EXPERT_CONTEXT_SUFFIX = """

When tool results are available, ground your answer in them and cite sources.
When no documents are relevant, draw on your general expertise and say so.\
"""


# ── Orchestrator ──────────────────────────────────────────────────────────────


class AgentOrchestrator:
    """
    Drives the tool-use loop and streams the final answer.
    Instantiate once at module level; thread-safe (no shared mutable state per call).
    """

    def __init__(self, tools: Optional[List[BaseTool]] = None) -> None:
        self._tools: Dict[str, BaseTool] = {}
        for t in tools or default_tools():
            self._tools[t.name] = t

    @property
    def claude_tools(self) -> List[dict]:
        return [t.to_claude_schema() for t in self._tools.values()]

    # ── Public streaming entry point ──────────────────────────────────────────

    async def stream(
        self,
        user_message: str,
        history: List[dict],
        session_id: str,
        message_id: str,
        mode: Optional[str] = None,
    ) -> AsyncIterator[dict]:
        """
        Full agentic streaming run.
        Yields SSE-ready dicts. Caller serialises to JSON.
        """
        from core.claude_client import claude  # avoid circular import at module level

        t0 = time.monotonic()
        memory = WorkingMemory(session_id=session_id)
        system = self._system_prompt(mode)
        messages = list(history) + [{"role": "user", "content": user_message}]
        step = 0

        yield {"type": "session", "session_id": session_id, "message_id": message_id}

        try:
            # ── Tool-use loop (non-streaming, fast per step) ──────────────────
            while step < settings.AGENT_MAX_STEPS:
                step += 1

                response = await claude.create(
                    messages=messages,
                    system=system,
                    tools=self.claude_tools,
                )

                tool_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]

                if not tool_blocks:
                    # No tools requested — proceed straight to final streaming answer
                    break

                # Append Claude's assistant turn (may mix TextBlock + ToolUseBlock)
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in tool_blocks:
                    yield {
                        "type": "tool_call",
                        "tool": block.name,
                        "input": dict(block.input),
                        "step": step,
                    }

                    result = await self._run_tool(block.name, dict(block.input), memory)

                    yield {
                        "type": "tool_result",
                        "tool": block.name,
                        "result": result[:400],
                        "step": step,
                    }

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

                messages.append({"role": "user", "content": tool_results})

            # ── Final streaming answer ────────────────────────────────────────
            # Strip tools from the final call so Claude commits to a text response.
            async for token in claude.stream_messages(messages=messages, system=system):
                yield {"type": "delta", "text": token}

            latency_ms = int((time.monotonic() - t0) * 1000)

            # Extract tickers from tool calls for episodic storage
            ticker_tools = {
                "get_stock_price",
                "technical_analysis",
                "get_fundamentals",
                "get_stock_news",
            }
            tickers_analyzed = list(
                {
                    tc.tool_input.get("ticker", "").upper()
                    for tc in memory.tool_calls
                    if tc.tool_name in ticker_tools and tc.tool_input.get("ticker")
                }
            )
            tools_used = list({tc.tool_name for tc in memory.tool_calls})

            yield {
                "type": "done",
                "latency_ms": latency_ms,
                "steps": memory.steps_taken,
                "tickers_analyzed": tickers_analyzed,
                "tools_used": tools_used,
                "chunks": [
                    {
                        "id": c.id,
                        "score": round(c.score, 4),
                        "source": c.source,
                        "page": c.page,
                        "content": c.content,
                        "content_type": c.content_type,
                    }
                    for c in memory.rag_chunks
                ],
            }

            log.info(
                "agent.run_complete",
                session_id=session_id,
                steps=memory.steps_taken,
                latency_ms=latency_ms,
                rag_chunks=len(memory.rag_chunks),
            )

        except Exception as e:
            log.error("agent.error", error=str(e))
            yield {"type": "error", "message": str(e)}

    # ── Tool execution ────────────────────────────────────────────────────────

    async def _run_tool(self, name: str, tool_input: dict, memory: WorkingMemory) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Unknown tool: {name}"

        try:
            result = await tool.execute(**tool_input)
        except Exception as e:
            result = f"Tool '{name}' raised an error: {e}"

        memory.record(
            step=memory.steps_taken + 1,
            tool_name=name,
            tool_input=tool_input,
            result=result,
        )

        # Harvest RAG chunks for citations
        if name == "search_documents" and isinstance(tool, RAGTool):
            memory.record_rag(tool.last_chunks)

        log.info("agent.tool_executed", tool=name, result_len=len(result))
        return result

    # ── System prompt selection ───────────────────────────────────────────────

    def _system_prompt(self, mode: Optional[str]) -> str:
        if mode == "strict_rag":
            return _STRICT_RAG_PROMPT

        base = _DOMAIN_PROMPTS.get(settings.AGENT_DOMAIN, _DOMAIN_PROMPTS["general"])

        if mode == "expert_context" or settings.CHAT_MODE == "expert_context":
            base += _EXPERT_CONTEXT_SUFFIX

        return base


# Module-level singleton — shared across all requests
orchestrator = AgentOrchestrator()
