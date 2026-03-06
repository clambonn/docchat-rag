"""
Hybrid Retrieval — Postgres native
────────────────────────────────────
One SQL query combining:
  1. pgvector  — HNSW cosine similarity (semantic)
  2. pg_textsearch — BM25 ranking (keyword)
  3. Reciprocal Rank Fusion — merge results

No external vector DB. No sync jobs. Just Postgres.
"""

from __future__ import annotations
from utils.config import settings
from utils.logger import logger
from utils.db import get_pool
from pipelines.ingestion import _get_embedder, _embed


async def retrieve(
    query: str,
    doc_id: str | None = None,
    top_k: int | None = None,
) -> list[dict]:
    """
    Hybrid search: vector + BM25 via Reciprocal Rank Fusion.
    Returns list of {content, filename, page, score}.
    """
    top_k = top_k or settings.RETRIEVAL_TOP_K

    # Embed query
    embedder = _get_embedder()
    vec = _embed(embedder, [query])[0]
    vec_str = f"[{','.join(map(str, vec))}]"

    doc_filter = "AND doc_id = $3" if doc_id else ""
    params_base = [vec_str, query]
    if doc_id:
        params_base.append(doc_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Hybrid: vector + BM25 with RRF
        sql = f"""
        WITH vector_ranked AS (
            SELECT id, content, filename, page,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vrank
            FROM chunks
            WHERE 1=1 {doc_filter}
            ORDER BY embedding <=> $1::vector
            LIMIT {top_k * 3}
        ),
        bm25_ranked AS (
            SELECT id, content, filename, page,
                   ROW_NUMBER() OVER (ORDER BY -(content <@> $2)) AS brank
            FROM chunks
            WHERE content @@ plainto_tsquery('english', $2)
            {doc_filter}
            LIMIT {top_k * 3}
        ),
        rrf AS (
            SELECT
                COALESCE(v.id, b.id) AS id,
                COALESCE(v.content, b.content) AS content,
                COALESCE(v.filename, b.filename) AS filename,
                COALESCE(v.page, b.page) AS page,
                (1.0 / (60 + COALESCE(v.vrank, 1000))) * {settings.HYBRID_ALPHA}
                + (1.0 / (60 + COALESCE(b.brank, 1000))) * {1 - settings.HYBRID_ALPHA}
                AS score
            FROM vector_ranked v
            FULL OUTER JOIN bm25_ranked b ON v.id = b.id
        )
        SELECT id, content, filename, page, score
        FROM rrf
        ORDER BY score DESC
        LIMIT {top_k}
        """
        rows = await conn.fetch(sql, *params_base)

    results = []
    for row in rows:
        if row["score"] >= settings.RELEVANCE_THRESHOLD:
            results.append({
                "content": row["content"],
                "filename": row["filename"],
                "page": row["page"],
                "score": round(float(row["score"]), 4),
                "source": f"{row['filename']} — Page {row['page']}",
                "excerpt": row["content"][:200] + ("..." if len(row["content"]) > 200 else ""),
            })

    logger.info(f"Retrieved {len(results)} chunks for: '{query[:60]}'")
    return results
