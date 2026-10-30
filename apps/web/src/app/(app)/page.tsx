"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useApi } from "@/lib/api";
import { CASE_TYPE, MILESTONE_STATUS, fmtDate } from "@/lib/labels";
import type { RegisterRow } from "@/lib/types";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import { useMe } from "@/components/Shell";
import { Donut, HBars, MilestoneBars, SERIES, Trend, monthLabel } from "@/components/dashboard/Charts";

type Task = { kind: string; label: string; case_id: string; folio: string; due: string | null; overdue: boolean };
type Dashboard = { my_tasks: Task[]; attention: { actions_pending_approval: number } };

// Filtros tipo Power BI: cada gráfico filtra a los demás; un gráfico no se filtra por su propia dimensión.
type Filters = { status: string | null; type: string | null; customer: string | null; month: string | null;
  defect: string | null; leader: string | null };
type Dim = keyof Filters;
const NONE: Filters = { status: null, type: null, customer: null, month: null, defect: null, leader: null };

const STATUS: Record<string, { label: string; color: string }> = {
  in_process: { label: "En proceso", color: SERIES[0] }, review: { label: "En revisión", color: SERIES[1] },
  closed: { label: "Cerrado", color: SERIES[2] },
};
const statusOf = (r: RegisterRow) => r.status === "closed" || r.status === "approved" ? "closed" : r.status === "pending_review" ? "review" : "in_process";
const customerOf = (r: RegisterRow) => r.case_type === "internal" ? "Internos (planta)" : (r.customer_name?.trim() || "Sin cliente");
const monthEnd = (m: string) => { const [y, mm] = m.split("-").map(Number); return `${m}-${String(new Date(y, mm, 0).getDate()).padStart(2, "0")}`; };
/** Trabajado en el mes: abierto en algún momento del mes (reportado antes de que termine y no cerrado antes de que empiece). */
const workedIn = (r: RegisterRow, m: string) => r.report_date <= monthEnd(m) && (!r.closed_on || r.closed_on >= `${m}-01`);
const leaderOf = (r: RegisterRow) => r.leader ?? "Sin responsable";

const MATCH: Record<Dim, (r: RegisterRow, v: string) => boolean> = {
  status: (r, v) => v === "overdue" ? r.overdue : statusOf(r) === v,
  type: (r, v) => r.case_type === v,
  customer: (r, v) => customerOf(r) === v,
  month: workedIn,
  defect: (r, v) => (r.main_defect ?? "Sin defecto") === v,
  leader: (r, v) => leaderOf(r) === v,
};
const LABEL: Record<Dim, string> = { status: "Estado", type: "Tipo", customer: "Cliente", month: "Trabajados en", defect: "Defecto", leader: "Responsable" };
const KPIS = [
  { key: null, label: "8D total", icon: "▤", bg: "#e8f1fd", fg: "#1d6fe0" },
  { key: "in_process", label: "En proceso", icon: "◔", bg: "#fff4df", fg: "#b26a00" },
  { key: "closed", label: "Cerrados", icon: "✓", bg: "#e6f5ec", fg: "#1f8a4c" },
  { key: "overdue", label: "Vencidos", icon: "!", bg: "#fdecec", fg: "#c62828" },
] as const;
const MS_COLORS = { on_time: "#1f8a4c", late: "#d08700", overdue: "#c62828", pending: "#8a96a8" };
const MS_ROWS = [["containment", "D3 · Contención 24 h"], ["root_cause", "D4 · Causa raíz 48 h"], ["actions", "D5–D7 · Acciones 7 días"], ["close", "D8 · Cierre 14 días"]] as const;
const TASK: Record<string, { icon: string; bg: string; fg: string; verb: string }> = {
  action: { icon: "A", bg: "#e8f1fd", fg: "#1d6fe0", verb: "Implementar acción" },
  containment: { icon: "C", bg: "#fff4df", fg: "#b26a00", verb: "Contención" },
  review: { icon: "R", bg: "#efeafd", fg: "#6250d6", verb: "Revisión" },
  approve_action: { icon: "✓", bg: "#e6f5ec", fg: "#1f8a4c", verb: "Aprobación" },
};

