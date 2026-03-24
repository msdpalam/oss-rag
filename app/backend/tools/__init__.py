from tools.base import BaseTool
from tools.news_tool import StockNewsTool
from tools.rag_tool import RAGTool
from tools.recall_tool import RecallAnalysesTool
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
]


def default_tools() -> list[BaseTool]:
    """Return the default tool set for the current domain."""
    return [
        RecallAnalysesTool(),
        RAGTool(),
        StockPriceTool(),
        FundamentalTool(),
        TechnicalAnalysisTool(),
        StockNewsTool(),
    ]
