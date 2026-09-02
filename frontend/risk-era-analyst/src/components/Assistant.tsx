import { useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { useApi } from "../api";
import { useAuth } from "../contexts/AuthContext";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  grounded?: boolean;
  sources?: string[];
};

const SUGGESTED = [
  "What is RISK-ERA?",
  "Explain the analyst workflow.",
  "How does risk investigation work?",
  "What does the audit chain verify?",
  "Explain this case.",
];

export default function Assistant() {
  const location = useLocation();
  const params = useParams();
  const api = useApi();
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = sessionStorage.getItem("risk_era_assistant_history");
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return [];
      }
    }
    return [];
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Persist chat state
  useEffect(() => {
    sessionStorage.setItem("risk_era_assistant_history", JSON.stringify(messages));
  }, [messages]);

  // Auto scroll
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Focus input when open
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  // Derive context from route and params
  const getContext = () => {
    const ctx: Record<string, unknown> = {
      route: location.pathname,
    };
    // Extract IDs from params or URL
    // For /case/:caseId, /customers/:id etc., useParams will have caseId or id
    const anyParams = params as any;
    if (anyParams.caseId) ctx.caseId = anyParams.caseId;
    if (anyParams.id) {
      // Determine type based on route
      if (location.pathname.startsWith("/customers/")) ctx.customerId = anyParams.id;
      else if (location.pathname.startsWith("/merchants/")) ctx.merchantId = anyParams.id;
      else if (location.pathname.startsWith("/devices/")) ctx.deviceId = anyParams.id;
      else if (location.pathname.startsWith("/case/")) ctx.caseId = anyParams.id;
    }
    // Also try to parse from pathname for cases where useParams not available (e.g., nested)
    const parts = location.pathname.split("/");
    if (parts[1] === "case" && parts[2]) ctx.caseId = parts[2];
    if (parts[1] === "customers" && parts[2]) ctx.customerId = parts[2];
    if (parts[1] === "merchants" && parts[2]) ctx.merchantId = parts[2];
    if (parts[1] === "devices" && parts[2]) ctx.deviceId = parts[2];
    // Add extra context if available in DOM? For now, just route
    return ctx;
  };

  const handleSend = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    if (!token) {
      setError("Please log in to use the assistant.");
      return;
    }
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: msg };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const ctx = getContext();
      const res = await (api as any).assistantChat({ message: msg, context: ctx });
      const answer = res.answer || "RISK-ERA Assistant is temporarily unavailable. Please try again.";
      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: answer,
        grounded: !!res.grounded,
        sources: res.sources || [],
      };
      setMessages((m) => [...m, assistantMsg]);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 401) setError("Session expired. Please log in again.");
      else setError("RISK-ERA Assistant is temporarily unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Keyboard handling
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape") setOpen(false);
  };

  return (
    <>
      {/* Floating button */}
      <button
        aria-label={open ? "Close RISK-ERA Assistant" : "Open RISK-ERA Assistant"}
        onClick={() => setOpen((o) => !o)}
        className="assistant-fab"
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          width: 56,
          height: 56,
          borderRadius: "50%",
          background: "var(--accent-primary)",
          color: "#fff",
          border: "1px solid var(--accent-primary)",
          boxShadow: "0 4px 16px rgba(14,116,144,.22), 0 1px 4px rgba(0,0,0,.08)",
          display: "grid",
          placeItems: "center",
          fontSize: "1.4rem",
          cursor: "pointer",
          zIndex: 80,
          transition: "var(--transition)",
        }}
      >
        {open ? "✕" : "◈"}
      </button>

      {/* Panel */}
      {open && (
        <div
          role="dialog"
          aria-label="RISK-ERA Assistant"
          aria-modal="false"
          className="assistant-panel"
          style={{
            position: "fixed",
            bottom: 88,
            right: 24,
            width: 400,
            maxWidth: "calc(100vw - 32px)",
            height: 520,
            maxHeight: "calc(100vh - 120px)",
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 20,
            boxShadow: "0 8px 32px rgba(16,30,60,.12), 0 1px 4px rgba(16,30,60,.06)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            zIndex: 80,
          }}
        >
          {/* Header */}
          <div style={{ padding: "16px 16px 12px 16px", borderBottom: "1px solid var(--border)", background: "var(--bg-card)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: ".95rem", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 28, height: 28, borderRadius: 8, background: "var(--accent-primary)", color: "#fff", display: "grid", placeItems: "center", fontSize: ".9rem" }}>◈</span>
                  RISK-ERA Assistant
                </div>
                <div className="muted" style={{ fontSize: ".7rem", marginTop: 2 }}>Explain risk operations, cases, and investigations</div>
              </div>
              <button aria-label="Close assistant" onClick={() => setOpen(false)} className="btn btn-ghost btn-sm" style={{ borderRadius: 10, width: 32, height: 32, padding: 0, display: "grid", placeItems: "center" }}>
                ✕
              </button>
            </div>
            <div className="muted" style={{ fontSize: ".66rem", marginTop: 6, lineHeight: 1.4 }}>
              Context: <span className="mono">{location.pathname}</span> {getContext().caseId ? `· case ${String(getContext().caseId).slice(0, 8)}…` : ""} {getContext().customerId ? `· customer ${String(getContext().customerId).slice(0, 8)}…` : ""}
            </div>
          </div>

          {/* Messages */}
          <div
            ref={listRef}
            role="log"
            aria-live="polite"
            style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 10, background: "var(--bg-primary)" }}
          >
            {messages.length === 0 && (
              <div className="empty-state" style={{ background: "var(--bg-card)", border: "1px dashed var(--border)", borderRadius: 12, padding: 14 }}>
                <div style={{ fontWeight: 600, fontSize: ".84rem", marginBottom: 6 }}>How can I help?</div>
                <div className="muted" style={{ fontSize: ".74rem", marginBottom: 10 }}>Ask about RISK-ERA, workflow, or the current page. For "Explain this case", open a case first.</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {SUGGESTED.map((q) => (
                    <button key={q} onClick={() => handleSend(q)} className="btn btn-ghost btn-sm" style={{ borderRadius: 20, fontSize: ".72rem", height: 28, padding: "0 10px" }}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  maxWidth: "82%",
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  background: m.role === "user" ? "var(--accent-primary)" : "var(--bg-card)",
                  color: m.role === "user" ? "#fff" : "var(--text-primary)",
                  border: `1px solid ${m.role === "user" ? "var(--accent-primary)" : "var(--border)"}`,
                  borderRadius: m.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                  padding: "10px 12px",
                  fontSize: ".84rem",
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  boxShadow: m.role === "assistant" ? "var(--shadow-card)" : "none",
                }}
              >
                {m.content}
                {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                  <div className="muted" style={{ marginTop: 6, fontSize: ".62rem", borderTop: "1px solid var(--border-light)", paddingTop: 4 }}>
                    {m.grounded ? "Grounded in: " : "Sources: "} {m.sources.join(", ")}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ alignSelf: "flex-start", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "16px 16px 16px 4px", padding: "10px 14px", fontSize: ".82rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 8 }}>
                <span className="skeleton" style={{ width: 16, height: 16, borderRadius: "50%" }} /> Thinking…
              </div>
            )}
            {error && (
              <div className="error-banner" style={{ margin: 0, padding: "8px 10px", fontSize: ".78rem" }}>
                {error}
              </div>
            )}
          </div>

          {/* Input */}
          <div style={{ padding: 12, borderTop: "1px solid var(--border)", background: "var(--bg-card)", display: "flex", gap: 8, alignItems: "center" }}>
            <input
              ref={inputRef}
              aria-label="Ask RISK-ERA Assistant"
              placeholder={token ? "Ask about RISK-ERA…" : "Please log in…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={loading || !token}
              style={{
                flex: 1,
                height: 40,
                borderRadius: 12,
                border: "1px solid var(--border)",
                background: "var(--bg-secondary)",
                padding: "0 12px",
                fontSize: ".84rem",
                outline: "none",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--accent-primary)")}
              onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
            />
            <button
              aria-label="Send message"
              onClick={() => handleSend()}
              disabled={loading || !input.trim() || !token}
              className="btn btn-primary"
              style={{ height: 40, borderRadius: 12, padding: "0 16px", flexShrink: 0 }}
            >
              {loading ? "…" : "Send"}
            </button>
          </div>
          <div className="muted" style={{ padding: "0 12px 10px 12px", fontSize: ".62rem", textAlign: "center" }}>
            {token ? "Assistant uses current page context when available." : "Log in to use the assistant."}
          </div>
        </div>
      )}

      {/* Responsive styles */}
      <style>{`
        @media(max-width:768px){
          .assistant-fab{bottom:16px !important; right:16px !important; width:52px !important; height:52px !important;}
          .assistant-panel{
            bottom:0 !important;
            right:0 !important;
            left:0 !important;
            width:auto !important;
            max-width:none !important;
            height:68vh !important;
            max-height:68vh !important;
            border-radius:16px 16px 0 0 !important;
            margin:0 8px 8px 8px !important;
          }
        }
        @media(max-width:480px){
          .assistant-panel{
            margin:0 !important;
            border-radius:16px 16px 0 0 !important;
            height:72vh !important;
            max-height:72vh !important;
            bottom:0 !important;
          }
        }
      `}</style>
    </>
  );
}
