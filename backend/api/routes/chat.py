"""
Chat API — AG-UI Protocol (SSE streaming)
─────────────────────────────────────────
POST /api/chat/run   → Server-Sent Events stream (AG-UI)
POST /api/chat/ask   → JSON (non-streaming fallback)
GET  /api/chat/history
DELETE /api/chat/history
"""

from __future__ import annotations
import uuid, time, asyncio
from typing import Optional, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pipelines.retrieval import retrieve
from utils.config import settings
from utils.logger import logger
import utils.agui_events as ev

router = APIRouter()

# In-process session store
_sessions: dict[str, list[dict]] = {}

SYSTEM_PROMPT = """You are DocChat, a precise document assistant.
Rules:
1. Answer ONLY from the provided excerpts.
2. Cite sources inline as [Source N].
3. If information is absent, say: "I could not find that in the document."
4. Be concise. Use bullet points for multi-part answers.
"""


def _get_llm():
    if settings.LLM_PROVIDER == "openai":
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE or None,
        )
    return None


def _build_messages(history: list[dict], context: str, question: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-(settings.MAX_HISTORY_TURNS * 2):]:
        msgs.append({"role": turn["role"], "content": turn["content"]})
    user_content = f"Document excerpts:\n{context}\n\nQuestion: {question}"
    msgs.append({"role": "user", "content": user_content})
    return msgs


def _format_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[{i}] {c['source']}\n{c['content']}"
        for i, c in enumerate(chunks, 1)
    )


# ── AG-UI Streaming endpoint ──────────────────────────────────────────────────

class RunRequest(BaseModel):
    messages: list[dict]          # AG-UI sends full message history
    threadId: Optional[str] = None
    runId: Optional[str] = None
    doc_id: Optional[str] = None


async def _stream_agui(req: RunRequest) -> AsyncIterator[str]:
    run_id = req.runId or str(uuid.uuid4())
    thread_id = req.threadId or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())

    # Extract last user message
    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        yield ev.run_error(run_id, "No user message found")
        return

    question = user_messages[-1]["content"]
    history = req.messages[:-1]  # everything before the last user message

    yield ev.run_started(run_id, thread_id)
    await asyncio.sleep(0)

    # Retrieve from Postgres
    chunks = await retrieve(question, doc_id=req.doc_id)

    if not chunks:
        yield ev.text_message_start(msg_id)
        yield ev.text_message_content(msg_id, "I could not find relevant information in the document.")
        yield ev.text_message_end(msg_id)
        yield ev.run_finished(run_id)
        return

    # Emit sources as a tool call event (renders as a citation panel in the UI)
    yield ev.tool_call_start(tool_id, "retrieve_sources")
    yield ev.tool_call_end(tool_id, {
        "sources": chunks,
        "query": question,
    })
    await asyncio.sleep(0)

    # Build prompt
    context = _format_context(chunks)
    messages = _build_messages(history, context, question)

    # Stream LLM response
    yield ev.text_message_start(msg_id)

    client = _get_llm()
    full_answer = ""

    try:
        if client:  # OpenAI async streaming
            stream = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                max_tokens=settings.MAX_ANSWER_TOKENS,
                temperature=0.1,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_answer += delta
                    yield ev.text_message_content(msg_id, delta)
                    await asyncio.sleep(0)
        else:
            # Fallback: non-streaming via LangChain
            from pipelines.llm import get_llm as get_lc_llm
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            lc_llm = get_lc_llm()
            lc_msgs = [SystemMessage(content=SYSTEM_PROMPT)]
            for m in history:
                if m["role"] == "user":
                    lc_msgs.append(HumanMessage(content=m["content"]))
                else:
                    lc_msgs.append(AIMessage(content=m["content"]))
            lc_msgs.append(HumanMessage(content=f"Excerpts:\n{context}\n\nQuestion: {question}"))
            resp = lc_llm.invoke(lc_msgs)
            full_answer = resp.content
            # Stream word by word for effect
            for word in full_answer.split(" "):
                yield ev.text_message_content(msg_id, word + " ")
                await asyncio.sleep(0.02)

    except Exception as e:
        logger.error(f"LLM error: {e}")
        yield ev.run_error(run_id, str(e))
        return

    yield ev.text_message_end(msg_id)

    # Update shared state with sources (AG-UI state_snapshot)
    yield ev.state_snapshot({
        "lastSources": chunks,
        "lastQuery": question,
        "threadId": thread_id,
    })

    # Persist session
    _sessions[thread_id] = _sessions.get(thread_id, []) + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": full_answer},
    ]

    yield ev.run_finished(run_id)


@router.post("/run")
async def chat_run(req: RunRequest):
    """AG-UI SSE streaming endpoint."""
    return StreamingResponse(
        _stream_agui(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── JSON fallback ─────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    doc_id: Optional[str] = None


@router.post("/ask")
async def ask(req: AskRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])
    chunks = await retrieve(req.question, doc_id=req.doc_id)

    if not chunks:
        return {"session_id": session_id, "answer": "No relevant content found.", "sources": []}

    context = _format_context(chunks)
    messages = _build_messages(history, context, req.question)

    client = _get_llm()
    if client:
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL, messages=messages,
            max_tokens=settings.MAX_ANSWER_TOKENS, temperature=0.1,
        )
        answer = resp.choices[0].message.content
    else:
        from pipelines.llm import get_llm as get_lc_llm
        from langchain_core.messages import HumanMessage, SystemMessage
        lc = get_lc_llm()
        r = lc.invoke([SystemMessage(content=SYSTEM_PROMPT),
                       HumanMessage(content=f"Excerpts:\n{context}\n\nQuestion: {req.question}")])
        answer = r.content

    _sessions[session_id] = history + [
        {"role": "user", "content": req.question},
        {"role": "assistant", "content": answer},
    ]

    return {"session_id": session_id, "answer": answer, "sources": chunks}


@router.get("/history")
def get_history(session_id: str):
    return {"session_id": session_id, "history": _sessions.get(session_id, [])}


@router.delete("/history")
def clear_history(session_id: str):
    _sessions.pop(session_id, None)
    return {"status": "cleared"}
