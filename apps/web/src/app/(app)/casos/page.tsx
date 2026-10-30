"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { CASE_STATUS, CASE_TYPE, OEM_CUSTOMERS, SEGMENTS, SEVERITY, SOURCE, SOURCES_BY_TYPE, todayISO } from "@/lib/labels";
import type { Case, IssuedDocument, Plant, RegisterRow } from "@/lib/types";
import { Empty, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { RegisterTable } from "@/components/dashboard/RegisterTable";

function NewCase({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const plants = useApi<Plant[]>("/plants");
  const [form, setForm] = useState({ plant_id: "", title: "", case_type: "", severity: "medium", source_type: "", part_number: "",
    customer_name: "", process_name: "", market_segment: "", main_defect: "", report_date: todayISO() });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (plants.data?.length && !form.plant_id) setForm((f) => ({ ...f, plant_id: plants.data![0].id }));
  }, [plants.data, form.plant_id]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ""));
      const created = await api<Case>("/cases", { body });
      router.push(`/casos/${created.id}`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal title="Nuevo caso 8D" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <ErrorBox error={error ?? plants.error} />
        <Field label="Título del problema" required><input value={form.title} onChange={set("title")} maxLength={200} required autoFocus /></Field>
        <div className="row" role="radiogroup" aria-label="Tipo de 8D">
          {(["external", "internal"] as const).map((t) => (
            <button type="button" key={t} role="radio" aria-checked={form.case_type === t}
              className={`btn ${form.case_type === t ? "primary" : ""}`} style={{ flex: 1, justifyContent: "center", flexDirection: "column", gap: 2 }}
              onClick={() => setForm({ ...form, case_type: t, source_type: t === "external" ? "customer_complaint" : "internal" })}>
              <span>{t === "external" ? "8D externo" : "8D interno"}</span>
              <span className="small" style={{ fontWeight: 400, opacity: 0.85 }}>{t === "external" ? "Reclamación del cliente" : "Detectado en planta, proveedor o auditoría"}</span>
            </button>))}
        </div>
        <div className="grid g2">
          <Field label="Planta" required>
            <select value={form.plant_id} onChange={set("plant_id")} required>
              {plants.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </Field>
          <Field label="Severidad"><select value={form.severity} onChange={set("severity")}>
            {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Origen"><select value={form.source_type} onChange={set("source_type")} disabled={!form.case_type}>
            <option value="">Seleccionar…</option>{(SOURCES_BY_TYPE[form.case_type] ?? []).map((k) => <option key={k} value={k}>{SOURCE[k]}</option>)}</select></Field>
          <Field label="Fecha de reporte" required><input type="date" value={form.report_date} onChange={set("report_date")} max={todayISO()} required /></Field>
          <Field label="Número de parte"><input value={form.part_number} onChange={set("part_number")} maxLength={100} /></Field>
          <Field label={form.case_type === "external" ? "Cliente" : "Cliente (opcional)"} required={form.case_type === "external"}>
            <input value={form.customer_name} onChange={set("customer_name")} maxLength={200} required={form.case_type === "external"}
              list="oem-customers" placeholder="p. ej. Ford, GM, Toyota" />
            <datalist id="oem-customers">{OEM_CUSTOMERS.map((c) => <option key={c} value={c} />)}</datalist></Field>
          <Field label="Proceso"><input value={form.process_name} onChange={set("process_name")} maxLength={200} placeholder="p. ej. Inyección, Maquinado" /></Field>
          <Field label="Defecto principal"><input value={form.main_defect} onChange={set("main_defect")} maxLength={200} placeholder="p. ej. Rebaba, Fuga, Faltante" /></Field>
          <Field label="Mercado"><select value={form.market_segment} onChange={set("market_segment")}>
            <option value="">—</option>{SEGMENTS.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
        </div>
        <p className="small muted">Se asigna un folio automático. Te registras como responsable y líder; puedes cambiarlo en D1.</p>
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary right" disabled={busy || !form.plant_id || !form.case_type} title={form.case_type ? "" : "Elige si el 8D es externo o interno"}>{busy ? "Creando…" : "Crear caso"}</button></div>
      </form>
    </Modal>
  );
}

/** Todos los 8D con sus hitos (concentrado): búsqueda, filtros y exportación a Excel. */
function CaseList() {
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
  const filtered = Object.values(f).some(Boolean);

  async function exportExcel() {
    try {
      const d = await api<IssuedDocument>("/exports/register", { body: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])) });
      setMsg({ ok: true, text: `${d.file_name} generado.`, id: d.id });
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  }

  return (
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
        <span className="right row small muted">{rows.length} 8D · {late} con hitos tarde o vencidos
          {canExport && <button className="btn sm" onClick={exportExcel}>Exportar a Excel</button>}</span>
      </div>
      {msg && <div style={{ padding: "0 18px 12px" }}><div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}{msg.id && <> <a href={`/api/documents/${msg.id}/content`}>Descargar</a></>}</div></div>}
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <div className="card-pad"><Loading /></div> : !rows.length && !filtered ? (
        <Empty title="Sin casos">Crea el primer caso 8D.</Empty>
      ) : <RegisterTable rows={rows} />}
    </div>
  );
}

function CasesPage() {
  const params = useSearchParams();
  const canCreate = useCan("case.create");
  const [creating, setCreating] = useState(params.get("nuevo") === "1");

  return (
    <>
      <div className="page-head">
        <div><h1>Casos 8D</h1><div className="sub">Expedientes con sus hitos: D3 24 h · D4 48 h · D5–D7 7 días · D8 14 días desde la fecha de reporte</div></div>
        <div className="actions">{canCreate && <button className="btn primary" onClick={() => setCreating(true)}>+ Nuevo caso</button>}</div>
      </div>
      <CaseList />
      {creating && <NewCase onClose={() => setCreating(false)} />}
    </>
  );
}

export default function Page() {
  return <Suspense><CasesPage /></Suspense>;
}
