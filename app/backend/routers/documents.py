"""
Documents router — upload, list, delete, and reindex documents.

GET    /documents            — list all documents
POST   /documents            — upload a new document (multipart/form-data)
GET    /documents/{id}       — get document status (for polling)
DELETE /documents/{id}       — delete document + chunks from Qdrant + S3
POST   /documents/{id}/reindex — re-run ingestion pipeline
"""

import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from core.models import Document
from core.storage import storage

router = APIRouter()
log = structlog.get_logger()

ANON_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
    "image/webp",
}


# ── Response schema ───────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    content_type: Optional[str]
    size_bytes: Optional[int]
    status: str
    error_message: Optional[str]
    page_count: Optional[int]
    chunk_count: Optional[int]
    has_images: Optional[bool]
    created_at: str
    updated_at: str
    indexed_at: Optional[str]
    title: Optional[str]

    @classmethod
    def from_orm(cls, d: Document) -> "DocumentResponse":
        return cls(
            id=str(d.id),
            filename=d.filename,
            original_name=d.original_name,
            content_type=d.content_type,
            size_bytes=d.size_bytes,
            status=d.status,
            error_message=d.error_message,
            page_count=d.page_count,
            chunk_count=d.chunk_count,
            has_images=d.has_images,
            created_at=d.created_at.isoformat(),
            updated_at=d.updated_at.isoformat(),
            indexed_at=d.indexed_at.isoformat() if d.indexed_at else None,
            title=d.title,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=List[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return [DocumentResponse.from_orm(d) for d in result.scalars()]


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, PNG, JPG, WEBP",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    doc_id = uuid.uuid4()
    s3_key = f"uploads/{doc_id}/{file.filename}"

    # Upload raw file to MinIO
    await storage.upload(
        bucket=settings.S3_BUCKET_DOCUMENTS,
        key=s3_key,
        data=content,
        content_type=content_type,
    )

    # Create DB record
    doc = Document(
        id=doc_id,
        filename=file.filename,
        original_name=file.filename,
        content_type=content_type,
        size_bytes=len(content),
        s3_key=s3_key,
        s3_bucket=settings.S3_BUCKET_DOCUMENTS,
        status="uploaded",
        uploaded_by=ANON_USER_ID,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    log.info(
        "document.uploaded",
        doc_id=str(doc_id),
        filename=file.filename,
        size=len(content),
    )

    # Kick off background ingestion
    from utils.ingestion import ingest_document

    background_tasks.add_task(
        ingest_document,
        doc_id=str(doc_id),
        s3_key=s3_key,
        content=content,
        content_type=content_type,
        original_name=file.filename,
    )

    return DocumentResponse.from_orm(doc)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    result = await db.execute(select(Document).where(Document.id == did))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.from_orm(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    result = await db.execute(select(Document).where(Document.id == did))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove vectors from Qdrant
    from core.vector_store import vector_store

    await vector_store.delete_by_document_id(doc_id)

    # Remove file from MinIO
    try:
        await storage.delete(bucket=doc.s3_bucket, key=doc.s3_key)
    except Exception as e:
        log.warning("storage.delete_failed", doc_id=doc_id, error=str(e))

    # Delete DB record (cascades to document_chunks)
    await db.delete(doc)
    await db.commit()
    log.info("document.deleted", doc_id=doc_id)


@router.post("/{doc_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    result = await db.execute(select(Document).where(Document.id == did))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete existing vectors
    from core.vector_store import vector_store

    await vector_store.delete_by_document_id(doc_id)

    # Reset status
    doc.status = "uploaded"
    doc.error_message = None
    await db.commit()
    await db.refresh(doc)

    # Download content from MinIO and re-ingest
    content = await storage.download(bucket=doc.s3_bucket, key=doc.s3_key)

    from utils.ingestion import ingest_document

    background_tasks.add_task(
        ingest_document,
        doc_id=doc_id,
        s3_key=doc.s3_key,
        content=content,
        content_type=doc.content_type or "application/octet-stream",
        original_name=doc.original_name,
    )

    log.info("document.reindex_queued", doc_id=doc_id)
    return DocumentResponse.from_orm(doc)
