"""
BaseTool — abstract contract every tool must implement.

Tools are the atomic capabilities available to the agent orchestrator.
Each tool maps directly to a Claude tool_use schema.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    name: str  # must match Claude tool name exactly
    description: str  # shown to Claude — be specific about when to use it
    parameters: Dict[str, Any]  # JSON Schema for the tool inputs

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Run the tool and return a plain-text result string.
        Errors should be returned as strings (not raised) so the agent can recover.
        """
        ...

    def to_claude_schema(self) -> Dict[str, Any]:
        """Return the dict Claude's tool_use API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
