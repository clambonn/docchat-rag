"""
Ingestion Pipeline v2 — Postgres native
Parse → Chunk → Embed → INSERT into Postgres (pgvector)
No Chroma, no FAISS. Just Postgres.
"""

from __future__ import annotations
import uuid, time
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from utils.config import settings
from utils.logger import logger
from utils.db import get_pool

# Reuse parser from v1
import sys, os
sys.path.insert(0, os.path.dirname(__file__))


def _get_embedder():
    if settings.EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=settings.OPENAI_EMBEDDING_MODEL,
                                openai_api_key=settings.OPENAI_API_KEY)
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def _embed(embedder, texts: list[str]) -> list[list[float]]:
    if hasattr(embedder, "encode"):          # SentenceTransformer
        return embedder.encode(texts, show_progress_bar=False).tolist()
    return embedder.embed_documents(texts)   # LangChain


def _parse_document(path: str):
    """Thin wrapper — reuses v1 parser."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(path)
            pages = [p.get_text("text").strip() for p in doc if p.get_text("text").strip()]
            doc.close()
        except Exception:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages if (p.extract_text() or "").strip()]
        return pages, "pdf"
    elif ext == ".docx":
        from docx import Document
        doc = Document(path)
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        pages = ["\n".join(paras[i:i+40]) for i in range(0, len(paras), 40)]
        return pages, "docx"
    raise ValueError(f"Unsupported file type: {ext}")


async def ingest_file(file_path: str) -> dict[str, Any]:
    start = time.perf_counter()
    doc_id = str(uuid.uuid4())
    filename = os.path.basename(file_path)
    logger.info(f"Ingesting {filename} → doc_id={doc_id}")

    pages, file_type = _parse_document(file_path)

    # Chunk
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    for page_num, page_text in enumerate(pages, 1):
        for idx, text in enumerate(splitter.split_text(page_text)):
            if text.strip():
                chunks.append((page_num, idx, text))

    chunks = chunks[: settings.MAX_CHUNKS_PER_DOC]
    texts = [c[2] for c in chunks]

    # Embed
    logger.info(f"Embedding {len(texts)} chunks...")
    embedder = _get_embedder()
    vectors = _embed(embedder, texts)

    # Insert into Postgres
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO documents (doc_id, filename, file_type, page_count, chunk_count)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (doc_id) DO NOTHING
            """, doc_id, filename, file_type, len(pages), len(chunks))

            # Batch insert chunks
            rows = [
                (doc_id, filename, page_num, chunk_idx, text, f"[{','.join(map(str, vec))}]")
                for (page_num, chunk_idx, text), vec in zip(chunks, vectors)
            ]
            await conn.executemany("""
                INSERT INTO chunks (doc_id, filename, page, chunk_index, content, embedding)
                VALUES ($1, $2, $3, $4, $5, $6::vector)
            """, rows)

    elapsed = round(time.perf_counter() - start, 2)
    logger.info(f"Done: {len(chunks)} chunks in {elapsed}s")
    return {"doc_id": doc_id, "filename": filename, "file_type": file_type,
            "page_count": len(pages), "chunk_count": len(chunks), "elapsed_seconds": elapsed}
