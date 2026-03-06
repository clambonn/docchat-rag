"""
Postgres connection pool + schema bootstrap.
Uses asyncpg for async access. pgvector + pg_textsearch installed as extensions.
"""

from __future__ import annotations
import asyncpg
from functools import lru_cache
from utils.config import settings
from utils.logger import logger

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.POSTGRES_DSN, min_size=2, max_size=10)
    return _pool


async def init_db():
    """Bootstrap Postgres schema on startup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ── Extensions ───────────────────────────────────────────────────
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_textsearch")

        # ── Documents table ───────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id      TEXT PRIMARY KEY,
                filename    TEXT NOT NULL,
                file_type   TEXT NOT NULL,
                page_count  INT,
                chunk_count INT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ── Chunks table with vector + BM25 ──────────────────────────────
        dim = settings.EMBEDDING_DIM
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id          BIGSERIAL PRIMARY KEY,
                doc_id      TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                filename    TEXT NOT NULL,
                page        INT,
                chunk_index INT,
                content     TEXT NOT NULL,
                embedding   vector({dim})
            )
        """)

        # ── Indexes ───────────────────────────────────────────────────────
        # DiskANN-style HNSW index for vector similarity
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_idx
            ON chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)

        # BM25 full-text index via pg_textsearch
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS chunks_bm25_idx
            ON chunks USING bm25(content)
            WITH (text_config = 'english')
        """)

    logger.info("✅ Postgres schema ready (pgvector + pg_textsearch)")
