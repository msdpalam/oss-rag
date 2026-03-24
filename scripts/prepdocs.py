#!/usr/bin/env python3
"""
prepdocs.py — Bulk document ingestion script.

Usage:
    python scripts/prepdocs.py --data-dir ./data
    python scripts/prepdocs.py --data-dir ./data --pattern "*.pdf"
    python scripts/prepdocs.py --data-dir ./data --reset
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "backend"))

import structlog
from dotenv import load_dotenv

load_dotenv()

log = structlog.get_logger()

SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


async def reset_collection() -> None:
    from core.vector_store import vector_store
    from qdrant_client.http.exceptions import UnexpectedResponse
    from core.config import settings

    try:
        await vector_store.client.delete_collection(settings.QDRANT_COLLECTION)
    except UnexpectedResponse:
        pass
    await vector_store.ensure_collection()
    log.info("reset.collection_recreated")


async def ingest_file(path: Path, dry_run: bool = False) -> bool:
    from utils.ingestion import ingest_document
    import uuid

    ext = path.suffix.lower()
    content_type = SUPPORTED_EXTENSIONS.get(ext)
    if not content_type:
        log.warning("prepdocs.unsupported", file=str(path))
        return False

    log.info("prepdocs.processing", file=path.name, size_kb=path.stat().st_size // 1024)

    if dry_run:
        return True

    content = path.read_bytes()
    doc_id = str(uuid.uuid4())

    try:
        await ingest_document(
            doc_id=doc_id,
            s3_key=f"prepdocs/{path.name}",
            content=content,
            content_type=content_type,
            original_name=path.name,
        )
        return True
    except Exception as e:
        log.error("prepdocs.failed", file=path.name, error=str(e))
        return False


async def main(args: argparse.Namespace) -> None:
    from core.embedder import embedder
    from core.vector_store import vector_store

    await embedder.warm_up()
    await vector_store.ensure_collection()

    if args.reset:
        confirm = input("Reset will DELETE all indexed documents. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            return
        await reset_collection()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        log.error("prepdocs.dir_not_found", path=str(data_dir))
        sys.exit(1)

    pattern = args.pattern or "*"
    files = sorted([
        f for f in data_dir.rglob(pattern)
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ])

    if not files:
        log.warning("prepdocs.no_files_found", dir=str(data_dir), pattern=pattern)
        return

    log.info("prepdocs.start", files=len(files), dry_run=args.dry_run)

    results = {"ok": 0, "failed": 0}
    for i, path in enumerate(files, 1):
        log.info(f"[{i}/{len(files)}] {path.name}")
        ok = await ingest_file(path, dry_run=args.dry_run)
        results["ok" if ok else "failed"] += 1

    log.info("prepdocs.done", **results)
    await embedder.close()
    await vector_store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk document ingestion for OSS RAG")
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--pattern", default="*")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args()))
