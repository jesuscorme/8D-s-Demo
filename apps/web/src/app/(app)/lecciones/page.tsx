"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { LESSON_STATUS, fmtDate } from "@/lib/labels";
import type { LessonSummary } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { useCan } from "@/components/Shell";

const TONE: Record<string, string> = { draft: "blue", in_review: "amber", approved: "green", published: "green", superseded: "", retired: "red" };

export default function LessonsPage() {
  const canEdit = useCan("lesson.edit");
  const [q, setQ] = useState("");
  const [f, setF] = useState({ q: "", status: "", process: "", product: "", plant: "", language: "" });
  useEffect(() => {
    const t = setTimeout(() => setF((x) => ({ ...x, q: q.trim() })), 300);
    return () => clearTimeout(t);
  }, [q]);
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v)));
  const { data, error, loading, reload } = useApi<LessonSummary[]>(`/lessons?${qs}`);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  return (
    <>
      <div className="page-head">
        <div><h1>Lecciones aprendidas</h1><div className="sub">{canEdit ? "Biblioteca completa con su flujo de revisión." : "Lecciones publicadas."} Se crean desde la D8 de un caso.</div></div>
      </div>
      <div className="card">
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <input placeholder="Buscar en título, problema, causa, acciones…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 300 }} aria-label="Buscar" />
          <input placeholder="Proceso" value={f.process} onChange={set("process")} style={{ maxWidth: 140 }} aria-label="Proceso" />
          <input placeholder="Producto" value={f.product} onChange={set("product")} style={{ maxWidth: 140 }} aria-label="Producto" />
          <input placeholder="Planta" value={f.plant} onChange={set("plant")} style={{ maxWidth: 100 }} aria-label="Planta" />
          {canEdit && <select value={f.status} onChange={set("status")} style={{ maxWidth: 160 }} aria-label="Estado">
            <option value="">Todos los estados</option>{Object.entries(LESSON_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
          <select value={f.language} onChange={set("language")} style={{ maxWidth: 120 }} aria-label="Idioma"><option value="">Idioma</option><option value="es">Español</option><option value="en">Inglés</option></select>
        </div>
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <div className="card-pad"><Loading /></div> : !data?.length ? <Empty title="Sin lecciones">Ninguna lección coincide con los filtros.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Folio</th><th>Rev.</th><th>Título</th><th>Aplica a</th><th>Idioma</th><th>Caso origen</th><th>Reutilizada</th><th>Estado</th><th>Actualizada</th></tr></thead>
            <tbody>{data.map((l) => (
              <tr key={l.id}>
                <td className="mono"><Link href={`/lecciones/${l.id}`}>{l.folio}</Link></td><td>{l.revision}</td><td>{l.title}</td>
                <td className="small">{[...l.products, ...l.processes, ...l.plant_codes, ...l.situations].slice(0, 5).join(", ") || "—"}</td>
                <td>{l.language_code.toUpperCase()}</td><td className="mono small">{l.source_folio}</td><td>{l.application_count}</td>
                <td><Badge tone={TONE[l.status]}>{LESSON_STATUS[l.status]}</Badge></td>
                <td className="small muted">{fmtDate(l.updated_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}
