"""
Ingestion pipeline — parse → chunk → embed → index.

Supports:
  - PDF (text + embedded images via PyMuPDF)
  - DOCX, PPTX, XLSX (via Unstructured)
  - HTML, Markdown, plain text
  - Images (PNG, JPEG, WEBP) — caption via Claude vision

Called as a FastAPI BackgroundTask after upload.
Also importable as a standalone script (scripts/prepdocs.py).
"""

import asyncio
import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import pymupdf
import pymupdf4llm
import structlog
from anthropic import AsyncAnthropic
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.config import settings
from core.database import AsyncSessionLocal
from core.embedder import embedder
from core.models import Document, DocumentChunk
from core.vector_store import vector_store

log = structlog.get_logger()

IMAGE_CAPTION_PROMPT = (
    "Describe this image concisely for a search index. "
    "Focus on text content, diagrams, charts, tables, and key visual information. "
    "Be specific and factual. Output only the description, no preamble."
)

MIN_CHUNK_CHARS = 50  # discard heading-only / whitespace-only fragments

TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
    length_function=len,
)


@dataclass
class ParsedChunk:
    content: str
    page_number: Optional[int] = None
    chunk_index: int = 0
    content_type: str = "text"
    image_data: Optional[bytes] = None


# ── Parsers ───────────────────────────────────────────────────────────────────


def _parse_pdf(content: bytes, original_name: str) -> tuple[List[ParsedChunk], int, bool]:
    doc = pymupdf.open(stream=content, filetype="pdf")
    page_count = len(doc)
    has_images = False
    raw_chunks: List[ParsedChunk] = []

    try:
        md_text = pymupdf4llm.to_markdown(doc, show_progress=False)
        pages = md_text.split("\n-----\n")
        for page_idx, page_text in enumerate(pages):
            stripped = page_text.strip()
            if stripped:
                raw_chunks.append(
                    ParsedChunk(
                        content=stripped,
                        page_number=page_idx + 1,
                        content_type="text",
                    )
                )
    except Exception as e:
        log.warning("pdf.markdown_extraction_failed", error=str(e))
        for page in doc:
            text = page.get_text().strip()
            if text:
                raw_chunks.append(
                    ParsedChunk(
                        content=text,
                        page_number=page.number + 1,
                        content_type="text",
                    )
                )

    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                if len(img_bytes) < 5_000:
                    continue
                has_images = True
                raw_chunks.append(
                    ParsedChunk(
                        content="",
                        page_number=page.number + 1,
                        content_type="image_caption",
                        image_data=img_bytes,
                    )
                )
            except Exception:
                pass

    doc.close()
    return raw_chunks, page_count, has_images


def _parse_text(content: bytes, content_type: str) -> List[ParsedChunk]:
    text = content.decode("utf-8", errors="replace")
    return [ParsedChunk(content=text, page_number=1, content_type="text")]


def _parse_office(content: bytes, content_type: str, original_name: str) -> List[ParsedChunk]:
    try:
        import io

        from unstructured.partition.auto import partition

        elements = partition(
            file=io.BytesIO(content),
            content_type=content_type,
            include_metadata=True,
        )
        chunks = []
        for el in elements:
            text = str(el).strip()
            if text:
                page = (
                    getattr(el.metadata, "page_number", None) if hasattr(el, "metadata") else None
                )
                ctype = "table" if el.category == "Table" else "text"
                chunks.append(ParsedChunk(content=text, page_number=page, content_type=ctype))
        return chunks
    except Exception as e:
        log.error("office.parse_failed", error=str(e))
        return [ParsedChunk(content=content.decode("utf-8", errors="replace"), content_type="text")]


def _parse_image_file(content: bytes) -> List[ParsedChunk]:
    return [
        ParsedChunk(content="", page_number=1, content_type="image_caption", image_data=content)
    ]


# ── Image captioning ──────────────────────────────────────────────────────────


async def _caption_images(chunks: List[ParsedChunk]) -> List[ParsedChunk]:
    image_chunks = [c for c in chunks if c.content_type == "image_caption" and c.image_data]
    if not image_chunks:
        return chunks

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    sem = asyncio.Semaphore(3)

    async def caption_one(chunk: ParsedChunk) -> None:
        async with sem:
            try:
                b64 = base64.standard_b64encode(chunk.image_data).decode()
                img_type = "image/png"
                if chunk.image_data[:3] == b"\xff\xd8\xff":
                    img_type = "image/jpeg"
                elif chunk.image_data[:4] == b"RIFF":
                    img_type = "image/webp"

                response = await client.messages.create(
                    model=settings.CLAUDE_MODEL,
                    max_tokens=300,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": img_type,
                                        "data": b64,
                                    },
                                },
                                {"type": "text", "text": IMAGE_CAPTION_PROMPT},
                            ],
                        }
                    ],
                )
                chunk.content = f"[Image] {response.content[0].text.strip()}"
            except Exception as e:
                log.warning("caption.failed", error=str(e))
                chunk.content = "[Image — caption unavailable]"

    await asyncio.gather(*[caption_one(c) for c in image_chunks])
    return chunks


