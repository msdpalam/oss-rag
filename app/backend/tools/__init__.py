from tools.base import BaseTool
from tools.rag_tool import RAGTool
from tools.stock_data import StockPriceTool, FundamentalTool
from tools.technical import TechnicalAnalysisTool
from tools.news_tool import StockNewsTool
from tools.recall_tool import RecallAnalysesTool

__all__ = [
    "BaseTool", "RAGTool", "StockPriceTool", "FundamentalTool",
    "TechnicalAnalysisTool", "StockNewsTool", "RecallAnalysesTool",
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
