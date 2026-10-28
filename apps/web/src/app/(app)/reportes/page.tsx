"use client";

import Link from "next/link";
import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { CASE_STATUS, DOC_TYPE, fmtBytes, fmtDate } from "@/lib/labels";
import type { IssuedDocument, Plant } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { useCan } from "@/components/Shell";

type Count = { label: string; n: number };
type Kpis = {
  definitions: { id: string; name: string; definition: string; source: string; rule: string }[];
  open_cases: number; closed_cases: number; by_status: Record<string, number>; by_discipline: Record<string, number>;
  overdue_cases: number; cases_without_target: number;
  actions: { containment_open: number; containment_overdue: number; actions_open: number; actions_overdue: number; actions_pending_approval: number };
  resolution: { n: number; sufficient: boolean; median_days?: number; mean_days?: number };
  effectiveness: { effective: number; ineffective: number; insufficient_data: number; n: number; sufficient: boolean; effective_pct: number | null };
  distribution: { n: number; sufficient: boolean; customer?: Count[]; product?: Count[]; process?: Count[]; plant?: Count[] };
};
type Doc = { id: string; document_type: string; revision: number; file_name: string; file_size_bytes: number; sha256_hex: string; status: string; generated_at: string; case_id: string | null; case_folio: string | null; generated_by_name: string };

function Kpi({ label, value, tone, note }: { label: string; value: string | number; tone?: string; note?: string }) {
  const text = typeof value === "string" && !/^[\d\s./%d]+$/.test(value);
  return <div className="card kpi"><div className="l">{label}</div>
    <div className="v" style={{ ...(tone ? { color: tone } : {}), ...(text ? { fontSize: 17, color: "var(--muted)", marginTop: 10 } : {}) }}>{value}</div>
    {note && <div className="small muted">{note}</div>}</div>;
}

function Bars({ title, rows }: { title: string; rows: Count[] }) {
  const max = Math.max(...rows.map((r) => r.n), 1);
  return (
    <div className="card card-pad">
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      <div className="stack" style={{ gap: 6 }}>{rows.map((r) => (
        <div key={r.label} className="small">
          <div className="row" style={{ gap: 6 }}><span>{r.label}</span><b className="right">{r.n}</b></div>
          <div style={{ height: 6, background: "var(--line-2)", borderRadius: 3 }}><div style={{ width: `${(100 * r.n) / max}%`, height: 6, background: "var(--accent)", borderRadius: 3 }} /></div>
        </div>))}</div>
    </div>
  );
}

