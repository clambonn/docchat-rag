"""
DocChat RAG v2 — FastAPI Backend
• Postgres-only: pgvector + pg_textsearch (no Chroma/FAISS)
• AG-UI Protocol: SSE event stream for real-time agent responses
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import ingest, chat, summarize, health
from utils.config import settings
from utils.logger import logger
from utils.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🐘 Initialising Postgres extensions...")
    await init_db()
    logger.info("✅ DocChat RAG v2 ready")
    yield
    logger.info("🛑 Shutting down")


app = FastAPI(
    title="DocChat RAG v2",
    description="Postgres-native RAG with AG-UI streaming protocol",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,     prefix="/api",           tags=["Health"])
app.include_router(ingest.router,     prefix="/api/ingest",    tags=["Ingestion"])
app.include_router(chat.router,       prefix="/api/chat",      tags=["Chat / AG-UI"])
app.include_router(summarize.router,  prefix="/api/summarize", tags=["Summarization"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT,
                reload=settings.DEBUG, log_level="info")
