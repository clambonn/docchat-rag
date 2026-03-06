from fastapi import APIRouter
from utils.config import settings
from utils.db import get_pool

router = APIRouter()

@router.get("/health")
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        pg_ver = await conn.fetchval("SELECT version()")
    return {
        "status": "ok",
        "postgres": pg_ver[:40],
        "llm_provider": settings.LLM_PROVIDER,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
    }
