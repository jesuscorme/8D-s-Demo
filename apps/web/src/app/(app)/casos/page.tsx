"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { CASE_STATUS, SEVERITY, SOURCE, fmtDate } from "@/lib/labels";
import type { Case, CaseSummary, Plant } from "@/lib/types";
import { Badge, CaseStatus, Empty, ErrorBox, Field, Loading, Modal, Severity } from "@/components/ui";
import { useCan } from "@/components/Shell";

function NewCase({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const plants = useApi<Plant[]>("/plants");
  const [form, setForm] = useState({ plant_id: "", title: "", severity: "medium", source_type: "", part_number: "", customer_name: "", process_name: "" });
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
        <div className="grid g2">
          <Field label="Planta" required>
            <select value={form.plant_id} onChange={set("plant_id")} required>
              {plants.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </Field>
          <Field label="Severidad"><select value={form.severity} onChange={set("severity")}>
            {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Origen"><select value={form.source_type} onChange={set("source_type")}>
            <option value="">Seleccionar…</option>{Object.entries(SOURCE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Número de parte"><input value={form.part_number} onChange={set("part_number")} maxLength={100} /></Field>
          <Field label="Cliente"><input value={form.customer_name} onChange={set("customer_name")} maxLength={200} /></Field>
          <Field label="Proceso"><input value={form.process_name} onChange={set("process_name")} maxLength={200} placeholder="p. ej. Inyección, Maquinado" /></Field>
        </div>
        <p className="small muted">Se asigna un folio automático. Te registras como responsable y líder; puedes cambiarlo en D1.</p>
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary right" disabled={busy || !form.plant_id}>{busy ? "Creando…" : "Crear caso"}</button></div>
      </form>
    </Modal>
  );
}

function CasesPage() {
  const params = useSearchParams();
  const canCreate = useCan("case.create");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [mine, setMine] = useState(params.get("mine") === "1");
  const [creating, setCreating] = useState(params.get("nuevo") === "1");
  const qs = new URLSearchParams({ ...(query && { q: query }), ...(status && { status }), ...(severity && { severity }), ...(mine && { mine: "true" }) });
  const { data, error, loading, reload } = useApi<CaseSummary[]>(`/cases?${qs}`);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <>
      <div className="page-head">
        <div><h1>Casos 8D</h1><div className="sub">Expedientes de tu organización</div></div>
        <div className="actions">{canCreate && <button className="btn primary" onClick={() => setCreating(true)}>+ Nuevo caso</button>}</div>
      </div>
      <div className="card">
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <input placeholder="Buscar por folio, título, parte, cliente…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 320 }} aria-label="Buscar" />
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 170 }} aria-label="Estado">
            <option value="">Todos los estados</option>{Object.entries(CASE_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} style={{ maxWidth: 170 }} aria-label="Severidad">
            <option value="">Toda severidad</option>{Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} style={{ width: "auto" }} />Solo míos</label>
        </div>
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <div className="card-pad"><Loading /></div> : data && data.length === 0 ? (
          <Empty title="Sin casos">{query || status || severity || mine ? "Ningún caso coincide con los filtros." : "Crea el primer caso 8D."}</Empty>
        ) : data && (
          <div className="table-wrap"><table>
            <thead><tr><th>Folio</th><th>Título</th><th>Planta</th><th>Parte</th><th>Cliente</th><th>Severidad</th><th>Disciplina</th><th>Estado</th><th>Responsable</th><th>Actualizado</th></tr></thead>
            <tbody>{data.map((c) => (
              <tr key={c.id}>
                <td className="mono"><Link href={`/casos/${c.id}`}>{c.folio}</Link></td>
                <td>{c.title}{c.is_demo && <> <Badge tone="amber">Demo</Badge></>}</td>
                <td>{c.plant_code}</td><td>{c.part_number ?? "—"}</td><td>{c.customer_name ?? "—"}</td>
                <td><Severity value={c.severity} /></td>
                <td><Badge tone="navy">{c.current_discipline ?? "—"}</Badge></td>
                <td><CaseStatus status={c.status} /></td>
                <td>{c.owner_name ?? "—"}</td>
                <td className="muted small">{fmtDate(c.updated_at, true)}</td>
              </tr>))}
            </tbody>
          </table></div>
        )}
      </div>
      {creating && <NewCase onClose={() => setCreating(false)} />}
    </>
  );
}

export default function Page() {
  return <Suspense><CasesPage /></Suspense>;
}
