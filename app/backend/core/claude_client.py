"""
Claude API client — wraps the Anthropic SDK.
Provides both streaming and non-streaming completions.
"""

from typing import AsyncIterator, List, Optional

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from core.config import settings
from core.vector_store import RetrievedChunk

log = structlog.get_logger()

# ── System prompts ────────────────────────────────────────────────────────────

# strict_rag: answers grounded solely in the indexed documents
STRICT_RAG_PROMPT = """You are a helpful assistant that answers questions based on the provided document excerpts.

Guidelines:
- Answer questions using ONLY the information in the provided excerpts.
- If the excerpts don't contain enough information to answer, say so clearly.
- Always cite your sources by referencing the document name and page number when available.
- Format citations as [Source: filename, page N].
- Be concise and accurate.
- If asked about topics not covered in the documents, say you don't have that information.
- For tables or structured data, preserve the structure in your answer.
"""

# expert_context: full LLM knowledge + documents as grounding context
EXPERT_CONTEXT_PROMPT = """You are a knowledgeable expert assistant. You have broad general knowledge and can help with analysis, code, explanations, and reasoning across any domain.

When document excerpts are provided:
- Treat them as the specific data context for this conversation — ground your answer in them.
- Cite specific figures, findings, or terminology from the documents as [Source: filename, page N].
- Combine the document content with your broader knowledge to give complete, insightful answers.

When no relevant excerpts are found for the question:
- Answer from your general knowledge.
- Clearly state when you are answering from general knowledge rather than the provided documents.

Always be precise, provide working code examples when relevant, and preserve table structure.
"""

SYSTEM_PROMPTS = {
    "strict_rag": STRICT_RAG_PROMPT,
    "expert_context": EXPERT_CONTEXT_PROMPT,
}

# Legacy alias so existing references still work
RAG_SYSTEM_PROMPT = STRICT_RAG_PROMPT

QUERY_REWRITE_PROMPT = """Given the conversation history and the user's latest message, generate an optimized search query to retrieve relevant document chunks.

Output ONLY the search query, nothing else. No explanation, no quotes.

Rules:
- Extract the key entities and concepts
- Rephrase as a declarative statement, not a question
- Keep it under 20 words
- Include domain-specific terms if present"""


class ClaudeClient:
    def __init__(self) -> None:
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ── Low-level primitives used by the agent orchestrator ───────────────────

    async def create(
        self,
        messages: List[MessageParam],
        system: str,
        tools: Optional[List[dict]] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Raw non-streaming create — supports tool_use.
        Used by the agent loop for tool-call rounds.
        """
        kwargs = {
            "model": settings.CLAUDE_MODEL,
            "max_tokens": max_tokens or settings.CLAUDE_MAX_TOKENS,
            "temperature": settings.CLAUDE_TEMPERATURE,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "auto"}
        return await self._client.messages.create(**kwargs)

    async def stream_messages(
        self,
        messages: List[MessageParam],
        system: str,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Streaming text-only call (no tools) — used for the final answer.
        Yields raw token strings.
        """
        async with self._client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=max_tokens or settings.CLAUDE_MAX_TOKENS,
            temperature=settings.CLAUDE_TEMPERATURE,
            system=system,
            messages=messages,
        ) as stream:
            async for token in stream.text_stream:
                yield token

    async def rewrite_query(
        self,
        user_message: str,
        conversation_history: Optional[List[MessageParam]] = None,
    ) -> str:
        """
        Use Claude to rewrite the user's question into an optimised search query.
        This mirrors the Azure demo's 'get_search_query' approach.
        """
        messages: List[MessageParam] = []

        if conversation_history:
            # Include last 4 turns for context
            messages.extend(conversation_history[-4:])

        messages.append({"role": "user", "content": f"User message: {user_message}"})

        response = await self._client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=100,
            temperature=0.0,
            system=QUERY_REWRITE_PROMPT,
            messages=messages,
        )
        query = response.content[0].text.strip()
        log.debug("claude.query_rewritten", original=user_message[:80], rewritten=query)
        return query

    async def stream_answer(
        self,
        user_message: str,
        retrieved_chunks: List[RetrievedChunk],
        conversation_history: Optional[List[MessageParam]] = None,
        mode: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a RAG answer from Claude, token by token.
        Yields raw text delta strings for SSE.
        """
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            page_info = f", page {chunk.page}" if chunk.page else ""
            context_parts.append(f"[Excerpt {i} — {chunk.source}{page_info}]\n{chunk.content}")
        context_block = (
            "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documents found."
        )

        messages: List[MessageParam] = list(conversation_history or [])
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Document excerpts:\n\n{context_block}\n\n---\n\nQuestion: {user_message}"
                ),
            }
        )

        log.debug(
            "claude.streaming",
            model=settings.CLAUDE_MODEL,
            chunks=len(retrieved_chunks),
            history_turns=len(conversation_history or []),
        )

        system_prompt = SYSTEM_PROMPTS.get(mode or settings.CHAT_MODE, STRICT_RAG_PROMPT)

        async with self._client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            temperature=settings.CLAUDE_TEMPERATURE,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def answer(
        self,
        user_message: str,
        retrieved_chunks: List[RetrievedChunk],
        conversation_history: Optional[List[MessageParam]] = None,
        mode: Optional[str] = None,
    ) -> tuple[str, dict]:
        """
        Non-streaming answer. Returns (text, usage_dict).
        """
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            page_info = f", page {chunk.page}" if chunk.page else ""
            context_parts.append(f"[Excerpt {i} — {chunk.source}{page_info}]\n{chunk.content}")

        context_block = "\n\n---\n\n".join(context_parts) or "No relevant documents found."

        messages: List[MessageParam] = list(conversation_history or [])
        messages.append(
            {
                "role": "user",
                "content": f"Document excerpts:\n\n{context_block}\n\n---\n\nQuestion: {user_message}",
            }
        )

        system_prompt = SYSTEM_PROMPTS.get(mode or settings.CHAT_MODE, STRICT_RAG_PROMPT)

        response = await self._client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            temperature=settings.CLAUDE_TEMPERATURE,
            system=system_prompt,
            messages=messages,
        )
        text = response.content[0].text
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "model": response.model,
        }
        return text, usage


# Module-level singleton
claude = ClaudeClient()