# ── Chunking ──────────────────────────────────────────────────────────────────


def _split_into_chunks(parsed: List[ParsedChunk]) -> List[ParsedChunk]:
    result: List[ParsedChunk] = []
    idx = 0
    for chunk in parsed:
        # Tables: keep whole if small enough; split large ones to avoid embedding truncation.
        # Image captions: always split — they can be 900+ chars and are plain prose.
        if chunk.content_type == "table" and len(chunk.content) <= settings.CHUNK_SIZE * 2:
            if len(chunk.content) >= MIN_CHUNK_CHARS:
                chunk.chunk_index = idx
                result.append(chunk)
                idx += 1
            continue

        sub_texts = TEXT_SPLITTER.split_text(chunk.content)
        for sub in sub_texts:
            cleaned = sub.strip()
            if len(cleaned) >= MIN_CHUNK_CHARS:
                result.append(
                    ParsedChunk(
                        content=cleaned,
                        page_number=chunk.page_number,
                        chunk_index=idx,
                        content_type=chunk.content_type,
                    )
                )
                idx += 1

    return result


# ── Main ingestion entry point ────────────────────────────────────────────────


async def ingest_document(
    doc_id: str,
    s3_key: str,
    content: bytes,
    content_type: str,
    original_name: str,
) -> None:
    log.info("ingestion.start", doc_id=doc_id, filename=original_name, size=len(content))

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        doc = result.scalar_one_or_none()
        if not doc:
            log.error("ingestion.document_not_found", doc_id=doc_id)
            return

        try:
            doc.status = "processing"
            await db.commit()

            page_count = 1
            has_images = False

            if content_type == "application/pdf":
                raw_chunks, page_count, has_images = _parse_pdf(content, original_name)
            elif content_type in ("text/plain", "text/markdown", "text/html"):
                raw_chunks = _parse_text(content, content_type)
            elif content_type in ("image/png", "image/jpeg", "image/webp"):
                raw_chunks = _parse_image_file(content)
                has_images = True
            else:
                raw_chunks = _parse_office(content, content_type, original_name)

            log.info("ingestion.parsed", doc_id=doc_id, raw_chunks=len(raw_chunks))

            if has_images:
                raw_chunks = await _caption_images(raw_chunks)

            chunks = _split_into_chunks(raw_chunks)

            if not chunks:
                raise ValueError("No extractable content found in document")

            texts = [c.content for c in chunks]
            BATCH = settings.EMBEDDING_BATCH_SIZE
            all_vectors = []
            for i in range(0, len(texts), BATCH):
                batch_vecs = await embedder.embed(texts[i : i + BATCH])
                all_vectors.extend(batch_vecs)

            # Compute BM25 sparse vectors for hybrid search (no extra dependencies)
            sparse_vectors = []
            if settings.USE_HYBRID_SEARCH:
                from core.sparse_embedder import bm25_encode

                for text in texts:
                    indices, values = bm25_encode(text)
                    sparse_vectors.append((indices, values))
            else:
                sparse_vectors = [([], [])] * len(texts)

            points = []
            chunk_records = []
            for chunk, vector, (sp_indices, sp_values) in zip(
                chunks, all_vectors, sparse_vectors, strict=False
            ):
                point_id = uuid.uuid4()
                point: dict = {
                    "id": point_id,
                    "dense_vector": vector,
                    "payload": {
                        "document_id": doc_id,
                        "source": original_name,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "content_type": chunk.content_type,
                        "s3_key": s3_key,
                    },
                }
                if sp_indices:
                    point["sparse_indices"] = sp_indices
                    point["sparse_values"] = sp_values
                points.append(point)

                chunk_records.append(
                    DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=uuid.UUID(doc_id),
                        qdrant_point_id=point_id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        content=chunk.content,
                        content_type=chunk.content_type,
                        char_count=len(chunk.content),
                    )
                )

            for i in range(0, len(points), 100):
                await vector_store.upsert(points[i : i + 100])

            db.add_all(chunk_records)

            doc.status = "indexed"
            doc.page_count = page_count
            doc.chunk_count = len(chunks)
            doc.has_images = has_images
            doc.indexed_at = datetime.now(timezone.utc)
            await db.commit()

            log.info(
                "ingestion.complete",
                doc_id=doc_id,
                chunks=len(chunks),
                pages=page_count,
            )

        except Exception as e:
            log.error("ingestion.failed", doc_id=doc_id, error=str(e))
            doc.status = "failed"
            doc.error_message = str(e)
            await db.commit()
            raise
