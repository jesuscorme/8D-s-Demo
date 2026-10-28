"use client";

import Link from "next/link";
import { use, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { SOURCE, fmtDate } from "@/lib/labels";
import type { Case } from "@/lib/types";
import { Badge, CaseStatus, ErrorBox, Field, Loading, Modal, Severity } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { WorkflowTab } from "@/components/case/Workflow";
import { AuditTab, CommentsTab, FilesTab } from "@/components/case/Tabs";

const TABS = [["flow", "Flujo 8D"], ["files", "Documentos y archivos"], ["comments", "Comentarios"], ["audit", "Bitácora"]] as const;

function CancelDialog({ c, onClose, onDone }: { c: Case; onClose: () => void; onDone: (c: Case) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      onDone(await api<Case>(`/cases/${c.id}/cancel`, { body: { reason } }));
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title={`Cancelar ${c.folio}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Motivo" required><textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required /></Field>
        <p className="small muted">El caso quedará de solo lectura. La acción se registra en la bitácora.</p>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Volver</button><button className="btn danger right">Cancelar caso</button></div>
      </form>
    </Modal>
  );
}

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: c, setData, error, loading, reload } = useApi<Case>(`/cases/${id}`);
  const canCancel = useCan("case.cancel");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("flow");
  const [cancelling, setCancelling] = useState(false);

  if (loading && !c) return <Loading rows={6} />;
  if (error && !c) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return null;
  const open = !["cancelled", "closed"].includes(c.status);
  const approved = c.workflow.filter((d) => d.status === "approved").length;

  return (
    <>
      <div className="small muted" style={{ marginBottom: 6 }}><Link href="/casos">Casos 8D</Link> / {c.folio}</div>
      <div className="page-head">
        <div>
          <div className="row"><span className="mono badge navy">{c.folio}</span><CaseStatus status={c.status} /><Severity value={c.severity} />
            {c.is_demo && <Badge tone="amber">Datos de demostración</Badge>}</div>
          <h1 style={{ marginTop: 8 }}>{c.title}</h1>
          <div className="sub">
            {c.plant_code} — {c.plant_name} · Responsable: {c.owner_name ?? "—"} · {c.source_type ? SOURCE[c.source_type] : "Origen sin definir"}
            {c.part_number && ` · Parte ${c.part_number}`} · Abierto {fmtDate(c.created_at)} por {c.opened_by_name}
          </div>
        </div>
        <div className="actions">
          <div className="card" style={{ padding: "8px 14px", textAlign: "center" }}>
            <div className="small muted">Disciplinas aprobadas</div><b style={{ fontSize: 18 }}>{approved} / 9</b>
          </div>
          {open && canCancel && <button className="btn danger" onClick={() => setCancelling(true)}>Cancelar caso</button>}
        </div>
      </div>
      {c.status === "cancelled" && <div className="notice error" style={{ marginBottom: 12 }}>Caso cancelado: {c.cancel_reason}</div>}
      <ErrorBox error={error} onRetry={reload} />
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {tab === "flow" && <WorkflowTab c={c} setCase={setData} reload={reload} />}
      {tab === "files" && <FilesTab caseId={c.id} open={open} />}
      {tab === "comments" && <CommentsTab caseId={c.id} />}
      {tab === "audit" && <AuditTab caseId={c.id} />}
      {cancelling && <CancelDialog c={c} onClose={() => setCancelling(false)} onDone={setData} />}
    </>
  );
}
