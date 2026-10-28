"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { ALERT_STATUS, CONTAINMENT_STATUS, fmtDate } from "@/lib/labels";
import type { Alert, AlertSummary, Containment, User } from "@/lib/types";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";

const TONE: Record<string, string> = { open: "", in_progress: "blue", implemented: "amber", verified: "green", cancelled: "red" };
const NEXT: Record<string, { to: string; label: string }[]> = {
  open: [{ to: "in_progress", label: "Iniciar" }, { to: "implemented", label: "Marcar implementada" }],
  in_progress: [{ to: "implemented", label: "Marcar implementada" }],
  implemented: [{ to: "verified", label: "Verificar" }],
  verified: [],
  cancelled: [],
};

export function UploadButton({ caseId, extra, onDone, label = "Adjuntar evidencia", accept = "image/png,image/jpeg,application/pdf", purpose = "evidence" }: {
  caseId: string; extra?: Record<string, string>; onDone: () => void; label?: string; accept?: string; purpose?: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("purpose", purpose);
    for (const [k, v] of Object.entries(extra ?? {})) form.append(k, v);
    try {
      await api(`/cases/${caseId}/attachments`, { form });
      onDone();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="row" style={{ gap: 6 }}>
      <label className="btn sm" style={{ cursor: busy ? "wait" : "pointer" }}>
        {busy ? "Subiendo…" : label}
        <input type="file" accept={accept} hidden disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
      </label>
      {error && <span className="small" style={{ color: "var(--bad)" }}>{error}</span>}
    </span>
  );
}

function ActionForm({ caseId, onClose, onSaved }: { caseId: string; onClose: () => void; onSaved: () => void }) {
  const users = useApi<User[]>("/users");
  const [f, setF] = useState({ description: "", location: "", responsible_user_id: "", due_date: "", quantity_checked: "", quantity_rejected: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "").map(([k, v]) => [k, k.startsWith("quantity") ? Number(v) : v]));
      await api(`/cases/${caseId}/containment`, { body });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title="Nueva acción de contención" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Acción" required><textarea value={f.description} onChange={set("description")} required minLength={3} placeholder="p. ej. Inspección 100% del inventario en almacén y tránsito" /></Field>
        <div className="grid g2">
          <Field label="Ubicación"><input value={f.location} onChange={set("location")} placeholder="Almacén, línea, cliente…" /></Field>
          <Field label="Responsable"><select value={f.responsible_user_id} onChange={set("responsible_user_id")}>
            <option value="">Seleccionar…</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
          <Field label="Vencimiento"><input type="date" value={f.due_date} onChange={set("due_date")} /></Field>
          <div className="grid g2">
            <Field label="Piezas revisadas"><input type="number" min={0} value={f.quantity_checked} onChange={set("quantity_checked")} /></Field>
            <Field label="Rechazadas"><input type="number" min={0} value={f.quantity_rejected} onChange={set("quantity_rejected")} /></Field>
          </div>
        </div>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Registrar</button></div>
      </form>
    </Modal>
  );
}

