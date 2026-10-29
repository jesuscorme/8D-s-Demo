"use client";

import { useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { CASE_STATUS, CASE_TYPE } from "@/lib/labels";
import type { IssuedDocument, Plant, RegisterRow } from "@/lib/types";
import { ErrorBox, Loading } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { RegisterTable } from "@/components/dashboard/RegisterTable";

export default function RegisterPage() {
  const canExport = useCan("report.export");
  const plants = useApi<Plant[]>("/plants");
  const [q, setQ] = useState("");
  const [f, setF] = useState({ q: "", case_type: "", status: "", plant_id: "", date_from: "", date_to: "" });
  useEffect(() => {
    const t = setTimeout(() => setF((x) => ({ ...x, q: q.trim() })), 300);
    return () => clearTimeout(t);
  }, [q]);
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v)));
  const { data, error, loading, reload } = useApi<{ rows: RegisterRow[] }>(`/reports/register?${qs}`);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; id?: string } | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const rows = data?.rows ?? [];
  const late = rows.filter((r) => r.milestones.some((m) => m.status === "late" || m.status === "overdue")).length;

  async function exportExcel() {
    try {
      const d = await api<IssuedDocument>("/exports/register", { body: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])) });
      setMsg({ ok: true, text: `${d.file_name} generado.`, id: d.id });
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Concentrado de 8D</h1><div className="sub">Todos los 8D con sus hitos: D3 24 h · D4 48 h · D5–D7 7 días · D8 14 días desde la fecha de reporte</div></div>
        <div className="actions">{canExport && <button className="btn primary" onClick={exportExcel}>Exportar a Excel</button>}</div>
      </div>
      <div className="card">
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <input placeholder="Buscar folio, falla, parte, cliente, defecto…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 280 }} aria-label="Buscar" />
          <select value={f.case_type} onChange={set("case_type")} style={{ maxWidth: 160 }} aria-label="Tipo"><option value="">Internos y externos</option>
            {Object.entries(CASE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select value={f.status} onChange={set("status")} style={{ maxWidth: 160 }} aria-label="Estado"><option value="">Todos los estados</option>
            {Object.entries(CASE_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select value={f.plant_id} onChange={set("plant_id")} style={{ maxWidth: 170 }} aria-label="Planta"><option value="">Todas las plantas</option>
            {plants.data?.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}</select>
          <label className="row small">Reporte desde <input type="date" value={f.date_from} onChange={set("date_from")} style={{ width: 150 }} /></label>
          <label className="row small">hasta <input type="date" value={f.date_to} onChange={set("date_to")} style={{ width: 150 }} /></label>
          <span className="right small muted">{rows.length} 8D · {late} con hitos tarde o vencidos</span>
        </div>
        {msg && <div style={{ padding: "0 18px 12px" }}><div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}{msg.id && <> <a href={`/api/documents/${msg.id}/content`}>Descargar</a></>}</div></div>}
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <div className="card-pad"><Loading /></div> : <RegisterTable rows={rows} />}
      </div>
    </>
  );
}
