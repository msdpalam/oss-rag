"""
Unit tests for the agent tool layer.

Validates that every tool:
  - implements the BaseTool contract
  - produces a valid Claude tool_use schema
  - has no duplicate names

No external services or model loading required.
"""
import pytest

from tools import (
    AnalystUpgradesTool,
    BaseTool,
    CompareStocksTool,
    CryptoTool,
    DCFValuationTool,
    EarningsHistoryTool,
    EconomicIndicatorsTool,
    FundamentalTool,
    InsiderTransactionsTool,
    InstitutionalHoldingsTool,
    MarketBreadthTool,
    OptionsChainTool,
    PortfolioSummaryTool,
    RAGTool,
    RecallAnalysesTool,
    RetirementCalculatorTool,
    SectorPerformanceTool,
    StockNewsTool,
    StockPriceTool,
    StockScreenerTool,
    TechnicalAnalysisTool,
    default_tools,
)

ALL_TOOL_CLASSES = [
    RAGTool,
    StockPriceTool,
    FundamentalTool,
    TechnicalAnalysisTool,
    StockNewsTool,
    RecallAnalysesTool,
    OptionsChainTool,
    EarningsHistoryTool,
    InsiderTransactionsTool,
    InstitutionalHoldingsTool,
    SectorPerformanceTool,
    StockScreenerTool,
    MarketBreadthTool,
    AnalystUpgradesTool,
    DCFValuationTool,
    CompareStocksTool,
    EconomicIndicatorsTool,
    CryptoTool,
    PortfolioSummaryTool,
    RetirementCalculatorTool,
]

EXPECTED_TOOL_NAMES = {
    "search_documents",
    "get_stock_price",
    "get_fundamentals",
    "technical_analysis",
    "get_stock_news",
    "recall_past_analyses",
    "get_options_chain",
    "get_earnings_history",
    "get_insider_transactions",
    "get_institutional_holdings",
    "get_sector_performance",
    "screen_stocks",
    "get_market_breadth",
    "get_analyst_upgrades",
    "calculate_dcf",
    "compare_stocks",
    "get_economic_indicators",
    "get_crypto_data",
    "get_portfolio_summary",
    "calculate_retirement",
}


# ── default_tools() factory ───────────────────────────────────────────────────

def test_default_tools_returns_expected_count():
    assert len(default_tools()) == len(EXPECTED_TOOL_NAMES)


def test_default_tools_names_match_expected_set():
    names = {t.name for t in default_tools()}
    assert names == EXPECTED_TOOL_NAMES


def test_default_tools_no_duplicates():
    names = [t.name for t in default_tools()]
    assert len(names) == len(set(names))


def test_default_tools_all_inherit_base():
    for tool in default_tools():
        assert isinstance(tool, BaseTool)


# ── Per-tool contract ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_tool_has_non_empty_name(ToolClass):
    tool = ToolClass()
    assert isinstance(tool.name, str) and len(tool.name) > 0


@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_tool_has_non_empty_description(ToolClass):
    tool = ToolClass()
    assert isinstance(tool.description, str) and len(tool.description) > 0


@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_tool_has_parameters_dict(ToolClass):
    tool = ToolClass()
    assert isinstance(tool.parameters, dict)


# ── Claude schema structure ───────────────────────────────────────────────────

@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_claude_schema_top_level_keys(ToolClass):
    schema = ToolClass().to_claude_schema()
    assert "name" in schema
    assert "description" in schema
    assert "input_schema" in schema


@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_claude_schema_input_schema_is_object(ToolClass):
    schema = ToolClass().to_claude_schema()
    assert schema["input_schema"]["type"] == "object"


@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_claude_schema_has_properties_key(ToolClass):
    # All tools must have a "properties" dict (may be empty for no-arg tools)
    schema = ToolClass().to_claude_schema()
    assert "properties" in schema["input_schema"]
    assert isinstance(schema["input_schema"]["properties"], dict)


@pytest.mark.parametrize("ToolClass", ALL_TOOL_CLASSES)
def test_claude_schema_required_is_list(ToolClass):
    schema = ToolClass().to_claude_schema()
    required = schema["input_schema"].get("required", [])
    assert isinstance(required, list)


# ── Tool-specific required parameters ────────────────────────────────────────

def test_stock_price_requires_ticker():
    schema = StockPriceTool().to_claude_schema()
    assert "ticker" in schema["input_schema"]["required"]


def test_fundamentals_requires_ticker():
    schema = FundamentalTool().to_claude_schema()
    assert "ticker" in schema["input_schema"]["required"]


def test_technical_analysis_requires_ticker():
    schema = TechnicalAnalysisTool().to_claude_schema()
    assert "ticker" in schema["input_schema"]["required"]


def test_news_requires_ticker():
    schema = StockNewsTool().to_claude_schema()
    assert "ticker" in schema["input_schema"]["required"]


def test_rag_tool_requires_query():
    schema = RAGTool().to_claude_schema()
    assert "query" in schema["input_schema"]["required"]


def test_recall_tool_requires_query():
    schema = RecallAnalysesTool().to_claude_schema()
    assert "query" in schema["input_schema"]["required"]


def test_crypto_tool_requires_symbols():
    schema = CryptoTool().to_claude_schema()
    assert "symbols" in schema["input_schema"]["required"]


def test_retirement_tool_requires_annual_expenses():
    schema = RetirementCalculatorTool().to_claude_schema()
    assert "annual_expenses" in schema["input_schema"]["required"]


def test_portfolio_summary_tool_has_no_required_params():
    schema = PortfolioSummaryTool().to_claude_schema()
    assert schema["input_schema"].get("required", []) == []
