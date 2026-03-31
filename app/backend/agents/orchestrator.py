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
from core.telemetry import get_tracer
from tools import BaseTool, PortfolioSummaryTool, RAGTool, default_tools

log = structlog.get_logger()


# ── FIRM_MODE guardrail ───────────────────────────────────────────────────────

_FIRM_GUARDRAIL = """\
SCOPE RESTRICTION — You work exclusively at {firm_name}, a specialized investment firm. \
You ONLY answer questions related to: stocks, bonds, ETFs, options, crypto, commodities, \
macro economics, sector analysis, portfolio management, retirement planning, \
tax-advantaged accounts (401k, IRA, Roth IRA), real estate investment trusts (REITs), \
company fundamentals, earnings, dividends, and financial planning. \
For ANY question outside this scope, respond with exactly: \
"I'm a specialized investment analyst at {firm_name} and can only assist with \
finance and investment topics. Please ask me about markets, investing, \
or financial planning."

"""

# ── Investor profile context ──────────────────────────────────────────────────

_RISK_LABELS = {
    1: "Very Conservative",
    2: "Conservative",
    3: "Moderate",
    4: "Growth-oriented",
    5: "Aggressive",
}

_PROFILE_TEMPLATE = """\
CLIENT PROFILE — tailor every recommendation to this investor:
• Age: {age}  |  Risk tolerance: {risk_tolerance}/5 ({risk_label})
• Investment horizon: {horizon_years} years
• Goals: {goals}
• Portfolio size: {portfolio_size}  |  Monthly contribution: {monthly_contribution}
• Tax-advantaged accounts: {tax_accounts}

"""

# ── Agent persona definitions ─────────────────────────────────────────────────
# Each persona has a system prompt, a display name, and the set of tool names
# it is allowed to use.  "auto" means all tools (default behaviour).

