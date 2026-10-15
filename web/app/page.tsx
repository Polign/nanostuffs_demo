"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type Hit = { title: string; lang: string; score: number };
type Turn = {
  message: string;
  memory: string[] | null;
  query: string;
  hits: Hit[];
  answer: string;
  remembered: string[];
  seconds: number;
  error?: string;
};
type Memory = { text: string; replaced: string[]; days_ago: number };

const SUGGESTIONS = [
  "I manage the contractor team in our Germany office. What's the parental leave policy?",
  "Does it cover contractors?",
  "What about annual leave?",
  "I've moved to the UK office since last week.",
  "मेरे कॉन्ट्रैक्टर्स को कितने दिन की छुट्टी मिलेगी?",
];

export default function Home() {
  const [user, setUser] = useState<string | null>(null);
  const [name, setName] = useState("priya");
  const [memory, setMemory] = useState(true);
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [known, setKnown] = useState<Memory[]>([]);
  const [busy, setBusy] = useState(false);

  const loadHistory = useCallback(async () => {
    const res = await fetch("/api/history");
    if (res.ok) setKnown(((await res.json()) as { memories: Memory[] }).memories);
  }, []);

  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((s: { userId: string | null }) => setUser(s.userId));
  }, []);

  useEffect(() => {
    if (user) void loadHistory();
  }, [user, loadHistory]);

  async function signIn(e: FormEvent) {
    e.preventDefault();
    const res = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ userId: name }) });
    if (res.ok) {
      setUser(((await res.json()) as { userId: string }).userId);
      setTurns([]);
    }
  }

  async function signOut() {
    await fetch("/api/session", { method: "DELETE" });
    setUser(null);
    setTurns([]);
    setKnown([]);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, memory }) });
      const data = (await res.json()) as Turn & { error?: string };
      setTurns((t) => [...t, res.ok ? data : { message: text, memory: null, query: "", hits: [], answer: "", remembered: [], seconds: 0, error: data.error ?? res.statusText }]);
      if (memory) void loadHistory();
    } finally {
      setBusy(false);
    }
  }

  async function forgetMe() {
    await fetch("/api/history", { method: "DELETE" });
    setKnown([]);
    setTurns([]);
  }

  if (user === null) {
    return (
      <main className="shell">
        <h1>Policy assistant</h1>
        <p className="lead">Sign in with any name. The route handlers read it from the session cookie and pass it to the agent.</p>
        <form onSubmit={signIn} className="row">
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label="user id" />
          <button type="submit">Sign in</button>
        </form>
      </main>
    );
  }

  return (
    <main className="shell wide">
      <header className="bar">
        <h1>Policy assistant</h1>
        <div className="row">
          <label className="toggle">
            <input type="checkbox" checked={memory} onChange={(e) => setMemory(e.target.checked)} /> memory
          </label>
          <span className="who">signed in as <b>{user}</b></span>
          <button onClick={signOut} className="quiet">Sign out</button>
        </div>
      </header>

      <div className="columns">
        <section className="chat">
          {turns.length === 0 && (
            <div className="suggest">
              <p>Try the five-turn script, or ask anything about the handbook:</p>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>
              ))}
            </div>
          )}
          {turns.map((t, i) => (
            <article key={i} className="turn">
              <p className="you">{t.message}</p>
              {t.error ? (
                <p className="error">{t.error}</p>
              ) : (
                <>
                  <p className="answer">{t.answer}</p>
                  <details>
                    <summary>How this was answered ({t.seconds}s)</summary>
                    <dl>
                      <dt>Memory knew</dt>
                      <dd>{t.memory === null ? "(memory off)" : t.memory.length ? t.memory.join("; ") : "(nothing yet)"}</dd>
                      <dt>Query sent to Qdrant</dt>
                      <dd>{t.query}</dd>
                      <dt>Passages</dt>
                      <dd>{t.hits.map((h) => `${h.title} (${h.lang}, ${h.score})`).join(" · ")}</dd>
                      <dt>Remembered</dt>
                      <dd>{t.remembered.length ? t.remembered.join("; ") : "(nothing new)"}</dd>
                    </dl>
                  </details>
                </>
              )}
            </article>
          ))}
          <form
            className="row compose"
            onSubmit={(e) => {
              e.preventDefault();
              void send(message);
            }}
          >
            <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder={busy ? "thinking…" : "Ask about a policy"} disabled={busy} aria-label="message" />
            <button type="submit" disabled={busy || !message.trim()}>Send</button>
          </form>
        </section>

        <aside className="memory">
          <h2>What Recall holds about {user}</h2>
          {known.length === 0 ? (
            <p className="muted">Nothing yet. It fills as you talk, and survives a new chat.</p>
          ) : (
            <ul>
              {known.map((m, i) => (
                <li key={i}>
                  {m.text}
                  {m.replaced.length > 0 && <span className="replaced"> replaced: {m.replaced.join(", ")}</span>}
                </li>
              ))}
            </ul>
          )}
          <div className="row">
            <button className="quiet" onClick={() => setTurns([])}>New chat</button>
            <button className="quiet" onClick={forgetMe}>Forget me</button>
          </div>
        </aside>
      </div>
    </main>
  );
}
