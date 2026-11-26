"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      setAnswer(data.answer ?? data.reason ?? JSON.stringify(data));
    } catch (err) {
      setAnswer(`Error: ${err}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "4rem auto", padding: "0 1rem" }}>
      <h1>Copiloto Clínico</h1>
      <form onSubmit={ask} style={{ display: "flex", gap: 8 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Escribe tu pregunta clínica…"
          style={{ flex: 1, padding: 8 }}
        />
        <button disabled={loading || !query.trim()}>{loading ? "…" : "Preguntar"}</button>
      </form>
      {answer && <p style={{ whiteSpace: "pre-wrap", marginTop: 24 }}>{answer}</p>}
    </main>
  );
}