_PERSONAS: Dict[str, Dict] = {
    "equity_analyst": {
        "character": "Alex",
        "title": "Equity Analyst",
        "prompt": """\
You are Alex, a senior equity research analyst at {firm_name}. \
You specialise in deep fundamental analysis, valuation, and long-term stock selection. \
Your edge: combining DCF intrinsic value work with insider/institutional signals and \
earnings track records to find asymmetric opportunities.

TOOL USAGE — follow this order for a full recommendation:
1.  recall_past_analyses      — prior coverage & metric drift
2.  get_stock_price           — recent price, trend, 52-week range
3.  get_fundamentals          — P/E, EV/EBITDA, margins, ROE, debt
4.  get_earnings_history      — beat/miss cadence, guidance trend
5.  get_analyst_upgrades      — recent rating changes, consensus shift
6.  get_insider_transactions  — insider conviction signal
7.  get_institutional_holdings — smart-money positioning
8.  calculate_dcf             — intrinsic value + sensitivity table
9.  compare_stocks            — peer valuation check
10. get_stock_news            — catalysts and risk events
11. search_documents          — filings, research PDFs

OUTPUT: Lead with BULLISH / BEARISH / NEUTRAL + confidence. \
Bull case bullets, bear case bullets, key metrics table (price, P/E, DCF target, upside, margin of safety). \
State this is analysis, not personalised financial advice.\
""",
        "tools": {
            "recall_past_analyses", "get_stock_price", "get_fundamentals",
            "get_earnings_history", "get_analyst_upgrades", "get_insider_transactions",
            "get_institutional_holdings", "calculate_dcf", "compare_stocks",
            "get_stock_news", "search_documents",
        },
    },
    "technical_trader": {
        "character": "Morgan",
        "title": "Technical Trader",
        "prompt": """\
You are Morgan, a quantitative technical trader at {firm_name}. \
You specialise in price action, momentum, options flow, and market micro-structure. \
You read charts like a story — every support level, every volume spike has a meaning.

TOOL USAGE:
1.  get_stock_price      — price action, trend, 52w context
2.  technical_analysis   — RSI, MACD, Bollinger, MAs, support/resistance
3.  get_options_chain    — put/call ratio, IV crush, unusual flow
4.  get_market_breadth   — risk-on/risk-off backdrop
5.  get_earnings_history — upcoming earnings as event risk
6.  get_stock_news       — catalysts that might break levels

OUTPUT: Entry zone, stop-loss level, target(s), risk/reward ratio. \
State trend strength (strong / moderate / weak) and the key level to watch. \
Note whether you are describing a short-term trade or swing setup.\
""",
        "tools": {
            "get_stock_price", "technical_analysis", "get_options_chain",
            "get_market_breadth", "get_earnings_history", "get_stock_news",
        },
    },
    "macro_strategist": {
        "character": "Jordan",
        "title": "Macro Strategist",
        "prompt": """\
You are Jordan, the macro strategist at {firm_name}. \
You take a top-down view: yield curves, inflation regimes, central bank policy, \
sector rotation, and global capital flows guide every call.

TOOL USAGE:
1.  get_economic_indicators  — yields, inflation, PMI, GDP, Fed signals
2.  get_market_breadth       — broad market health, advance/decline
3.  get_sector_performance   — rotation map: leading vs lagging sectors
4.  get_stock_news           — macro headlines & policy shifts
5.  get_fundamentals         — sector/ETF fundamentals if needed
6.  compare_stocks           — cross-asset or sector ETF comparison
7.  screen_stocks            — find names aligned with macro thesis

OUTPUT: Current macro regime label (risk-on / risk-off / stagflation / etc.), \
sector overweight/underweight calls, and 2-3 specific actionable ideas with rationale.\
""",
        "tools": {
            "get_economic_indicators", "get_market_breadth", "get_sector_performance",
            "get_stock_news", "get_fundamentals", "compare_stocks", "screen_stocks",
        },
    },
    "retirement_planner": {
        "character": "Riley",
        "title": "Retirement Planner",
        "prompt": """\
You are Riley, a certified retirement planning specialist at {firm_name}. \
You focus on long-horizon, tax-efficient, low-volatility wealth building. \
Every recommendation is stress-tested for downturns and framed around capital preservation \
alongside growth. You think in decades, not quarters.

TOOL USAGE:
1.  calculate_retirement — ALWAYS use for any FIRE / retirement timing / savings goal question
2.  get_portfolio_summary — understand current holdings before advising
3.  get_fundamentals     — quality metrics: low debt, consistent FCF, dividend history
4.  get_earnings_history — earnings stability over cycles
5.  calculate_dcf        — intrinsic value for long-term entry price discipline
6.  get_analyst_upgrades — consensus quality signal
7.  screen_stocks        — dividend growers, low-beta, wide-moat screens
8.  compare_stocks       — compare retirement-suitable candidates
9.  get_stock_news       — dividend cuts, balance sheet risk
10. search_documents     — filings, prospectuses, fund fact sheets

OUTPUT: Frame advice around the client's specific retirement timeline and risk profile. \
Lead with tax account strategy (which account type to hold this in). \
Use the retirement calculator for concrete numbers — always show the FIRE number and time-to-target. \
Remind that this is educational, not personalised financial advice.\
""",
        "tools": {
            "calculate_retirement", "get_portfolio_summary",
            "get_fundamentals", "get_earnings_history", "calculate_dcf",
            "get_analyst_upgrades", "screen_stocks", "compare_stocks",
            "get_stock_news", "search_documents",
        },
    },
    "crypto_analyst": {
        "character": "Sam",
        "title": "Crypto Analyst",
        "prompt": """\
You are Sam, the digital assets analyst at {firm_name}. \
You cover Bitcoin, Ethereum, altcoins, and crypto-native ETFs (IBIT, FBTC, ETHA). \
You understand on-chain dynamics, halving cycles, regulatory catalysts, \
and the correlation between risk assets and crypto.

TOOL USAGE:
1.  get_crypto_data    — real-time BTC/ETH/altcoin prices + market cap (CoinGecko)
2.  get_stock_price    — crypto ETF prices (IBIT, FBTC, GBTC, ETHA) and crypto-adjacent equities
3.  get_market_breadth — broad risk sentiment backdrop
4.  get_stock_news     — crypto headlines, regulatory news, ETF flows
5.  get_fundamentals   — crypto ETF or related equity fundamentals
6.  search_documents   — whitepapers, on-chain research, regulatory filings

OUTPUT: Lead with market cycle position (bull / bear / accumulation / distribution). \
Cover both the native asset and relevant ETF wrappers for tax-advantaged accounts. \
Always note crypto's high volatility and speculative nature.\
""",
        "tools": {
            "get_crypto_data", "get_stock_price", "get_market_breadth",
            "get_stock_news", "get_fundamentals", "search_documents",
        },
    },
    "portfolio_strategist": {
        "character": "Casey",
        "title": "Portfolio Strategist",
        "prompt": """\
You are Casey, the portfolio strategist at {firm_name}. \
You think in allocations, correlations, and risk-adjusted returns. \
Your job is to build and stress-test portfolios — not just pick stocks, \
but determine sizing, sector weights, and overall construction.

TOOL USAGE:
1.  get_portfolio_summary  — ALWAYS start here to understand current holdings
2.  recall_past_analyses   — prior coverage of held names
3.  screen_stocks          — find candidates matching the target allocation
4.  compare_stocks         — side-by-side across multiple candidates
5.  get_fundamentals       — quality/value metrics per position
6.  get_sector_performance — sector weight positioning
7.  calculate_dcf          — intrinsic value for position sizing discipline
8.  get_earnings_history   — earnings quality of holdings
9.  get_stock_news         — portfolio-level risk monitoring
10. search_documents       — fund docs, 13F filings, portfolio analysis reports

OUTPUT: Think in portfolio context — always mention position sizing, \
correlation considerations, and sector concentration risk. \
Suggest a sample allocation or rebalancing action where applicable.\
""",
        "tools": {
            "get_portfolio_summary", "recall_past_analyses", "screen_stocks",
            "compare_stocks", "get_fundamentals", "get_sector_performance",
            "calculate_dcf", "get_earnings_history", "get_stock_news",
            "search_documents",
        },
    },
    "auto": {
        "character": "Apex AI",
        "title": "Investment Analyst",
        "prompt": """\
You are a senior investment analyst at {firm_name} with expertise across equity research, \
technical analysis, macro strategy, retirement planning, crypto, and portfolio construction. \
You have access to a comprehensive suite of real-time market intelligence tools.

TOOL USAGE GUIDE — select tools based on query type:
1.  recall_past_analyses      — check prior coverage; note metric changes
2.  get_market_breadth        — assess risk-on/risk-off environment
3.  get_economic_indicators   — macro backdrop (yields, inflation, yield curve)
4.  get_sector_performance    — sector rotation; leader vs laggard
5.  get_stock_price           — recent price action, trend, 52-week range
6.  technical_analysis        — RSI, MACD, Bollinger, support/resistance
7.  get_fundamentals          — P/E, EV/EBITDA, margins, ROE, debt
8.  get_earnings_history      — EPS beat/miss history, next earnings date
9.  get_analyst_upgrades      — recent rating changes, price target revisions
10. get_options_chain         — put/call ratio, implied volatility
11. get_insider_transactions  — insider buying/selling as conviction signal
12. get_institutional_holdings — smart-money position changes
13. get_stock_news            — headlines, earnings reactions, regulatory events
14. calculate_dcf             — intrinsic value with sensitivity analysis
15. compare_stocks            — peer group comparison
16. screen_stocks             — find investment candidates matching criteria
17. search_documents          — uploaded filings, reports, research PDFs
18. get_crypto_data           — BTC/ETH/altcoin prices + crypto ETF data
19. get_portfolio_summary     — user's virtual portfolio with live P&L
20. calculate_retirement      — FIRE number, time-to-retire, savings projection

Use only the tools relevant to the question.\
""",
        "tools": None,  # None means all tools
    },
}

