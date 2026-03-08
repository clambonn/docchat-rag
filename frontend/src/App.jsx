import { useState, useRef, useEffect, useCallback } from "react";

const API = "http://localhost:8000/api";

// ── AG-UI SSE client ──────────────────────────────────────────────────────────
async function* streamAgUI(messages, docId, threadId) {
  const body = JSON.stringify({
    messages,
    threadId,
    runId: crypto.randomUUID(),
    doc_id: docId,
  });

  const res = await fetch(`${API}/chat/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n\n");
    buf = lines.pop();
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try { yield JSON.parse(line.slice(6)); } catch {}
      }
    }
  }
}

// ── Upload helper ─────────────────────────────────────────────────────────────
async function uploadFile(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/ingest/upload`, { method: "POST", body: form });
  return res.json();
}

async function listDocs() {
  const res = await fetch(`${API}/ingest/list`);
  return (await res.json()).documents || [];
}

async function deleteDoc(docId) {
  await fetch(`${API}/ingest/${docId}`, { method: "DELETE" });
}

async function summarizeDoc(docId, strategy = "auto") {
  const res = await fetch(`${API}/summarize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, strategy }),
  });
  return res.json();
}

// ── Icons ─────────────────────────────────────────────────────────────────────
const Ico = {
  upload: "⬆",
  chat: "◈",
  doc: "◻",
  trash: "⌫",
  send: "→",
  spark: "✦",
  pg: "🐘",
  check: "✓",
  spin: "◌",
  cite: "❝",
  sum: "≡",
};

// ── Main App ──────────────────────────────────────────────────────────────────
export default function DocChatV2() {
  const [tab, setTab] = useState("chat");
  const [docs, setDocs] = useState([]);
  const [activeDocId, setActiveDocId] = useState(null);
  const [activeDocName, setActiveDocName] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sources, setSources] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);
  const [threadId] = useState(crypto.randomUUID());
  const bottomRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    listDocs().then(setDocs);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadStatus(null);
    try {
      const res = await uploadFile(file);
      if (res.doc_id) {
        setUploadStatus({ ok: true, msg: `✓ Ingested ${res.chunk_count} chunks in ${res.elapsed_seconds}s`, doc: res });
        setActiveDocId(res.doc_id);
        setActiveDocName(res.filename);
        const fresh = await listDocs();
        setDocs(fresh);
      } else {
        setUploadStatus({ ok: false, msg: res.detail || "Upload failed" });
      }
    } catch (err) {
      setUploadStatus({ ok: false, msg: String(err) });
    } finally {
      setUploading(false);
    }
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming) return;
    const question = input.trim();
    setInput("");
    setStreaming(true);
    setSources([]);

    const userMsg = { role: "user", content: question, id: crypto.randomUUID() };
    setMessages(prev => [...prev, userMsg]);

    const assistantId = crypto.randomUUID();
    setMessages(prev => [...prev, { role: "assistant", content: "", id: assistantId, streaming: true }]);

    try {
      const allMessages = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }));
      for await (const event of streamAgUI(allMessages, activeDocId, threadId)) {
        if (event.type === "TEXT_MESSAGE_CONTENT") {
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, content: m.content + event.delta } : m
          ));
        } else if (event.type === "TOOL_CALL_END" && event.result?.sources) {
          setSources(event.result.sources);
        } else if (event.type === "RUN_FINISHED") {
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, streaming: false } : m
          ));
        } else if (event.type === "RUN_ERROR") {
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, content: `Error: ${event.message}`, streaming: false } : m
          ));
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, content: `Connection error: ${err}`, streaming: false } : m
      ));
    } finally {
      setStreaming(false);
    }
  }, [input, streaming, messages, activeDocId, threadId]);

  const handleSummarize = async (strategy) => {
    if (!activeDocId) return;
    setSummarizing(true);
    setSummary(null);
    try {
      const res = await summarizeDoc(activeDocId, strategy);
      setSummary(res);
    } catch (e) {
      setSummary({ summary: `Error: ${e}` });
    } finally {
      setSummarizing(false);
    }
  };

  const handleDeleteDoc = async (docId) => {
    await deleteDoc(docId);
    if (activeDocId === docId) { setActiveDocId(null); setActiveDocName(null); }
    setDocs(docs.filter(d => d.doc_id !== docId));
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={S.root}>
      {/* Sidebar */}
      <aside style={S.sidebar}>
        <div style={S.logo}>
          <span style={S.logoIcon}>{Ico.pg}</span>
          <span style={S.logoText}>DocChat</span>
        </div>

        <div style={S.sideSection}>
          <div style={S.sideLabel}>NAVIGATION</div>
          {["chat", "upload", "summarize"].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ ...S.navBtn, ...(tab === t ? S.navBtnActive : {}) }}>
              <span>{t === "chat" ? Ico.chat : t === "upload" ? Ico.upload : Ico.sum}</span>
              <span style={{ textTransform: "capitalize" }}>{t}</span>
            </button>
          ))}
        </div>

        <div style={S.sideSection}>
          <div style={S.sideLabel}>DOCUMENTS ({docs.length})</div>
          {docs.length === 0 && <div style={S.emptyDocs}>No documents yet</div>}
          {docs.map(doc => (
            <div key={doc.doc_id} style={{ ...S.docItem, ...(activeDocId === doc.doc_id ? S.docItemActive : {}) }}
              onClick={() => { setActiveDocId(doc.doc_id); setActiveDocName(doc.filename); setTab("chat"); }}>
              <span style={S.docIcon}>{Ico.doc}</span>
              <span style={S.docName}>{doc.filename.length > 18 ? doc.filename.slice(0, 15) + "…" : doc.filename}</span>
              <button style={S.docDel} onClick={e => { e.stopPropagation(); handleDeleteDoc(doc.doc_id); }}>{Ico.trash}</button>
            </div>
          ))}
        </div>

        <div style={S.pgBadge}>
          <span style={{ opacity: 0.5, fontSize: 10 }}>Powered by</span>
          <span style={{ fontWeight: 700, fontSize: 11 }}>{Ico.pg} PostgreSQL</span>
          <span style={{ opacity: 0.4, fontSize: 9 }}>pgvector · pg_textsearch</span>
        </div>
      </aside>

      {/* Main panel */}
      <main style={S.main}>
        {/* Header */}
        <header style={S.header}>
          <div style={S.headerLeft}>
            <span style={S.headerTitle}>
              {tab === "chat" ? "Chat" : tab === "upload" ? "Upload Document" : "Summarize"}
            </span>
            {activeDocName && (
              <span style={S.headerDoc}>{Ico.doc} {activeDocName}</span>
            )}
          </div>
          <div style={S.headerRight}>
            <span style={S.agUiBadge}>AG-UI {Ico.spark}</span>
            {streaming && <span style={S.streamingBadge}>● streaming</span>}
          </div>
        </header>

        {/* ── Tab: Chat ────────────────────────────────────────────────── */}
        {tab === "chat" && (
          <div style={S.chatLayout}>
            <div style={S.messages}>
              {messages.length === 0 && (
                <div style={S.emptyState}>
                  <div style={S.emptyIcon}>{Ico.chat}</div>
                  <div style={S.emptyTitle}>Start a conversation</div>
                  <div style={S.emptyHint}>Upload a document and ask anything about it</div>
                </div>
              )}
              {messages.map(msg => (
                <div key={msg.id} style={{ ...S.msgRow, ...(msg.role === "user" ? S.msgRowUser : {}) }}>
                  <div style={{ ...S.bubble, ...(msg.role === "user" ? S.bubbleUser : S.bubbleAssistant) }}>
                    {msg.role === "assistant" && !msg.streaming && (
                      <span style={S.roleLabel}>{Ico.spark} DocChat</span>
                    )}
                    <div style={S.msgContent}>
                      {msg.content || (msg.streaming ? <span style={S.cursor}>▊</span> : "")}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Sources panel */}
            {sources.length > 0 && (
              <div style={S.sourcePanel}>
                <div style={S.sourcePanelTitle}>{Ico.cite} Sources ({sources.length})</div>
                {sources.map((s, i) => (
                  <div key={i} style={S.sourceItem}>
                    <span style={S.sourceNum}>[{i + 1}]</span>
                    <div>
                      <div style={S.sourceMeta}>{s.source}</div>
                      <div style={S.sourceExcerpt}>{s.excerpt}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Input */}
            <div style={S.inputRow}>
              {!activeDocId && (
                <div style={S.noDocWarning}>⚠ Upload a document first</div>
              )}
              <div style={S.inputWrap}>
                <textarea
                  style={S.textarea}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder={activeDocId ? "Ask anything about the document… (Enter to send)" : "Select a document to start chatting"}
                  disabled={!activeDocId || streaming}
                  rows={2}
                />
                <button style={{ ...S.sendBtn, ...(streaming || !activeDocId ? S.sendBtnDisabled : {}) }}
                  onClick={handleSend} disabled={!activeDocId || streaming}>
                  {streaming ? Ico.spin : Ico.send}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Tab: Upload ───────────────────────────────────────────────── */}
        {tab === "upload" && (
          <div style={S.uploadPage}>
            <div
              style={{ ...S.dropzone, ...(uploading ? S.dropzoneActive : {}) }}
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) { const inp = fileRef.current; Object.defineProperty(inp, "files", { value: [f], writable: true }); handleUpload({ target: inp }); } }}
            >
              <input ref={fileRef} type="file" accept=".pdf,.docx" style={{ display: "none" }} onChange={handleUpload} />
              <div style={S.dropzoneIcon}>{uploading ? Ico.spin : Ico.upload}</div>
              <div style={S.dropzoneTitle}>{uploading ? "Processing…" : "Drop PDF or DOCX here"}</div>
              <div style={S.dropzoneHint}>or click to browse · Max 50MB</div>
            </div>

            {uploadStatus && (
              <div style={{ ...S.statusBox, ...(uploadStatus.ok ? S.statusOk : S.statusErr) }}>
                {uploadStatus.msg}
                {uploadStatus.ok && uploadStatus.doc && (
                  <div style={S.statusMeta}>
                    Pages: {uploadStatus.doc.page_count} · Chunks: {uploadStatus.doc.chunk_count} · {uploadStatus.doc.elapsed_seconds}s
                  </div>
                )}
              </div>
            )}

            <div style={S.techNote}>
              <span style={S.techNoteTitle}>{Ico.pg} Postgres-native storage</span>
              <span>Chunks stored with pgvector (HNSW) + pg_textsearch (BM25) — no external vector DB needed.</span>
            </div>
          </div>
        )}

        {/* ── Tab: Summarize ────────────────────────────────────────────── */}
        {tab === "summarize" && (
          <div style={S.summarizePage}>
            {!activeDocId ? (
              <div style={S.emptyState}>
                <div style={S.emptyIcon}>{Ico.sum}</div>
                <div style={S.emptyTitle}>No document selected</div>
                <div style={S.emptyHint}>Upload or select a document from the sidebar</div>
              </div>
            ) : (
              <>
                <div style={S.sumHeader}>Summarizing: <strong>{activeDocName}</strong></div>
                <div style={S.strategyRow}>
                  {["auto", "stuff", "map_reduce"].map(s => (
                    <button key={s} style={S.stratBtn} onClick={() => handleSummarize(s)} disabled={summarizing}>
                      {summarizing ? Ico.spin : Ico.spark} {s}
                    </button>
                  ))}
                </div>
                {summarizing && <div style={S.sumLoading}>Generating summary…</div>}
                {summary && (
                  <div style={S.summaryBox}>
                    <div style={S.summaryStrategy}>{summary.strategy} strategy · {summary.chunks_used} chunks</div>
                    <div style={S.summaryText}>{summary.summary}</div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  root: {
    display: "flex", height: "100vh", width: "100%", fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
    background: "#0d0f14", color: "#c8cdd8", overflow: "hidden",
  },
  sidebar: {
    width: 220, background: "#111318", borderRight: "1px solid #1e2230",
    display: "flex", flexDirection: "column", padding: "0 0 16px 0", flexShrink: 0,
  },
  logo: {
    padding: "20px 16px 16px", borderBottom: "1px solid #1e2230",
    display: "flex", alignItems: "baseline", gap: 6,
  },
  logoIcon: { fontSize: 20 },
  logoText: { fontWeight: 700, fontSize: 15, color: "#e2e8f0", letterSpacing: "-0.5px" },
  logoVersion: { fontSize: 10, color: "#3d8bff", fontWeight: 700, background: "#1a2640", padding: "1px 5px", borderRadius: 4 },
  sideSection: { padding: "16px 0 0" },
  sideLabel: { fontSize: 9, letterSpacing: 2, color: "#3d4659", padding: "0 16px 8px", fontWeight: 700 },
  navBtn: {
    display: "flex", alignItems: "center", gap: 10, width: "100%",
    padding: "8px 16px", background: "none", border: "none", color: "#7a8499",
    cursor: "pointer", fontSize: 12, textAlign: "left", letterSpacing: 0.3,
    transition: "all 0.15s",
  },
  navBtnActive: { color: "#3d8bff", background: "#131b2e", borderLeft: "2px solid #3d8bff" },
  docItem: {
    display: "flex", alignItems: "center", gap: 6, padding: "6px 16px",
    cursor: "pointer", fontSize: 11, color: "#5a6478", transition: "all 0.1s",
  },
  docItemActive: { color: "#a0aec0", background: "#151922" },
  docIcon: { fontSize: 10, flexShrink: 0 },
  docName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  docDel: { background: "none", border: "none", color: "#3d4659", cursor: "pointer", fontSize: 12, padding: 0, opacity: 0, transition: "opacity 0.15s" },
  emptyDocs: { padding: "4px 16px", fontSize: 10, color: "#2a3040" },
  pgBadge: {
    marginTop: "auto", padding: "12px 16px", borderTop: "1px solid #1e2230",
    display: "flex", flexDirection: "column", gap: 2, fontSize: 10, color: "#4a5568",
  },

  main: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  header: {
    padding: "0 24px", height: 52, borderBottom: "1px solid #1e2230",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    background: "#0f1117", flexShrink: 0,
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 12 },
  headerTitle: { fontWeight: 700, fontSize: 13, color: "#e2e8f0", letterSpacing: 0.5 },
  headerDoc: { fontSize: 11, color: "#3d4659", background: "#151922", padding: "2px 8px", borderRadius: 4 },
  headerRight: { display: "flex", alignItems: "center", gap: 10 },
  agUiBadge: { fontSize: 10, color: "#3d8bff", background: "#131b2e", padding: "2px 8px", borderRadius: 4, letterSpacing: 1 },
  streamingBadge: { fontSize: 10, color: "#4ade80", animation: "pulse 1s infinite" },

  // Chat
  chatLayout: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  messages: { flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 },
  emptyState: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, opacity: 0.3, paddingTop: 80 },
  emptyIcon: { fontSize: 40 },
  emptyTitle: { fontSize: 16, fontWeight: 700, color: "#e2e8f0" },
  emptyHint: { fontSize: 12 },
  msgRow: { display: "flex" },
  msgRowUser: { justifyContent: "flex-end" },
  bubble: { maxWidth: "72%", padding: "12px 16px", borderRadius: 10, fontSize: 13, lineHeight: 1.6 },
  bubbleUser: { background: "#1a2640", color: "#93c5fd", borderTopRightRadius: 2 },
  bubbleAssistant: { background: "#151922", border: "1px solid #1e2230", color: "#c8cdd8", borderTopLeftRadius: 2 },
  roleLabel: { fontSize: 10, color: "#3d8bff", marginBottom: 6, display: "block", letterSpacing: 1 },
  msgContent: { whiteSpace: "pre-wrap" },
  cursor: { animation: "blink 1s infinite", color: "#3d8bff" },

  sourcePanel: { borderTop: "1px solid #1e2230", padding: "12px 24px", maxHeight: 160, overflowY: "auto", background: "#0d0f14" },
  sourcePanelTitle: { fontSize: 10, color: "#3d8bff", letterSpacing: 1, marginBottom: 8, fontWeight: 700 },
  sourceItem: { display: "flex", gap: 10, marginBottom: 8, padding: "6px 8px", background: "#111318", borderRadius: 6 },
  sourceNum: { color: "#3d8bff", fontWeight: 700, fontSize: 11, flexShrink: 0 },
  sourceMeta: { fontSize: 10, color: "#5a6a8a", marginBottom: 2, fontWeight: 700 },
  sourceExcerpt: { fontSize: 11, color: "#5a6478" },

  inputRow: { padding: "12px 24px 20px", borderTop: "1px solid #1e2230", background: "#0f1117" },
  noDocWarning: { fontSize: 11, color: "#f59e0b", marginBottom: 8, background: "#1a1400", padding: "4px 10px", borderRadius: 6 },
  inputWrap: { display: "flex", gap: 10, alignItems: "flex-end" },
  textarea: {
    flex: 1, background: "#111318", border: "1px solid #1e2230", color: "#c8cdd8",
    borderRadius: 8, padding: "10px 14px", fontSize: 13, fontFamily: "inherit",
    resize: "none", outline: "none", lineHeight: 1.5,
  },
  sendBtn: {
    width: 40, height: 40, background: "#3d8bff", border: "none", borderRadius: 8,
    color: "#fff", fontSize: 18, cursor: "pointer", flexShrink: 0, transition: "all 0.15s",
  },
  sendBtnDisabled: { background: "#1e2230", color: "#3d4659", cursor: "not-allowed" },

  // Upload
  uploadPage: { flex: 1, padding: 32, display: "flex", flexDirection: "column", gap: 20, maxWidth: 600 },
  dropzone: {
    border: "2px dashed #1e2230", borderRadius: 12, padding: "48px 32px",
    display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
    cursor: "pointer", transition: "all 0.2s",
  },
  dropzoneActive: { borderColor: "#3d8bff", background: "#0d1525" },
  dropzoneIcon: { fontSize: 32 },
  dropzoneTitle: { fontSize: 15, fontWeight: 700, color: "#e2e8f0" },
  dropzoneHint: { fontSize: 12, color: "#3d4659" },
  statusBox: { padding: "12px 16px", borderRadius: 8, fontSize: 12 },
  statusOk: { background: "#0d1f0f", border: "1px solid #1a4d1f", color: "#4ade80" },
  statusErr: { background: "#1f0d0d", border: "1px solid #4d1a1a", color: "#f87171" },
  statusMeta: { fontSize: 11, opacity: 0.7, marginTop: 4 },
  techNote: {
    display: "flex", flexDirection: "column", gap: 4, padding: "12px 16px",
    background: "#111318", borderRadius: 8, fontSize: 11, color: "#4a5568",
    border: "1px solid #1e2230",
  },
  techNoteTitle: { fontWeight: 700, color: "#3d8bff", marginBottom: 2 },

  // Summarize
  summarizePage: { flex: 1, padding: 32, display: "flex", flexDirection: "column", gap: 20, maxWidth: 700 },
  sumHeader: { fontSize: 13, color: "#a0aec0" },
  strategyRow: { display: "flex", gap: 10 },
  stratBtn: {
    padding: "8px 20px", background: "#111318", border: "1px solid #1e2230",
    color: "#7a8499", borderRadius: 8, cursor: "pointer", fontSize: 12,
    fontFamily: "inherit", transition: "all 0.15s",
  },
  sumLoading: { fontSize: 12, color: "#3d4659" },
  summaryBox: { background: "#111318", border: "1px solid #1e2230", borderRadius: 10, padding: 20 },
  summaryStrategy: { fontSize: 10, color: "#3d8bff", letterSpacing: 1, marginBottom: 12, fontWeight: 700 },
  summaryText: { fontSize: 13, lineHeight: 1.8, color: "#a0aec0", whiteSpace: "pre-wrap" },
};
