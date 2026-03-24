"""
Agent memory — two layers:

  WorkingMemory  — per-request scratchpad: tool calls, results, RAG chunks.
                   Lives only for the duration of one agentic run.

  (Future) EpisodicMemory — persisted past analyses stored in PostgreSQL +
                            vector store for cross-session recall.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.vector_store import RetrievedChunk


@dataclass
class ToolCallRecord:
    step: int
    tool_name: str
    tool_input: Dict[str, Any]
    result_snippet: str  # first 300 chars for logging / summary
    result_full: str  # complete result passed back to Claude


@dataclass
class WorkingMemory:
    """
    Scratch-pad for a single agentic run.
    Tracks every tool call and aggregates RAG chunks for citation.
    """

    session_id: str
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    rag_chunks: List[RetrievedChunk] = field(default_factory=list)

    def record(
        self,
        step: int,
        tool_name: str,
        tool_input: Dict[str, Any],
        result: str,
    ) -> None:
        self.tool_calls.append(
            ToolCallRecord(
                step=step,
                tool_name=tool_name,
                tool_input=tool_input,
                result_snippet=result[:300],
                result_full=result,
            )
        )

    def record_rag(self, chunks: List[RetrievedChunk]) -> None:
        """Deduplicate and accumulate RAG chunks across multiple search_documents calls."""
        seen_ids = {c.id for c in self.rag_chunks}
        for chunk in chunks:
            if chunk.id not in seen_ids:
                self.rag_chunks.append(chunk)
                seen_ids.add(chunk.id)

    def tool_summary(self) -> str:
        """Human-readable summary of the execution trace (for debugging / logging)."""
        if not self.tool_calls:
            return "No tools called."
        lines = [
            f"Step {r.step}: {r.tool_name}({r.tool_input}) → {r.result_snippet}…"
            for r in self.tool_calls
        ]
        return "\n".join(lines)

    @property
    def steps_taken(self) -> int:
        return len(self.tool_calls)