function TransitionForm({ action, to, onClose, onSaved }: { action: Containment; to: string; onClose: () => void; onSaved: () => void }) {
  const [evidence, setEvidence] = useState(action.evidence_notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const needs = to === "implemented" || to === "verified";
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const body: Record<string, string> = { status: to };
      if (needs && evidence !== (action.evidence_notes ?? "") && action.status !== "implemented") body.evidence_notes = evidence;
      await api(`/containment/${action.id}`, { method: "PATCH", body });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title={`${CONTAINMENT_STATUS[to]}: ${action.description.slice(0, 60)}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        {needs && (
          <Field label="Evidencia" required hint="Describe la evidencia (registro, inspección, fotos). Puedes adjuntar archivos desde la tabla.">
            <textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} required disabled={action.status === "implemented"} />
          </Field>
        )}
        {to === "cancelled" && <p className="muted">La acción quedará cancelada y no podrá reactivarse.</p>}
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Volver</button>
          <button className={`btn right ${to === "cancelled" ? "danger" : "primary"}`}>Confirmar</button></div>
      </form>
    </Modal>
  );
}

export function ContainmentPanel({ caseId, editable, onChanged }: { caseId: string; editable: boolean; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi<Containment[]>(`/cases/${caseId}/containment`);
  const [adding, setAdding] = useState(false);
  const [transition, setTransition] = useState<{ action: Containment; to: string } | null>(null);
  const refresh = () => { void reload(); onChanged(); };

  return (
    <div className="card">
      <div className="card-head"><h2>Acciones de contención</h2>
        {editable && <div className="right"><button className="btn primary sm" onClick={() => setAdding(true)}>+ Acción</button></div>}</div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <div className="card-pad"><Loading rows={2} /></div> : !data?.length ? (
        <Empty title="Sin acciones de contención">Registra cómo se protege al cliente mientras se investiga.</Empty>
      ) : (
        <div className="table-wrap"><table>
          <thead><tr><th>Acción</th><th>Responsable</th><th>Vence</th><th>Rev./Rech.</th><th>Evidencia</th><th>Estado</th><th></th></tr></thead>
          <tbody>{data.map((a) => (
            <tr key={a.id}>
              <td>{a.description}{a.location && <div className="small muted">{a.location}</div>}</td>
              <td>{a.responsible_name ?? "—"}</td>
              <td>{fmtDate(a.due_date)}{a.overdue && <div><Badge tone="red">Vencida</Badge></div>}</td>
              <td>{a.quantity_checked ?? "—"} / {a.quantity_rejected ?? "—"}</td>
              <td style={{ maxWidth: 260 }}>{a.evidence_notes ?? <span className="muted">—</span>}
                <div className="small muted">{a.attachment_count} archivo(s){a.verified_by_name && ` · verificó ${a.verified_by_name}`}</div></td>
              <td><Badge tone={TONE[a.status]}>{CONTAINMENT_STATUS[a.status]}</Badge></td>
              <td>{editable && (
                <div className="stack" style={{ gap: 4, alignItems: "flex-start" }}>
                  {NEXT[a.status].map((n) => <button key={n.to} className="btn sm" onClick={() => setTransition({ action: a, to: n.to })}>{n.label}</button>)}
                  {!["verified", "cancelled"].includes(a.status) && <UploadButton caseId={caseId} extra={{ containment_id: a.id }} onDone={refresh} label="Adjuntar" />}
                  {a.status !== "cancelled" && <button className="btn sm danger" onClick={() => setTransition({ action: a, to: "cancelled" })}>Cancelar</button>}
                </div>)}
              </td>
            </tr>))}
          </tbody>
        </table></div>
      )}
      {adding && <ActionForm caseId={caseId} onClose={() => setAdding(false)} onSaved={refresh} />}
      {transition && <TransitionForm {...transition} onClose={() => setTransition(null)} onSaved={refresh} />}
    </div>
  );
}

export function CaseAlerts({ caseId, open }: { caseId: string; open: boolean }) {
  const router = useRouter();
  const canEdit = useCan("alert.edit");
  const { data, error, reload } = useApi<AlertSummary[]>(`/cases/${caseId}/alerts`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function create(failure_type: string) {
    setBusy(true);
    try {
      const a = await api<Alert>(`/cases/${caseId}/alerts`, { body: { failure_type } });
      router.push(`/alertas/${a.id}`);
    } catch (e) {
      setErr(errorText(e));
      setBusy(false);
    }
  }
  return (
    <div className="card">
      <div className="card-head"><h2>Alerta de calidad</h2>
        {canEdit && open && <div className="right row">
          <button className="btn sm" disabled={busy} onClick={() => create("internal")}>+ Alerta interna</button>
          <button className="btn sm" disabled={busy} onClick={() => create("external")}>+ Alerta externa</button></div>}</div>
      <ErrorBox error={error ?? err} onRetry={reload} />
      {!data?.length ? <Empty title="Sin alertas">La alerta se prellena con los datos del caso y la contención.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Folio</th><th>Rev.</th><th>Tipo</th><th>Título</th><th>Estado</th><th>Emitida</th><th>PDF</th></tr></thead>
          <tbody>{data.map((a) => (
            <tr key={a.id}>
              <td className="mono"><Link href={`/alertas/${a.id}`}>{a.folio}</Link></td><td>{a.revision}</td>
              <td>{a.failure_type === "external" ? "Externa" : "Interna"}</td><td>{a.title}</td>
              <td><Badge tone={a.status === "issued" ? "green" : a.status === "draft" ? "blue" : ""}>{ALERT_STATUS[a.status]}</Badge></td>
              <td className="small">{fmtDate(a.issued_at, true)}</td>
              <td>{a.document_id ? <a href={`/api/documents/${a.document_id}/content`} target="_blank" rel="noreferrer">Abrir</a> : "—"}</td>
            </tr>))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
