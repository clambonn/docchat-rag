# DocChat RAG

A document question-answering system built with a RAG (Retrieval-Augmented Generation) pipeline. Upload any PDF or DOCX file and ask questions about it in natural language.

---

## What it does

- Accepts PDF and DOCX documents via a drag-and-drop interface
- Chunks and embeds document content into a vector database
- Retrieves the most relevant passages when you ask a question
- Generates grounded answers using an LLM, with source citations

---

## Tech stack

- **Backend** — FastAPI, asyncpg, pgvector, SentenceTransformers, LangChain
- **Database** — PostgreSQL 17 with pgvector extension
- **LLM** — Groq API (llama-3.1-8b-instant)
- **Frontend** — React + Vite, AG-UI streaming protocol
- **Deployment** — Docker Compose

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A free [Groq API key](https://console.groq.com) (takes 1 minute to get)

---

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/clambonn/docchat-rag.git
cd docchat-rag
```

**2. Add your Groq API key**

Create a file called `.env` in the root folder:

```
OPENAI_API_KEY=your_groq_api_key_here
```

Get a free key from [console.groq.com](https://console.groq.com) → API Keys → Create new key.

**3. Start everything**

```bash
docker compose up --build
```

Wait for all three services to start (about 1–2 minutes the first time).

**4. Open the app**

Go to [http://localhost:5173](http://localhost:5173) in your browser.

---

## How to use

1. Click **Upload Document** and select a PDF or DOCX file
2. Wait for the ingestion to complete (the document will appear in the sidebar)
3. Type a question in the chat box and press Enter
4. The answer will stream in with source citations from the document

---

## Stopping the app

```bash
docker compose down
```

To also delete the stored documents and embeddings:

```bash
docker compose down -v
```

---

## Project structure

```
docchat-rag/
├── backend/
│   ├── main.py
│   ├── api/routes/        # chat, ingest, summarize, health
│   ├── pipelines/         # ingestion, retrieval, llm
│   └── utils/             # config, db, agui events, logger
├── frontend/
│   └── src/
│       └── App.jsx        # React UI with streaming chat
├── backend.Dockerfile
├── frontend.Dockerfile
├── docker-compose.yml
└── requirements.txt
```
