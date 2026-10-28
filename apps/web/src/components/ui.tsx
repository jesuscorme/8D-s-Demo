"use client";

import type { ReactNode } from "react";
import { CASE_STATUS, SEVERITY } from "@/lib/labels";

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ height: 38 }} />)}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="notice error row" role="alert">
      <span>{error}</span>
      {onRetry && <button className="btn sm right" onClick={onRetry}>Reintentar</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><b>{title}</b>{children}</div>;
}

const STATUS_TONE: Record<string, string> = {
  draft: "", open: "blue", in_progress: "blue", pending_review: "amber", approved: "green", closed: "green", cancelled: "red",
};
const SEV_TONE: Record<string, string> = { low: "", medium: "blue", high: "amber", critical: "red" };

export function CaseStatus({ status }: { status: string }) {
  return <span className={`badge ${STATUS_TONE[status] ?? ""}`}>{CASE_STATUS[status] ?? status}</span>;
}

export function Severity({ value }: { value: string }) {
  return <span className={`badge ${SEV_TONE[value] ?? ""}`}>{SEVERITY[value] ?? value}</span>;
}

export function Badge({ tone = "", children }: { tone?: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Field({ label, required, children, hint }: { label: string; required?: boolean; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}{required && <span className="req"> *</span>}</span>
      {children}
      {hint && <span className="small muted" style={{ fontWeight: 400 }}>{hint}</span>}
    </label>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card modal" role="dialog" aria-label={title}>
        <div className="card-head"><h2>{title}</h2><button className="btn ghost sm right" onClick={onClose} aria-label="Cerrar">✕</button></div>
        <div className="card-pad">{children}</div>
      </div>
    </div>
  );
}

/** Página de un módulo de una fase posterior: explícitamente no disponible, sin datos simulados. */
export function NotAvailable({ title, phase, description }: { title: string; phase: string; description: string }) {
  return (
    <>
      <div className="page-head"><div><h1>{title}</h1><div className="sub">{phase}</div></div></div>
      <div className="card"><Empty title="Módulo no disponible en esta versión">
        <p style={{ maxWidth: 520, margin: "6px auto 0" }}>{description}</p>
      </Empty></div>
    </>
  );
}
