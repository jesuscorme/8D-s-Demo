"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/labels";
import { CaseStatus, Empty, ErrorBox, Loading, Severity } from "@/components/ui";
import { useMe } from "@/components/Shell";

type Dashboard = {
  by_status: Record<string, number>;
  overdue_containment: number;
  pending_review: number;
  issued_alerts: number;
  my_cases: { id: string; folio: string; title: string; status: string; severity: string; updated_at: string }[];
  attention: { actions_overdue: number; actions_pending_approval: number; actions_ineffective: number; criteria_pending: number; lessons_pending: number; cases_overdue: number };
  attention_items: { kind: string; id: string; case_id: string; folio: string; title: string; status: string; due_date: string | null; overdue: boolean }[];
};

const ATTENTION: [keyof Dashboard["attention"], string, string][] = [
  ["cases_overdue", "Casos vencidos", "red"], ["actions_overdue", "Acciones vencidas", "red"],
  ["actions_pending_approval", "Acciones pendientes de aprobación", "amber"], ["actions_ineffective", "Acciones no eficaces", "red"],
  ["criteria_pending", "Criterios de eficacia por aprobar", "amber"], ["lessons_pending", "Lecciones en revisión o por publicar", "amber"],
];

export default function Home() {
  const me = useMe();
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard");
  const open = data ? Object.entries(data.by_status).filter(([s]) => !["closed", "cancelled"].includes(s)).reduce((a, [, n]) => a + n, 0) : 0;

  return (
    <>
      <div className="page-head">
        <div><h1>Hola, {me.user.display_name.split(" ")[0]}</h1><div className="sub">Resumen de tus expedientes 8D</div></div>
        <div className="actions"><Link className="btn primary" href="/casos?nuevo=1">+ Nuevo caso</Link></div>
      </div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading rows={4} /> : data && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid g4">
            <div className="card kpi"><div className="l">Casos activos</div><div className="v">{open}</div></div>
            <div className="card kpi"><div className="l">Disciplinas en revisión</div><div className="v">{data.pending_review}</div></div>
            <div className="card kpi"><div className="l">Contenciones vencidas</div><div className="v" style={{ color: data.overdue_containment ? "var(--bad)" : undefined }}>{data.overdue_containment}</div></div>
            <div className="card kpi"><div className="l">Alertas vigentes</div><div className="v">{data.issued_alerts}</div></div>
          </div>
          {ATTENTION.some(([k]) => data.attention[k] > 0) && (
            <div className="card">
              <div className="card-head"><h2>Requiere atención</h2>
                <div className="right row">{ATTENTION.filter(([k]) => data.attention[k] > 0).map(([k, label, tone]) => (
                  <span key={k} className={`badge ${tone}`}>{label}: {data.attention[k]}</span>))}</div></div>
              {data.attention_items.length > 0 && <div className="table-wrap"><table><tbody>{data.attention_items.map((i) => (
                <tr key={`${i.kind}-${i.id}`}>
                  <td className="mono"><Link href={`/casos/${i.case_id}`}>{i.folio}</Link></td>
                  <td>{i.kind === "containment" ? "Contención" : "Acción"}: {i.title}</td>
                  <td>{i.overdue ? <span className="badge red">Vencida {fmtDate(i.due_date)}</span>
                    : <span className="badge amber">{i.status === "pending_approval" ? "Pendiente de aprobación" : "No eficaz"}</span>}</td>
                </tr>))}</tbody></table></div>}
            </div>
          )}
          <div className="card">
            <div className="card-head"><h2>Mis casos</h2><Link className="right small" href="/casos?mine=1">Ver todos</Link></div>
            {data.my_cases.length === 0 ? <Empty title="No tienes casos asignados">Crea un caso o pide que te agreguen a un equipo 8D.</Empty> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Folio</th><th>Título</th><th>Severidad</th><th>Estado</th><th>Actualizado</th></tr></thead>
                <tbody>{data.my_cases.map((c) => (
                  <tr key={c.id}>
                    <td className="mono"><Link href={`/casos/${c.id}`}>{c.folio}</Link></td>
                    <td>{c.title}</td><td><Severity value={c.severity} /></td><td><CaseStatus status={c.status} /></td>
                    <td className="muted">{fmtDate(c.updated_at, true)}</td>
                  </tr>))}
                </tbody>
              </table></div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