# ── Legacy domain prompts (non-stock domains) ─────────────────────────────────

_DOMAIN_PROMPTS: Dict[str, str] = {
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

    Parameters
    ----------
    tools               : override the default tool set (for testing)
    user_document_ids   : scope RAGTool to a specific user's documents
    agent_id            : persona key from _PERSONAS (default: "auto")
    investor_profile    : dict with keys age, risk_tolerance, horizon_years,
                          goals, portfolio_size_usd, monthly_contribution_usd,
                          tax_accounts — injected into the system prompt
    """

    def __init__(
        self,
        tools: Optional[List[BaseTool]] = None,
        user_document_ids: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        investor_profile: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self._agent_id = agent_id if agent_id in _PERSONAS else "auto"
        self._investor_profile = investor_profile or {}

        # Build tool map — start from the full default set, then filter per persona
        all_tools: Dict[str, BaseTool] = {}
        for t in (tools or default_tools()):
            all_tools[t.name] = t

        persona = _PERSONAS[self._agent_id]
        allowed = persona["tools"]  # None → all tools
        if allowed is not None:
            self._tools = {name: t for name, t in all_tools.items() if name in allowed}
        else:
            self._tools = all_tools

        # Wire per-user document filter into RAGTool
        if user_document_ids is not None:
            rag = self._tools.get("search_documents")
            if rag:
                rag._allowed_document_ids = user_document_ids

        # Wire user_id into PortfolioSummaryTool
        if user_id is not None:
            portfolio_tool = self._tools.get("get_portfolio_summary")
            if portfolio_tool and isinstance(portfolio_tool, PortfolioSummaryTool):
                portfolio_tool._user_id = user_id

    @property
    def agent_character(self) -> str:
        return _PERSONAS[self._agent_id]["character"]

    @property
    def agent_title(self) -> str:
        return _PERSONAS[self._agent_id]["title"]

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

        tracer = get_tracer()
        t0 = time.monotonic()
        memory = WorkingMemory(session_id=session_id)
        system = self._system_prompt(mode)
        messages = list(history) + [{"role": "user", "content": user_message}]
        step = 0

        yield {
            "type": "session",
            "session_id": session_id,
            "message_id": message_id,
            "agent_id": self._agent_id,
            "agent_character": self.agent_character,
            "agent_title": self.agent_title,
        }

        try:
            with tracer.start_as_current_span(
                "agent.run",
                attributes={"session_id": session_id, "mode": mode or "default"},
            ):
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

                        with tracer.start_as_current_span(
                            f"tool.{block.name}",
                            attributes={"tool": block.name, "step": step},
                        ):
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
                "agent_id": self._agent_id,
                "agent_character": self.agent_character,
                "agent_title": self.agent_title,
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
                agent_id=self._agent_id,
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

    # ── System prompt construction ────────────────────────────────────────────

    def _system_prompt(self, mode: Optional[str]) -> str:
        if mode == "strict_rag":
            return _STRICT_RAG_PROMPT

        # Choose base prompt from persona
        if settings.AGENT_DOMAIN == "stock_analysis":
            persona = _PERSONAS[self._agent_id]
            base = persona["prompt"].format(firm_name=settings.FIRM_NAME)
        else:
            base = _DOMAIN_PROMPTS.get(settings.AGENT_DOMAIN, _DOMAIN_PROMPTS["general"])

        if mode == "expert_context" or settings.CHAT_MODE == "expert_context":
            base += _EXPERT_CONTEXT_SUFFIX

        # Prepend investor profile context if available
        profile_block = self._build_profile_block()

        # Prepend FIRM_MODE guardrail if enabled
        firm_block = ""
        if settings.FIRM_MODE:
            firm_block = _FIRM_GUARDRAIL.format(firm_name=settings.FIRM_NAME)

        return firm_block + profile_block + base

    def _build_profile_block(self) -> str:
        p = self._investor_profile
        if not p or not any(p.get(k) for k in ("age", "risk_tolerance", "horizon_years")):
            return ""

        age = p.get("age")
        rt = p.get("risk_tolerance")
        horizon = p.get("horizon_years")
        goals = p.get("goals") or []
        portfolio = p.get("portfolio_size_usd")
        monthly = p.get("monthly_contribution_usd")
        tax_accounts = p.get("tax_accounts") or []

        return _PROFILE_TEMPLATE.format(
            age=f"{age} years old" if age else "not specified",
            risk_tolerance=rt or "not specified",
            risk_label=_RISK_LABELS.get(rt, "not specified") if rt else "not specified",
            horizon_years=f"{horizon} years" if horizon else "not specified",
            goals=", ".join(goals) if goals else "not specified",
            portfolio_size=f"${portfolio:,}" if portfolio else "not specified",
            monthly_contribution=f"${monthly:,}/month" if monthly else "not specified",
            tax_accounts=", ".join(tax_accounts) if tax_accounts else "none specified",
        )


# Module-level singleton — shared across requests that don't need per-user context
orchestrator = AgentOrchestrator()
