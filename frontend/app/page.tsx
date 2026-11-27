"use client";

import { useState } from "react";

import { References } from "@/components/References";
import type { Status } from "@/lib/types";
import { useCopilot } from "@/lib/useCopilot";

const VERDICT: Record<Status, { label: string; className: string }> = {
  verified: { label: "Verificada contra las fuentes", className: "bg-teal-50 text-teal-800" },
  retracted: { label: "Respuesta retirada: no pasó la verificación", className: "bg-red-50 text-red-800" },
  abstained: { label: "Las guías no responden esta pregunta", className: "bg-gray-100 text-gray-700" },
  no_evidence: { label: "Sin evidencia suficiente en las guías", className: "bg-gray-100 text-gray-700" },
  blocked: { label: "Pregunta bloqueada", className: "bg-amber-50 text-amber-800" },
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const { ask, stage, blocks, references, final, error, busy } = useCopilot();

  // Decisión de diseño (ver README): el texto se muestra solo después del veredicto, nunca mientras llega.
  // Una respuesta retirada no se muestra; las fuentes tampoco, para no invitar a leerla por partes.
  const showAnswer = blocks.length > 0 && (final?.status === "verified" || final?.status === "abstained");

  return (
    <main className="mx-auto grid w-full max-w-6xl gap-8 p-8 lg:grid-cols-[3fr_2fr]">
      <section>
        <h1 className="text-2xl font-semibold">Copiloto clínico</h1>
        <p className="mt-1 text-sm text-gray-500">Responde solo con las guías cargadas. Cada afirmación lleva su fuente.</p>

        <form
          className="mt-6 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim().length >= 3) ask(question.trim());
          }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="¿Cuál es la meta de HbA1c en personas con DM2?"
            className="flex-1 rounded-md border border-gray-300 px-3 py-2"
          />
          <button disabled={busy} className="rounded-md bg-teal-700 px-4 py-2 font-medium text-white disabled:opacity-50">
            Preguntar
          </button>
        </form>

        {stage && (
          <p className="mt-4 text-sm text-gray-500" aria-live="polite">
            {stage}
          </p>
        )}
        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}

        {final && (
          <p className={`mt-4 inline-block rounded px-2 py-1 text-xs font-medium ${VERDICT[final.status].className}`}>
            {VERDICT[final.status].label}
          </p>
        )}

        {showAnswer && (
          <p className="mt-3 whitespace-pre-wrap leading-relaxed text-gray-900">
            {blocks.map((b, i) => (
              <span key={i}>
                {b.text}
                {b.cites.map((n) => (
                  <sup key={n} className="ml-0.5 font-medium text-teal-700">[{n}]</sup>
                ))}
              </span>
            ))}
          </p>
        )}

        {final?.message && <p className="mt-3 text-gray-700">{final.message}</p>}
        {final?.status === "retracted" && (
          <ul className="mt-3 list-disc pl-5 text-sm text-red-800">
            {final.problems.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        )}

        <p className="mt-10 text-xs text-gray-400">
          Demo educativa. Apoya la consulta de guías clínicas; no reemplaza el juicio profesional
          ni debe usarse con datos de pacientes.
        </p>
      </section>

      <aside>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Fuentes citadas</h2>
        <div className="mt-3">
          {showAnswer && references.length > 0
            ? <References references={references} />
            : <p className="text-sm text-gray-400">Aparecerán aquí, con página, párrafo y texto exacto.</p>}
        </div>
      </aside>
    </main>
  );
}
