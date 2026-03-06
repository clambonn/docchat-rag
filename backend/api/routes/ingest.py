"""Ingestion API — v2 stores into Postgres directly."""

import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from utils.config import settings
from utils.db import get_pool
from pipelines.ingestion import ingest_file

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported: {ext}")

    contents = await file.read()
    if len(contents) / (1024 * 1024) > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(413, "File too large")

    save_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        f.write(contents)

    try:
        result = await ingest_file(save_path)
    except Exception as e:
        raise HTTPException(500, str(e))

    return {"status": "success", "message": f"'{file.filename}' ingested.", **result}


@router.get("/list")
async def list_docs():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT doc_id, filename, file_type, page_count, chunk_count, created_at FROM documents ORDER BY created_at DESC"
        )
    return {"documents": [dict(r) for r in rows]}


@router.delete("/{doc_id}")
async def delete_doc(doc_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)
    return {"status": "deleted", "doc_id": doc_id}
