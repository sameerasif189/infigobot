/**
 * Copy into the Infigo React app (e.g. src/components/InfigoChatWidget.tsx).
 * Mount once in root layout: <InfigoChatWidget />
 *
 * Env (Vite): VITE_INFIGO_CHAT_API_URL, VITE_INFIGO_CHAT_API_KEY
 * Env (CRA):  REACT_APP_INFIGO_CHAT_API_URL, REACT_APP_INFIGO_CHAT_API_KEY
 */
import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = (
  import.meta.env?.VITE_INFIGO_CHAT_API_URL ??
  process.env.REACT_APP_INFIGO_CHAT_API_URL ??
  ""
).replace(/\/$/, "");
const API_KEY =
  import.meta.env?.VITE_INFIGO_CHAT_API_KEY ??
  process.env.REACT_APP_INFIGO_CHAT_API_KEY ??
  "";

const SESSION_KEY = "infigo_chat_session";
const VISITOR_KEY = "infigo_visitor";

type Visitor = { name?: string; email?: string };

type ChatResponse = {
  answer: string;
  session_id?: string;
  booking_url?: string;
  contact_email?: string;
  proposal_hint?: string;
  detail?: string;
};

function parseNameEmail(text: string): Visitor | null {
  const m = text.match(/([^\s,]+@[^\s,]+)/);
  if (!m) return null;
  const email = m[1];
  const name = text.replace(email, "").replace(/[,;]/g, " ").trim();
  return { name: name || "Guest", email };
}

function loadVisitor(): Visitor {
  try {
    return JSON.parse(localStorage.getItem(VISITOR_KEY) || "{}");
  } catch {
    return {};
  }
}

export function InfigoChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string; bookingUrl?: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const greeted = useRef(false);

  useEffect(() => {
    if (open && !greeted.current) {
      greeted.current = true;
      setMessages([
        {
          role: "bot",
          text: "Hi! I can explain Infigo startup and enterprise services, our process, and how to book a call or request a proposal.",
        },
      ]);
    }
  }, [open]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || !API_URL) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setLoading(true);

    let visitor = loadVisitor();
    const parsed = parseNameEmail(text);
    if (parsed) {
      visitor = parsed;
      localStorage.setItem(VISITOR_KEY, JSON.stringify(visitor));
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (API_KEY) headers["X-Site-Api-Key"] = API_KEY;

    try {
      const res = await fetch(`${API_URL}/chat/public`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: text,
          session_id: localStorage.getItem(SESSION_KEY),
          visitor_name: visitor.name ?? null,
          visitor_email: visitor.email ?? null,
          llm_mode: "api",
        }),
      });
      const data: ChatResponse = await res.json();
      if (!res.ok) {
        setMessages((m) => [...m, { role: "bot", text: data.detail || "Something went wrong." }]);
        return;
      }
      if (data.session_id) localStorage.setItem(SESSION_KEY, data.session_id);
      setMessages((m) => [
        ...m,
        { role: "bot", text: data.answer, bookingUrl: data.booking_url },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "bot", text: "Could not reach the assistant. Please use our contact form." },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input]);

  if (!API_URL) return null;

  return (
    <>
      <button
        type="button"
        aria-label="Open chat"
        onClick={() => setOpen((o) => !o)}
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 99999,
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: "none",
          background: "#6366f1",
          color: "#fff",
          fontSize: 22,
          cursor: "pointer",
          boxShadow: "0 8px 24px rgba(0,0,0,.25)",
        }}
      >
        💬
      </button>
      {open && (
        <div
          style={{
            position: "fixed",
            bottom: 92,
            right: 24,
            zIndex: 99999,
            width: "min(380px, calc(100vw - 32px))",
            height: 480,
            maxHeight: "70vh",
            background: "#0f172a",
            color: "#f1f5f9",
            borderRadius: 16,
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 16px 48px rgba(0,0,0,.4)",
          }}
        >
          <div style={{ padding: "14px 16px", fontWeight: 600, borderBottom: "1px solid rgba(148,163,184,.2)" }}>
            Infigo Assistant
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "90%",
                  padding: "10px 12px",
                  borderRadius: 12,
                  background: msg.role === "user" ? "#334155" : "#312e81",
                }}
              >
                {msg.text}
                {msg.bookingUrl && (
                  <a href={msg.bookingUrl} target="_blank" rel="noopener noreferrer" style={{ display: "block", marginTop: 6, color: "#22d3ee" }}>
                    Book a meeting
                  </a>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid rgba(148,163,184,.2)" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !loading && send()}
              placeholder="Ask about our services…"
              style={{ flex: 1, borderRadius: 8, border: "1px solid rgba(148,163,184,.3)", background: "#1e293b", color: "#f1f5f9", padding: "8px 10px" }}
            />
            <button type="button" onClick={send} disabled={loading} style={{ borderRadius: 8, border: "none", background: "#6366f1", color: "#fff", padding: "8px 14px" }}>
              Send
            </button>
          </div>
        </div>
      )}
    </>
  );
}
