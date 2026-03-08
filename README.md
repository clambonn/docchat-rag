# DocChat RAG v2

> Same RAG pipeline. No more 7 databases. Just Postgres.
> AG-UI streaming protocol for real-time agent interaction.


## Why Postgres for everything

From the TigerData blog: instead of managing Pinecone + Elasticsearch + Postgres separately,
we use one database with extensions:

```sql
CREATE EXTENSION vector;        -- pgvector: HNSW cosine search
CREATE EXTENSION pg_textsearch; -- BM25: same algorithm as Elasticsearch
```

One backup. One monitoring dashboard. One connection string.
AI agents can fork your entire state with a single `pg_dump`.

## Why AG-UI

AG-UI is an open event-based protocol connecting agent backends to frontends.
Instead of REST polling, we stream AG-UI events:

```
RUN_STARTED → TOOL_CALL_START (sources) → TOOL_CALL_END →
TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT × N → TEXT_MESSAGE_END →
STATE_SNAPSHOT → RUN_FINISHED
```

This lets the UI render sources and streamed tokens in real time,
with full conversation state sync between agent and frontend.

## Quick Start

### 1. Postgres with pgvector

```bash

docker run -d -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg17


```

### 2. Backend

```bash
cd docchat-v2
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  
cd backend && uvicorn main:app --reload
```

### 3. Frontend

```bash
cd docchat-v2/frontend
npm install
npm run dev  
```

## Architecture

```
React (AG-UI client)
  └── POST /api/chat/run → SSE stream
        ├── RUN_STARTED
        ├── TOOL_CALL_END { sources: [...] }     ← from Postgres hybrid search
        ├── TEXT_MESSAGE_CONTENT × N             ← OpenAI token stream
        ├── STATE_SNAPSHOT { lastSources, ... }  ← shared state
        └── RUN_FINISHED

Postgres
  ├── chunks(embedding vector(384))     ← pgvector HNSW index
  ├── chunks(content text)              ← pg_textsearch BM25 index
  └── Hybrid RRF query: one SQL, one result
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health + Postgres version |
| `POST /api/ingest/upload` | Upload PDF/DOCX |
| `GET /api/ingest/list` | List documents |
| `DELETE /api/ingest/{doc_id}` | Delete document + chunks |
| `POST /api/chat/run` | **AG-UI SSE stream** |
| `POST /api/chat/ask` | JSON fallback |
| `POST /api/summarize` | Summarize document |
