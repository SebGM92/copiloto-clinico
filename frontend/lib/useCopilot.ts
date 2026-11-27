"use client";

import { useState } from "react";

import { readSSE } from "./sse";
import type { AnswerBlock, Final, Reference } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STAGES: Record<string, string> = {
  buscando: "Buscando en las guías…",
  generando: "Redactando la respuesta…",
  verificando: "Verificando cada cita contra la fuente…",
};

export function useCopilot() {
  const [stage, setStage] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<AnswerBlock[]>([]);
  const [references, setReferences] = useState<Reference[]>([]);
  const [final, setFinal] = useState<Final | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(question: string) {
    setStage(STAGES.buscando);
    setBlocks([]);
    setReferences([]);
    setFinal(null);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok) throw new Error(`La API respondió ${response.status}`);

      let gotFinal = false;
      for await (const { event, data } of readSSE(response)) {
        if (event === "status") {
          setStage(STAGES[(data as { stage: string }).stage] ?? null);
        } else if (event === "token") {
          const { text, block } = data as { text: string; block: number };
          setBlocks((prev) => {
            const next = [...prev];
            next[block] = { text: (next[block]?.text ?? "") + text, cites: next[block]?.cites ?? [] };
            return next;
          });
        } else if (event === "citation") {
          const { n, block } = data as { n: number; block: number };
          setBlocks((prev) => {
            const next = [...prev];
            const current = next[block] ?? { text: "", cites: [] };
            next[block] = { ...current, cites: current.cites.includes(n) ? current.cites : [...current.cites, n] };
            return next;
          });
        } else if (event === "references") {
          setReferences(data as Reference[]);
        } else if (event === "final") {
          gotFinal = true;
          setFinal(data as Final);
        }
      }
      // Sin veredicto no hay respuesta que mostrar: la conexión se cortó a mitad de camino
      if (!gotFinal) throw new Error("La conexión se cortó antes de verificar la respuesta. Intenta de nuevo.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setStage(null);
    }
  }

  return { ask, stage, blocks, references, final, error, busy: stage !== null };
}
