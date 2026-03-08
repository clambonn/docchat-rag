"""
Retrieval — Postgres pgvector (pure vector search)
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
    top_k = top_k or settings.RETRIEVAL_TOP_K
    logger.info(f"DEBUG threshold={settings.RELEVANCE_THRESHOLD} top_k={top_k}")

    embedder = _get_embedder()
    vec = _embed(embedder, [query])[0]
    vec_str = f"[{','.join(map(str, vec))}]"

    pool = await get_pool()
    async with pool.acquire() as conn:
        if doc_id:
            sql = f"""
                SELECT id, content, filename, page,
                       1 - (embedding <=> $1::vector) AS score
                FROM chunks
                WHERE doc_id = $2
                ORDER BY embedding <=> $1::vector
                LIMIT {top_k}
            """
            rows = await conn.fetch(sql, vec_str, doc_id)
        else:
            sql = f"""
                SELECT id, content, filename, page,
                       1 - (embedding <=> $1::vector) AS score
                FROM chunks
                ORDER BY embedding <=> $1::vector
                LIMIT {top_k}
            """
            rows = await conn.fetch(sql, vec_str)

    results = []
    for row in rows:
        score = float(row["score"])
        if score >= settings.RELEVANCE_THRESHOLD:
            results.append({
                "content": row["content"],
                "filename": row["filename"],
                "page": row["page"],
                "score": round(score, 4),
                "source": f"{row['filename']} — Page {row['page']}",
                "excerpt": row["content"][:200] + ("..." if len(row["content"]) > 200 else ""),
            })

    logger.info(f"Retrieved {len(results)} chunks for: '{query[:60]}'")
    return results
