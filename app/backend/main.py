"""
OSS RAG Stack — FastAPI application entrypoint
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from core.config import settings
from core.database import init_db
from core.embedder import embedder
from core.vector_store import vector_store
from routers import chat, documents, health, sessions

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup.begin", env=settings.APP_ENV)

    await init_db()
    log.info("startup.database_ready")

    await embedder.warm_up()
    log.info("startup.embedder_ready", model=settings.EMBEDDING_MODEL)

    await vector_store.ensure_collection()
    log.info("startup.vector_store_ready", collection=settings.QDRANT_COLLECTION)

    from agents.episodic_memory import episodic_memory

    await episodic_memory.ensure_collection()
    log.info("startup.episodic_memory_ready")

    if settings.USE_RERANKING:
        from core.reranker import reranker

        await reranker.warm_up()
        log.info("startup.reranker_ready", model=settings.RERANKER_MODEL)

    log.info("startup.complete")
    yield

    log.info("shutdown.begin")
    await embedder.close()
    await vector_store.close()
    if settings.USE_RERANKING:
        from core.reranker import reranker

        await reranker.close()
    log.info("shutdown.complete")


app = FastAPI(
    title="OSS RAG API",
    description="Cloud-agnostic RAG stack powered by Claude + Qdrant",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
