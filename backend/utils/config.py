"""Configuration — v2 uses Postgres for everything."""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # ── Postgres (replaces ChromaDB + FAISS) ─────────────────────────────
    POSTGRES_DSN: str = "postgresql://postgres:postgres@localhost:5432/docchat"

    # ── LLM ──────────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["openai", "ollama", "huggingface"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_API_BASE: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    HF_MODEL_ID: str = "mistralai/Mistral-7B-Instruct-v0.2"

    # ── Embeddings ────────────────────────────────────────────────────────
    EMBEDDING_PROVIDER: Literal["openai", "sentence_transformers"] = "sentence_transformers"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 384          # 384 for MiniLM, 1536 for OpenAI

    # ── Chunking ──────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    MAX_CHUNKS_PER_DOC: int = 500

    # ── Retrieval ─────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K: int = 5
    HYBRID_ALPHA: float = 0.7         # weight for vector vs BM25 in hybrid search
    RELEVANCE_THRESHOLD: float = 0.30

    # ── Guardrails ────────────────────────────────────────────────────────
    ENABLE_GUARDRAILS: bool = True
    MAX_ANSWER_TOKENS: int = 1024

    # ── Files ─────────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx"]

    # ── AG-UI ─────────────────────────────────────────────────────────────
    MAX_HISTORY_TURNS: int = 10

    class Config:
        env_file = ".env"


settings = Settings()

import os
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
