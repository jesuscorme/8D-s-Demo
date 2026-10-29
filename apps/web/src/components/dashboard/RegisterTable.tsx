"use client";

import Link from "next/link";
import { CASE_TYPE, MILESTONE_STATUS, fmtDate } from "@/lib/labels";
import type { RegisterRow } from "@/lib/types";
import { Badge } from "@/components/ui";

const TONE: Record<string, string> = { on_time: "green", late: "amber", pending: "blue", overdue: "red" };
const STATUS_TONE: Record<string, string> = { closed: "green", approved: "green", pending_review: "amber", cancelled: "", in_progress: "blue", open: "blue", draft: "" };
const COLS = [["containment", "D3 · 24 h", "Contención"], ["root_cause", "D4 · 48 h", "Causa raíz"],
  ["actions", "D5–D7 · 7 días", "Acciones"], ["close", "D8 · 14 días", "Cierre"]] as const;

/** Concentrado de 8D con hitos (misma estructura que la hoja de control de calidad). */
export function RegisterTable({ rows, compact = false }: { rows: RegisterRow[]; compact?: boolean }) {
  return (
    <div className="table-wrap" style={{ maxHeight: compact ? 460 : 720, overflowY: "auto" }}>
      <table style={{ fontSize: 13 }}>
        <thead style={{ position: "sticky", top: 0, zIndex: 1 }}>
          <tr>
            <th>#</th><th>Mes</th><th>Reporte</th><th>Tipo</th><th>Cliente</th><th>Descripción de la falla</th>
            {!compact && <th>OEM | OES | AM</th>}<th>Defecto</th><th>No. de parte</th>{!compact && <th>Cant.</th>}<th>Causa raíz</th>
            <th>Cierre</th><th>Líder</th><th>Estado 8D</th>
            {COLS.map(([k, label, sub]) => <th key={k} style={{ textAlign: "center" }}>{label}<div style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>{sub}</div></th>)}
            <th style={{ textAlign: "right" }}>Días</th>
          </tr>
        </thead>
        <tbody>
          {!rows.length && <tr><td colSpan={20} className="muted">Sin 8D para los filtros elegidos.</td></tr>}
          {rows.map((r, i) => {
            const ms = Object.fromEntries(r.milestones.map((m) => [m.key, m]));
            return (
              <tr key={r.id}>
                <td className="muted">{rows.length - i}</td>
                <td>{r.month}</td>
                <td style={{ whiteSpace: "nowrap" }}><Link href={`/casos/${r.id}`} className="mono">{r.folio}</Link><div className="muted">{fmtDate(r.report_date)}</div></td>
                <td><Badge tone={r.case_type === "external" ? "red" : "blue"}>{CASE_TYPE[r.case_type]}</Badge></td>
                <td>{r.customer_name ?? "—"}</td>
                <td style={{ minWidth: 200 }}>{r.title}{r.is_demo && <> <Badge tone="amber">Demo</Badge></>}</td>
                {!compact && <td>{r.market_segment ?? "—"}</td>}
                <td>{r.main_defect ?? "—"}</td>
                <td className="mono">{r.part_number ?? "—"}</td>
                {!compact && <td>{r.detected_quantity ?? "—"}</td>}
                <td style={{ minWidth: 180, background: r.root_cause ? "#fff8e6" : undefined }}>{r.root_cause ?? <span className="muted">—</span>}</td>
                <td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.closed_on)}</td>
                <td>{r.leader ?? "—"}</td>
                <td><Badge tone={STATUS_TONE[r.status] ?? ""}>{r.status_label}</Badge>{r.current_discipline && r.status !== "closed" && <div className="small muted">{r.current_discipline}</div>}</td>
                {COLS.map(([k]) => {
                  const m = ms[k];
                  if (!m) return <td key={k} className="muted" style={{ textAlign: "center" }}>—</td>;
                  return (
                    <td key={k} style={{ textAlign: "center", whiteSpace: "nowrap" }} title={`Meta ${fmtDate(m.due)}${m.done ? ` · cumplido ${fmtDate(m.done)}` : ""}`}>
                      <Badge tone={TONE[m.status]}>{MILESTONE_STATUS[m.status]}</Badge>
                      <div className="small muted">{m.done ? fmtDate(m.done) : `meta ${fmtDate(m.due)}`}</div>
                    </td>);
                })}
                <td style={{ textAlign: "right", fontWeight: 700, color: r.overdue ? "var(--bad)" : undefined }}>{r.days_open}</td>
              </tr>);
          })}
        </tbody>
      </table>
    </div>
  );
}
