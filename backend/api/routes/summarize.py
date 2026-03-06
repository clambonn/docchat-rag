from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from utils.db import get_pool
from utils.config import settings

router = APIRouter()


class SummarizeRequest(BaseModel):
    doc_id: str
    strategy: Optional[str] = "auto"


@router.post("")
async def summarize(req: SummarizeRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT content FROM chunks WHERE doc_id = $1 ORDER BY page, chunk_index LIMIT 40",
            req.doc_id
        )
    if not rows:
        raise HTTPException(404, "Document not found")

    texts = [r["content"] for r in rows]
    total_chars = sum(len(t) for t in texts)
    strategy = req.strategy
    if strategy == "auto":
        strategy = "stuff" if total_chars < 12000 else "map_reduce"

    CHUNK_PROMPT = "Summarise in 3-5 sentences, keeping key terms, dates, parties, obligations:\n\n{text}"
    FINAL_PROMPT = "Combine into an executive summary (150-250 words) covering: purpose, parties, obligations, risks.\n\n{summaries}"

    if settings.LLM_PROVIDER == "openai":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        async def llm(prompt): 
            r = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512, temperature=0.1,
            )
            return r.choices[0].message.content
    else:
        from pipelines.llm import get_llm
        lc = get_llm()
        async def llm(prompt):
            r = lc.invoke(prompt)
            return r.content if hasattr(r, "content") else str(r)

    if strategy == "stuff":
        combined = "\n\n".join(texts)[:14000]
        summary = await llm(CHUNK_PROMPT.format(text=combined))
    else:
        partials = []
        for t in texts[:20]:
            p = await llm(CHUNK_PROMPT.format(text=t[:3000]))
            partials.append(p)
        summary = await llm(FINAL_PROMPT.format(summaries="\n---\n".join(partials)))

    return {"doc_id": req.doc_id, "summary": summary.strip(), "strategy": strategy, "chunks_used": len(texts)}
