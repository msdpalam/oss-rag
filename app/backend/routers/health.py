"""
Health check endpoints.
GET /health       — liveness (always 200 if process is running)
GET /health/ready — readiness (checks DB + Qdrant)
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.vector_store import vector_store

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    info = await vector_store.get_collection_info()
    return {"status": "ready", "vector_store": info}