export default function ReportsPage() {
  const canExport = useCan("report.export");
  const canAudit = useCan("audit.read");
  const plants = useApi<Plant[]>("/plants");
  const [f, setF] = useState({ plant_id: "", date_from: "", date_to: "" });
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v)));
  const k = useApi<Kpis>(`/reports/kpis?${qs}`);
  const docs = useApi<Doc[]>("/documents");
  const [msg, setMsg] = useState<{ ok: boolean; text: string; id?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [key]: e.target.value });

  async function exportTo(path: string, body: unknown) {
    setBusy(true);
    try {
      const d = await api<IssuedDocument>(path, { body });
      setMsg({ ok: true, text: `${d.file_name} generado.`, id: d.id });
      void docs.reload();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }
  const filters = { plant_id: f.plant_id || null, date_from: f.date_from || null, date_to: f.date_to || null };

  return (
    <>
      <div className="page-head"><div><h1>Reportes e indicadores</h1><div className="sub">Calculados con datos reales de tu organización y plantas visibles.</div></div></div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <select value={f.plant_id} onChange={set("plant_id")} style={{ maxWidth: 200 }} aria-label="Planta"><option value="">Todas las plantas</option>
            {plants.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select>
          <label className="row small">Alta desde <input type="date" value={f.date_from} onChange={set("date_from")} style={{ width: 160 }} /></label>
          <label className="row small">hasta <input type="date" value={f.date_to} onChange={set("date_to")} style={{ width: 160 }} /></label>
          <div className="right row">
            {canExport && <button className="btn sm" disabled={busy} onClick={() => exportTo("/exports/cases", { plant_id: filters.plant_id, date_from: filters.date_from, date_to: filters.date_to })}>Exportar casos (Excel)</button>}
            {canAudit && <button className="btn sm" disabled={busy} onClick={() => exportTo("/exports/audit", { date_from: filters.date_from, date_to: filters.date_to })}>Exportar bitácora (Excel)</button>}
          </div>
        </div>
        {msg && <div style={{ padding: "0 18px 14px" }}><div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}{msg.id && <> <a href={`/api/documents/${msg.id}/content`}>Descargar</a></>}</div></div>}
      </div>
      <ErrorBox error={k.error} onRetry={k.reload} />
      {k.loading && !k.data ? <Loading rows={5} /> : k.data && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid g4">
            <Kpi label="Casos abiertos" value={k.data.open_cases} />
            <Kpi label="Casos cerrados" value={k.data.closed_cases} />
            <Kpi label="Casos vencidos" value={k.data.overdue_cases} tone={k.data.overdue_cases ? "var(--bad)" : undefined}
              note={k.data.cases_without_target ? `${k.data.cases_without_target} abierto(s) sin fecha objetivo` : undefined} />
            <Kpi label="Tiempo de resolución" value={k.data.resolution.sufficient ? `${k.data.resolution.median_days} d` : "Datos insuficientes"}
              note={k.data.resolution.sufficient ? `Mediana; media ${k.data.resolution.mean_days} d · n=${k.data.resolution.n}` : `n=${k.data.resolution.n}; se requieren 3 casos cerrados`} />
          </div>
          <div className="grid g4">
            <Kpi label="Acciones abiertas" value={k.data.actions.actions_open} note={`${k.data.actions.actions_pending_approval} pendiente(s) de aprobación`} />
            <Kpi label="Acciones vencidas" value={k.data.actions.actions_overdue} tone={k.data.actions.actions_overdue ? "var(--bad)" : undefined} />
            <Kpi label="Contenciones abiertas / vencidas" value={`${k.data.actions.containment_open} / ${k.data.actions.containment_overdue}`} />
            <Kpi label="Eficacia" value={k.data.effectiveness.effective_pct !== null ? `${k.data.effectiveness.effective_pct} %` : "Datos insuficientes"}
              note={`${k.data.effectiveness.effective} eficaz · ${k.data.effectiveness.ineffective} no eficaz · ${k.data.effectiveness.insufficient_data} datos insuf.${k.data.effectiveness.sufficient ? "" : " (porcentaje con n ≥ 5)"}`} />
          </div>
          <div className="grid g2">
            <div className="card">
              <div className="card-head"><h2>Casos por estado</h2></div>
              {!Object.keys(k.data.by_status).length ? <Empty title="Sin casos en el periodo" /> : (
                <div className="table-wrap"><table><tbody>{Object.entries(k.data.by_status).map(([s, n]) => <tr key={s}><td>{CASE_STATUS[s] ?? s}</td><td style={{ width: 80 }}><b>{n}</b></td></tr>)}</tbody></table></div>)}
            </div>
            <div className="card">
              <div className="card-head"><h2>Casos abiertos por disciplina</h2></div>
              {!Object.keys(k.data.by_discipline).length ? <Empty title="Sin casos abiertos" /> : (
                <div className="table-wrap"><table><tbody>{Object.entries(k.data.by_discipline).map(([d, n]) => <tr key={d}><td><Badge tone="navy">{d}</Badge></td><td style={{ width: 80 }}><b>{n}</b></td></tr>)}</tbody></table></div>)}
            </div>
          </div>
          {k.data.distribution.sufficient ? (
            <div className="grid g4">
              <Bars title="Por cliente" rows={k.data.distribution.customer ?? []} />
              <Bars title="Por producto" rows={k.data.distribution.product ?? []} />
              <Bars title="Por proceso" rows={k.data.distribution.process ?? []} />
              <Bars title="Por planta" rows={k.data.distribution.plant ?? []} />
            </div>
          ) : <div className="notice info">Distribución por cliente, producto, proceso y planta: datos insuficientes (n={k.data.distribution.n}; se requieren 3 casos).</div>}
          <details className="card card-pad">
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>Definición de los indicadores</summary>
            <div className="table-wrap" style={{ marginTop: 10 }}><table>
              <thead><tr><th>Indicador</th><th>Definición</th><th>Fuente</th><th>Regla de cálculo</th></tr></thead>
              <tbody>{k.data.definitions.map((d) => <tr key={d.id}><td><b>{d.name}</b></td><td className="small">{d.definition}</td><td className="mono">{d.source}</td><td className="small">{d.rule}</td></tr>)}</tbody>
            </table></div>
          </details>
        </div>
      )}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2>Documentos emitidos</h2><span className="small muted">Solo los que puedes consultar.</span></div>
        <ErrorBox error={docs.error} onRetry={docs.reload} />
        {!docs.data?.length ? <Empty title="Sin documentos" /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Archivo</th><th>Tipo</th><th>Rev.</th><th>Caso</th><th>Estado</th><th>Emitido</th><th>SHA-256</th></tr></thead>
            <tbody>{docs.data.map((d) => (
              <tr key={d.id}>
                <td><a href={`/api/documents/${d.id}/content`} target="_blank" rel="noreferrer">{d.file_name}</a><div className="small muted">{fmtBytes(d.file_size_bytes)}</div></td>
                <td>{DOC_TYPE[d.document_type] ?? d.document_type}</td><td>{d.revision}</td>
                <td className="mono">{d.case_id ? <Link href={`/casos/${d.case_id}`}>{d.case_folio}</Link> : "—"}</td>
                <td><Badge tone={d.status === "issued" ? "green" : ""}>{d.status === "issued" ? "Vigente" : "Sustituido"}</Badge></td>
                <td className="small">{fmtDate(d.generated_at, true)}<div className="muted">{d.generated_by_name}</div></td>
                <td className="mono" title={d.sha256_hex}>{d.sha256_hex.slice(0, 12)}…</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}