function count<T>(items: T[], key: (x: T) => string) {
  const out = new Map<string, number>();
  for (const x of items) out.set(key(x), (out.get(key(x)) ?? 0) + 1);
  return [...out.entries()].map(([label, n]) => ({ label, n })).sort((a, b) => b.n - a.n || a.label.localeCompare(b.label));
}

export default function Home() {
  const me = useMe();
  const dash = useApi<Dashboard>("/dashboard");
  const reg = useApi<{ rows: RegisterRow[] }>("/reports/register");
  const [f, setF] = useState<Filters>(NONE);
  const all = useMemo(() => (reg.data?.rows ?? []).filter((r) => r.status !== "cancelled"), [reg.data]);

  const toggle = (dim: Dim) => (v: string | null) => setF((cur) => ({ ...cur, [dim]: cur[dim] === v ? null : v }));
  /** Filas filtradas por todo excepto `except` (para que cada gráfico muestre su propia selección). */
  const rowsExcept = (except?: Dim) => all.filter((r) => (Object.keys(f) as Dim[]).every((d) => d === except || !f[d] || MATCH[d](r, f[d]!)));
  const rows = rowsExcept();
  const active = (Object.keys(f) as Dim[]).filter((d) => f[d]);

  const months = useMemo(() => {
    const now = new Date();
    return Array.from({ length: 6 }, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() - 5 + i, 1);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    });
  }, []);

  const kpiRows = rowsExcept("status");
  const kpiCount = (k: string | null) => k === null ? kpiRows.length : kpiRows.filter((r) => MATCH.status(r, k)).length;
  const closedRows = kpiRows.filter((r) => statusOf(r) === "closed");
  const avgClose = closedRows.length ? Math.round(closedRows.reduce((s, r) => s + r.days_open, 0) / closedRows.length) : null;
  const trendRows = rowsExcept("month");
  const trend = months.map((m) => ({ month: m, opened: trendRows.filter((r) => r.month === m).length,
    closed: trendRows.filter((r) => r.closed_on?.startsWith(m)).length }));
  const milestones = MS_ROWS.map(([key, label]) => {
    const counts: Record<string, number> = {};
    for (const r of rows) { const m = r.milestones.find((x) => x.key === key); if (m) counts[m.status] = (counts[m.status] ?? 0) + 1; }
    return { label, counts };
  });
  const chip = (d: Dim) => d === "status" ? (f.status === "overdue" ? "Vencidos" : STATUS[f.status!].label)
    : d === "type" ? CASE_TYPE[f.type!] : d === "month" ? monthLabel(f.month!) : f[d]!;

  return (
    <>
      <div className="page-head">
        <div><h1>Dashboard</h1><div className="sub">Hola, {me.user.display_name.split(" ")[0]} · Haz clic en cualquier gráfico para filtrar todo el tablero</div></div>
        <div className="actions"><Link className="btn primary" href="/casos?nuevo=1">+ Nuevo 8D</Link></div>
      </div>
      <ErrorBox error={reg.error} onRetry={reg.reload} />
      {reg.loading && !reg.data ? <Loading rows={6} /> : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <span className="seg" role="group" aria-label="Tipo de 8D">
              {([[null, "Todos"], ["external", "Externos"], ["internal", "Internos"]] as const).map(([k, l]) => (
                <button key={l} type="button" className={f.type === k ? "on" : ""} aria-pressed={f.type === k} onClick={() => setF({ ...f, type: k })}>{l}</button>))}
            </span>
            {active.filter((d) => d !== "type").map((d) => (
              <span key={d} className="fchip">{LABEL[d]}: {chip(d)}
                <button type="button" aria-label={`Quitar filtro ${LABEL[d]}`} onClick={() => setF({ ...f, [d]: null })}>×</button></span>))}
            {active.length > 0 && <>
              <span className="small muted">Mostrando {rows.length} de {all.length} 8D</span>
              <button type="button" className="btn sm" style={{ marginLeft: "auto" }} onClick={() => setF(NONE)}>Limpiar filtros</button></>}
          </div>

          <div className="grid g4">
            {KPIS.map((k) => {
              const on = f.status === k.key || (k.key === null && !f.status);
              return (
                <button key={k.label} type="button" className={`card kpi${on && f.status ? " on" : ""}`} aria-pressed={on}
                  onClick={() => setF({ ...f, status: k.key === null || f.status === k.key ? null : k.key })}
                  style={{ padding: 18, display: "flex", gap: 16, alignItems: "center", opacity: f.status && !on ? 0.6 : 1 }}>
                  <span style={{ width: 56, height: 56, borderRadius: "50%", background: k.bg, color: k.fg, display: "grid", placeItems: "center", fontSize: 24, fontWeight: 800, flex: "none" }} aria-hidden>{k.icon}</span>
                  <span>
                    <span className="muted" style={{ display: "block" }}>{k.label}</span>
                    <span style={{ display: "block", fontSize: 32, fontWeight: 750, lineHeight: 1.1, color: k.key === "overdue" && kpiCount("overdue") ? "var(--bad)" : undefined }}>{kpiCount(k.key)}</span>
                    <span className="small muted">
                      {k.key === null && `${kpiRows.filter((r) => r.case_type === "external").length} externos · ${kpiRows.filter((r) => r.case_type === "internal").length} internos`}
                      {k.key === "in_process" && "Clic para ver los abiertos"}
                      {k.key === "closed" && (avgClose !== null ? `Promedio ${avgClose} días para cerrar` : "Sin cierres")}
                      {k.key === "overdue" && "Hito o fecha objetivo vencidos"}
                    </span>
                  </span>
                </button>);
            })}
          </div>

          <div className="grid dash3">
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>Estado de los 8D</h2>
              <Donut label="Estado de los 8D" total={rows.length} selected={f.status} onSelect={toggle("status")}
                data={Object.entries(STATUS).map(([key, s]) => ({ key, label: s.label, color: s.color, n: rowsExcept("status").filter((r) => statusOf(r) === key).length }))} />
            </div>
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>8D por cliente</h2>
              <HBars data={count(rowsExcept("customer"), customerOf)} selected={f.customer} onSelect={toggle("customer")} /></div>
            <div className="card card-pad"><h2 style={{ marginBottom: 8 }}>Abiertos vs. cerrados por mes</h2>
              <Trend data={trend} selected={f.month} onSelect={toggle("month")} />
              <div className="small muted">Clic en un mes: 8D trabajados en ese mes.</div></div>
          </div>

          <div className="grid dash3b">
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>Defecto principal</h2>
              <HBars data={count(rowsExcept("defect"), (r) => r.main_defect ?? "Sin defecto")} color={SERIES[1]} selected={f.defect} onSelect={toggle("defect")} /></div>
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>8D por responsable</h2>
              <HBars data={count(rowsExcept("leader"), leaderOf)} color={SERIES[2]} selected={f.leader} onSelect={toggle("leader")} /></div>
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>Cumplimiento de hitos</h2>
              <MilestoneBars data={milestones} colors={MS_COLORS} labels={MILESTONE_STATUS} /></div>
          </div>

          <div className="card">
            <div className="card-head"><h2>Mis tareas</h2>
              {(dash.data?.attention.actions_pending_approval ?? 0) > 0 && <span className="badge amber right">{dash.data!.attention.actions_pending_approval} por aprobar</span>}</div>
            {!dash.data?.my_tasks.length ? <Empty title="Sin pendientes">No tienes tareas asignadas.</Empty> : (
              <div className="stack" style={{ padding: "8px 18px 16px", gap: 4, maxHeight: 300, overflowY: "auto" }}>
                {dash.data.my_tasks.map((t, i) => {
                  const s = TASK[t.kind] ?? TASK.action;
                  return (
                    <Link key={i} href={`/casos/${t.case_id}`} className="row" style={{ gap: 12, padding: "8px 0", borderBottom: "1px solid var(--line-2)", color: "inherit", textDecoration: "none", flexWrap: "nowrap" }}>
                      <span style={{ width: 34, height: 34, borderRadius: "50%", background: s.bg, color: s.fg, display: "grid", placeItems: "center", fontWeight: 800, flex: "none" }} aria-hidden>{s.icon}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.label}</div>
                        <div className="small muted">{s.verb} · {t.folio}</div>
                      </span>
                      <span className="small" style={{ color: t.overdue ? "var(--bad)" : "var(--muted)", fontWeight: t.overdue ? 700 : 400, whiteSpace: "nowrap" }}>{t.due ? fmtDate(t.due) : ""}</span>
                    </Link>);
                })}
              </div>)}
          </div>
        </div>
      )}
    </>
  );
}
