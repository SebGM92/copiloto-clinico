import type { Reference } from "@/lib/types";

const OLD_GUIDE_YEARS = 5;

function location(ref: Reference): string {
  return ref.paragraphs
    .map((p) =>
      p.kind === "table"
        ? `pág. ${p.page}, tabla`
        : p.kind === "caption"
          ? `pág. ${p.page}, título de tabla` // los rótulos no cuentan como párrafo (para = 0)
          : `pág. ${p.page}, párr. ${p.para}`,
    )
    .join(" · ");
}

export function References({ references }: { references: Reference[] }) {
  // Varias citas pueden apuntar al mismo párrafo: se muestran una sola vez
  const unique = references.filter(
    (r, i) => references.findIndex((o) => o.n === r.n && location(o) === location(r)) === i,
  );
  const currentYear = new Date().getFullYear();

  return (
    <ol className="space-y-3">
      {unique.map((ref) => (
        <li key={`${ref.n}-${location(ref)}`} className="rounded-lg border border-gray-200 p-3 text-sm">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-medium">
              [{ref.n}] {ref.title} ({ref.year})
            </span>
            <a href={ref.url} target="_blank" rel="noreferrer" className="shrink-0 text-teal-700 hover:underline">
              Abrir PDF
            </a>
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            {ref.section} · {location(ref)}
          </p>
          {currentYear - ref.year > OLD_GUIDE_YEARS && (
            <p className="mt-1 text-xs text-amber-700">
              Guía de {ref.year}: revisa si existe una actualización antes de aplicarla.
            </p>
          )}
          <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-teal-600 pl-3 text-gray-700">
            {ref.quote}
          </blockquote>
        </li>
      ))}
    </ol>
  );
}
