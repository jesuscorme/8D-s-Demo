"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/labels";
import type { RegisterRow } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { useMe } from "@/components/Shell";
import { Donut, HBars, SERIES, Trend } from "@/components/dashboard/Charts";
import { RegisterTable } from "@/components/dashboard/RegisterTable";

type Task = { kind: string; label: string; case_id: string; folio: string; due: string | null; overdue: boolean };
type Dashboard = {
  totals: { total: number; in_process: number; closed: number; overdue: number };
  by_type: { internal: number; external: number };
  status_groups: { key: string; label: string; n: number }[];
  by_customer: { label: string; n: number }[];
  trend: { month: string; opened: number; closed: number }[];
  recent: { id: string; folio: string; customer: string | null; title: string; status: string; status_label: string; overdue: boolean; due: string | null; is_demo: boolean }[];
  my_tasks: Task[];
  attention: { actions_overdue: number; actions_pending_approval: number; actions_ineffective: number; criteria_pending: number; lessons_pending: number; cases_overdue: number };
};

const KPIS = [
  { key: "total", label: "8D total", icon: "▤", bg: "#e8f1fd", fg: "#1d6fe0" },
  { key: "in_process", label: "En proceso", icon: "◔", bg: "#fff4df", fg: "#b26a00" },
  { key: "closed", label: "Cerrados", icon: "✓", bg: "#e6f5ec", fg: "#1f8a4c" },
  { key: "overdue", label: "Vencidos", icon: "!", bg: "#fdecec", fg: "#c62828" },
] as const;
const STATUS_COLOR: Record<string, string> = { in_process: SERIES[0], review: SERIES[1], closed: SERIES[2] };
const TASK: Record<string, { icon: string; bg: string; fg: string; verb: string }> = {
  action: { icon: "A", bg: "#e8f1fd", fg: "#1d6fe0", verb: "Implementar acción" },
  containment: { icon: "C", bg: "#fff4df", fg: "#b26a00", verb: "Contención" },
  review: { icon: "R", bg: "#efeafd", fg: "#6250d6", verb: "Revisión" },
  approve_action: { icon: "✓", bg: "#e6f5ec", fg: "#1f8a4c", verb: "Aprobación" },
};
const PILL: Record<string, string> = { closed: "green", approved: "green", pending_review: "amber", in_progress: "blue", open: "blue", draft: "" };

export default function Home() {
  const me = useMe();
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard");
  const reg = useApi<{ rows: RegisterRow[] }>("/reports/register");

  return (
    <>
      <div className="page-head">
        <div><h1>Dashboard</h1><div className="sub">Hola, {me.user.display_name.split(" ")[0]} · Seguimiento de 8D internos y externos</div></div>
        <div className="actions"><Link className="btn" href="/concentrado">Concentrado</Link><Link className="btn primary" href="/casos?nuevo=1">+ Nuevo 8D</Link></div>
      </div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading rows={6} /> : data && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid g4">
            {KPIS.map((k) => (
              <div key={k.key} className="card" style={{ padding: 18, display: "flex", gap: 16, alignItems: "center" }}>
                <div style={{ width: 56, height: 56, borderRadius: "50%", background: k.bg, color: k.fg, display: "grid", placeItems: "center", fontSize: 24, fontWeight: 800 }} aria-hidden>{k.icon}</div>
                <div>
                  <div className="muted">{k.label}</div>
                  <div style={{ fontSize: 32, fontWeight: 750, lineHeight: 1.1, color: k.key === "overdue" && data.totals.overdue ? "var(--bad)" : undefined }}>{data.totals[k.key]}</div>
                  {k.key === "total" && <div className="small muted">{data.by_type.external} externos · {data.by_type.internal} internos</div>}
                  {k.key === "overdue" && <div className="small muted">Hito o fecha objetivo vencidos</div>}
                </div>
              </div>))}
          </div>

          <div className="grid dash3">
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>Estado de los 8D</h2>
              <Donut label="Estado de los 8D" total={data.totals.total}
                data={data.status_groups.map((g) => ({ label: g.label, n: g.n, color: STATUS_COLOR[g.key] }))} />
            </div>
            <div className="card card-pad"><h2 style={{ marginBottom: 14 }}>8D por cliente</h2><HBars data={data.by_customer} /></div>
            <div className="card card-pad"><h2 style={{ marginBottom: 8 }}>Abiertos vs. cerrados · 6 meses</h2><Trend data={data.trend} /></div>
          </div>

          <div className="grid dash2">
            <div className="card">
              <div className="card-head"><h2>8D recientes</h2><Link className="right small" href="/casos">Ver todos</Link></div>
              {!data.recent.length ? <Empty title="Aún no hay 8D">Crea el primero con «Nuevo 8D».</Empty> : (
                <div className="table-wrap"><table>
                  <thead><tr><th>No. 8D</th><th>Cliente</th><th>Descripción del problema</th><th>Estado</th><th>Fecha límite</th></tr></thead>
                  <tbody>{data.recent.map((r) => (
                    <tr key={r.id}>
                      <td className="mono"><Link href={`/casos/${r.id}`}>{r.folio}</Link></td>
                      <td>{r.customer ?? "—"}</td>
                      <td>{r.title}{r.is_demo && <> <Badge tone="amber">Demo</Badge></>}</td>
                      <td><Badge tone={r.overdue ? "red" : PILL[r.status] ?? ""}>{r.overdue ? "Vencido" : r.status_label}</Badge></td>
                      <td style={{ color: r.overdue ? "var(--bad)" : undefined, whiteSpace: "nowrap" }}>
                        {r.status === "closed" ? <span className="muted">Cerrado</span> : fmtDate(r.due)}</td>
                    </tr>))}</tbody>
                </table></div>
              )}
            </div>
            <div className="card">
              <div className="card-head"><h2>Mis tareas</h2>
                {data.attention.actions_pending_approval > 0 && <span className="badge amber right">{data.attention.actions_pending_approval} por aprobar</span>}</div>
              {!data.my_tasks.length ? <Empty title="Sin pendientes">No tienes tareas asignadas.</Empty> : (
                <div className="stack" style={{ padding: "8px 18px 16px", gap: 4 }}>
                  {data.my_tasks.map((t, i) => {
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
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-head"><h2>Concentrado de 8D</h2><span className="small muted">Hitos: D3 24 h · D4 48 h · D5–D7 7 días · D8 14 días desde el reporte</span>
              <Link className="right small" href="/concentrado">Ver completo y exportar</Link></div>
            <ErrorBox error={reg.error} onRetry={reg.reload} />
            {reg.loading && !reg.data ? <div className="card-pad"><Loading rows={3} /></div> : <RegisterTable rows={reg.data?.rows.slice(0, 12) ?? []} compact />}
          </div>
        </div>
      )}
    </>
  );
}
