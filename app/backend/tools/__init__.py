from tools.base import BaseTool
from tools.crypto_tool import CryptoTool
from tools.market_tools import (
    AnalystUpgradesTool,
    CompareStocksTool,
    DCFValuationTool,
    EarningsHistoryTool,
    EconomicIndicatorsTool,
    InsiderTransactionsTool,
    InstitutionalHoldingsTool,
    MarketBreadthTool,
    OptionsChainTool,
    SectorPerformanceTool,
    StockScreenerTool,
)
from tools.news_tool import StockNewsTool
from tools.portfolio_tool import PortfolioSummaryTool
from tools.rag_tool import RAGTool
from tools.recall_tool import RecallAnalysesTool
from tools.retirement_tool import RetirementCalculatorTool
from tools.stock_data import FundamentalTool, StockPriceTool
from tools.technical import TechnicalAnalysisTool

__all__ = [
    "BaseTool",
    "RAGTool",
    "StockPriceTool",
    "FundamentalTool",
    "TechnicalAnalysisTool",
    "StockNewsTool",
    "RecallAnalysesTool",
    "OptionsChainTool",
    "EarningsHistoryTool",
    "InsiderTransactionsTool",
    "InstitutionalHoldingsTool",
    "SectorPerformanceTool",
    "StockScreenerTool",
    "MarketBreadthTool",
    "AnalystUpgradesTool",
    "DCFValuationTool",
    "CompareStocksTool",
    "EconomicIndicatorsTool",
    "CryptoTool",
    "PortfolioSummaryTool",
    "RetirementCalculatorTool",
]


def default_tools() -> list[BaseTool]:
    """Return the full tool set (20 tools). Used by 'auto' agent."""
    return [
        RecallAnalysesTool(),
        RAGTool(),
        StockPriceTool(),
        FundamentalTool(),
        TechnicalAnalysisTool(),
        StockNewsTool(),
        OptionsChainTool(),
        EarningsHistoryTool(),
        InsiderTransactionsTool(),
        InstitutionalHoldingsTool(),
        SectorPerformanceTool(),
        StockScreenerTool(),
        MarketBreadthTool(),
        AnalystUpgradesTool(),
        DCFValuationTool(),
        CompareStocksTool(),
        EconomicIndicatorsTool(),
        CryptoTool(),
        PortfolioSummaryTool(),
        RetirementCalculatorTool(),
    ]
