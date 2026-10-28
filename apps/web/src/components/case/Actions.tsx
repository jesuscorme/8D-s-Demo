"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import {
  ACTION_STATUS, ACTION_TYPE, CRITERION_STATUS, EFFECT, LESSON_STATUS, OUTCOME, THRESHOLD, UPDATE_STATUS, UPDATE_TYPE, fmtDate,
} from "@/lib/labels";
import type { Action, Case, Cause, Check, Effectiveness, Lesson, SystemUpdate, User } from "@/lib/types";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { UploadButton } from "./Containment";

const ACTION_TONE: Record<string, string> = {
  open: "", in_progress: "blue", pending_approval: "amber", approved: "green", verified: "green", ineffective: "red", cancelled: "",
};
const EFFECT_TONE: Record<string, string> = { pending: "blue", effective: "green", ineffective: "red", insufficient_data: "amber" };

type Form = Record<string, string>;
const useForm = (init: Form) => {
  const [f, setF] = useState(init);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  return { f, setF, set };
};
const clean = (f: Form, numbers: string[] = []) =>
  Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "").map(([k, v]) => [k, numbers.includes(k) ? Number(v) : v]));

function Submitting({ title, onClose, onSubmit, children, danger }: {
  title: string; onClose: () => void; onSubmit: () => Promise<void>; children: React.ReactNode; danger?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <form className="stack" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try { await onSubmit(); onClose(); } catch (x) { setError(errorText(x)); } finally { setBusy(false); }
      }}>
        {children}
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className={`btn right ${danger ? "danger" : "primary"}`} disabled={busy}>{busy ? "Guardando…" : "Confirmar"}</button></div>
      </form>
    </Modal>
  );
}

function NewAction({ c, types, onClose, onSaved }: { c: Case; types: string[]; onClose: () => void; onSaved: (a: Action[]) => void }) {
  const users = useApi<User[]>("/users");
  const causes = useApi<Cause[]>(`/cases/${c.id}/causes`);
  const { f, set } = useForm({ action_type: types[0], cause_id: "", description: "", responsible_user_id: "", due_date: "" });
  const options = causes.data?.filter((x) => f.action_type !== "corrective" || x.investigation_status === "root_cause") ?? [];
  return (
    <Submitting title="Nueva acción" onClose={onClose} onSubmit={async () => onSaved(await api<Action[]>(`/cases/${c.id}/actions`, { body: clean(f) }))}>
      {types.length > 1 && <Field label="Tipo" required><select value={f.action_type} onChange={set("action_type")}>
        {types.map((t) => <option key={t} value={t}>{ACTION_TYPE[t]}</option>)}</select></Field>}
      <Field label={f.action_type === "corrective" ? "Causa raíz que elimina" : "Causa relacionada (opcional)"} required={f.action_type === "corrective"}
        hint={f.action_type === "corrective" ? "Solo causas confirmadas como causa raíz en D4." : undefined}>
        <select value={f.cause_id} onChange={set("cause_id")} required={f.action_type === "corrective"}>
          <option value="">{f.action_type === "corrective" ? "Seleccionar…" : "— Sin causa vinculada —"}</option>
          {options.map((x) => <option key={x.id} value={x.id}>{x.potential_cause}</option>)}
        </select></Field>
      <Field label="Acción" required><textarea value={f.description} onChange={set("description")} minLength={3} required /></Field>
      <div className="grid g2">
        <Field label="Responsable" required><select value={f.responsible_user_id} onChange={set("responsible_user_id")} required>
          <option value="">Seleccionar…</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
        <Field label="Fecha compromiso" required><input type="date" value={f.due_date} onChange={set("due_date")} required /></Field>
      </div>
    </Submitting>
  );
}

export function ActionsPanel({ c, types, canDefine, canExecute, title, onChanged }: {
  c: Case; types: string[]; canDefine: boolean; canExecute: boolean; title: string; onChanged: () => void;
}) {
  const canEdit = useCan("action.edit");
  const canApprove = useCan("action.approve");
  const { data, setData, error, loading, reload } = useApi<Action[]>(`/cases/${c.id}/actions`);
  const [adding, setAdding] = useState(false);
  const [dialog, setDialog] = useState<{ a: Action; kind: "submit" | "approve" | "reject" | "reopen" | "cancel" } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const list = data?.filter((a) => types.includes(a.action_type)) ?? [];
  const saved = (rows: Action[]) => { setData(rows); onChanged(); };
  async function start(a: Action) {
    try { saved(await api<Action[]>(`/actions/${a.id}/start`, { method: "POST" })); setErr(null); } catch (e) { setErr(errorText(e)); }
  }

  return (
    <div className="card">
      <div className="card-head"><h2>{title}</h2>
        {canDefine && canEdit && <div className="right"><button className="btn primary sm" onClick={() => setAdding(true)}>+ Acción</button></div>}</div>
      <ErrorBox error={error ?? err} onRetry={reload} />
      {loading && !data ? <div className="card-pad"><Loading rows={2} /></div> : !list.length ? (
        <Empty title="Sin acciones">{types.includes("corrective") ? "Cada causa raíz necesita al menos una acción correctiva." : "Registra acciones preventivas o sistémicas, o justifica por qué no aplican."}</Empty>
      ) : (
        <div className="table-wrap"><table>
          <thead><tr><th>Tipo</th><th>Acción</th><th>Causa</th><th>Responsable</th><th>Vence</th><th>Evidencia</th><th>Estado</th><th></th></tr></thead>
          <tbody>{list.map((a) => (
            <tr key={a.id}>
              <td><Badge tone="navy">{ACTION_TYPE[a.action_type]}</Badge></td>
              <td>{a.description}{a.review_comment && <div className="small muted">Revisión: «{a.review_comment}»</div>}</td>
              <td className="small">{a.cause_text ?? "—"}</td>
              <td>{a.responsible_name ?? "—"}</td>
              <td>{fmtDate(a.due_date)}{a.overdue && <div><Badge tone="red">Vencida</Badge></div>}</td>
              <td className="small" style={{ maxWidth: 240 }}>{a.implementation_evidence ?? (a.evidence_exception ? `Excepción: ${a.evidence_exception}` : "—")}
                <div className="muted">{a.attachment_count} archivo(s){a.approved_by_name && ` · aprobó ${a.approved_by_name}`}</div></td>
              <td><Badge tone={ACTION_TONE[a.status]}>{ACTION_STATUS[a.status]}</Badge>
                {a.latest_effectiveness && <div className="small muted">Eficacia: {EFFECT[a.latest_effectiveness]}</div>}</td>
              <td>{canExecute && (
                <div className="stack" style={{ gap: 4, alignItems: "flex-start" }}>
                  {canEdit && a.status === "open" && <button className="btn sm" onClick={() => start(a)}>Iniciar</button>}
                  {canEdit && ["open", "in_progress"].includes(a.status) && <button className="btn sm primary" onClick={() => setDialog({ a, kind: "submit" })}>Enviar a aprobación</button>}
                  {canApprove && a.status === "pending_approval" && <>
                    <button className="btn sm ok" onClick={() => setDialog({ a, kind: "approve" })}>Aprobar</button>
                    <button className="btn sm" onClick={() => setDialog({ a, kind: "reject" })}>Rechazar</button></>}
                  {canApprove && ["approved", "ineffective"].includes(a.status) && <button className="btn sm" onClick={() => setDialog({ a, kind: "reopen" })}>Reabrir</button>}
                  {canEdit && !["verified", "cancelled"].includes(a.status) && <UploadButton caseId={c.id} extra={{ action_id: a.id }} onDone={reload} label="Adjuntar" />}
                  {canApprove && ["open", "in_progress", "pending_approval", "ineffective"].includes(a.status) &&
                    <button className="btn sm danger" onClick={() => setDialog({ a, kind: "cancel" })}>Cancelar</button>}
                </div>)}
              </td>
            </tr>))}
          </tbody>
        </table></div>
      )}
      {adding && <NewAction c={c} types={types} onClose={() => setAdding(false)} onSaved={saved} />}
      {dialog && <ActionDialog {...dialog} onClose={() => setDialog(null)} onSaved={saved} />}
    </div>
  );
}

function ActionDialog({ a, kind, onClose, onSaved }: { a: Action; kind: string; onClose: () => void; onSaved: (r: Action[]) => void }) {
  const { f, set } = useForm({ implementation_evidence: "", evidence_exception: "", comment: "", reason: "" });
  const titles: Record<string, string> = { submit: "Enviar a aprobación", approve: "Aprobar implementación", reject: "Rechazar", reopen: "Reabrir acción", cancel: "Cancelar acción" };
  async function submit() {
    const body = kind === "submit" ? { implementation_evidence: f.implementation_evidence || null, evidence_exception: f.evidence_exception || null }
      : kind === "cancel" ? { reason: f.reason } : { comment: f.comment || null };
    onSaved(await api<Action[]>(`/actions/${a.id}/${kind}`, { body }));
  }
  return (
    <Submitting title={`${titles[kind]}: ${a.description.slice(0, 50)}`} onClose={onClose} onSubmit={submit} danger={kind === "cancel"}>
      {kind === "submit" && <>
        <Field label="Evidencia de implementación" hint="Orden de trabajo, registro, documento. Adjunta archivos desde la tabla."><textarea value={f.implementation_evidence} onChange={set("implementation_evidence")} /></Field>
        <Field label="…o excepción justificada" hint="Solo si no existe evidencia documental; quedará registrada."><textarea value={f.evidence_exception} onChange={set("evidence_exception")} /></Field>
      </>}
      {kind === "approve" && <p className="small muted">La aprobación debe hacerla una persona distinta de quien envió la acción ({a.submitted_by_name ?? "—"}).</p>}
      {["approve", "reject", "reopen"].includes(kind) && <Field label="Comentario" required={kind !== "approve"}><textarea value={f.comment} onChange={set("comment")} required={kind !== "approve"} /></Field>}
      {kind === "cancel" && <Field label="Motivo" required><textarea value={f.reason} onChange={set("reason")} minLength={5} required /></Field>}
    </Submitting>
  );
}

// ---- Eficacia (D6) --------------------------------------------------------------------------

function NewCriterion({ caseId, denominators, onClose, onSaved }: { caseId: string; denominators: Record<string, string>; onClose: () => void; onSaved: (e: Effectiveness) => void }) {
  const { f, set } = useForm({ description: "", metric_name: "", defect_unit: "piezas", denominator_type: "units_produced", denominator_label: "",
    threshold_type: "max_rate_ppm", threshold_value: "", min_period_days: "", min_denominator: "1" });
  return (
    <Submitting title="Nuevo criterio de aceptación" onClose={onClose}
      onSubmit={async () => onSaved(await api<Effectiveness>(`/cases/${caseId}/criteria`, { body: clean(f, ["threshold_value", "min_period_days", "min_denominator"]) }))}>
      <p className="small muted">Define el criterio para este caso (no se asume «cero defectos por 30 días»). Debe aprobarlo un gerente de calidad antes de usarse.</p>
      <Field label="Criterio" required><textarea value={f.description} onChange={set("description")} required minLength={3} placeholder="p. ej. Rebaba ≤ 100 ppm durante 30 días con producción" /></Field>
      <div className="grid g2">
        <Field label="Indicador" required><input value={f.metric_name} onChange={set("metric_name")} required placeholder="Piezas con rebaba" /></Field>
        <Field label="Unidad del defecto" required><input value={f.defect_unit} onChange={set("defect_unit")} required /></Field>
        <Field label="Denominador" required><select value={f.denominator_type} onChange={set("denominator_type")}>
          {Object.entries(denominators).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        {f.denominator_type === "other" && <Field label="Describe el denominador" required><input value={f.denominator_label} onChange={set("denominator_label")} required /></Field>}
        <Field label="Tipo de límite" required><select value={f.threshold_type} onChange={set("threshold_type")}>
          {Object.entries(THRESHOLD).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Límite" required><input type="number" min={0} step="any" value={f.threshold_value} onChange={set("threshold_value")} required /></Field>
        <Field label="Días mínimos con producción" required><input type="number" min={1} value={f.min_period_days} onChange={set("min_period_days")} required /></Field>
        <Field label="Denominador mínimo" required><input type="number" min={1} value={f.min_denominator} onChange={set("min_denominator")} required /></Field>
      </div>
    </Submitting>
  );
}

function NewCheck({ caseId, actions, criteria, onClose, onSaved }: { caseId: string; actions: Action[]; criteria: Effectiveness["criteria"]; onClose: () => void; onSaved: (e: Effectiveness) => void }) {
  const { f, set } = useForm({ action_id: actions[0]?.id ?? "", criterion_id: criteria[0]?.id ?? "", period_start: "", period_end: "",
    denominator_quantity: "", defect_quantity: "", days_without_production: "0", data_notes: "" });
  async function submit() {
    const { action_id, ...rest } = clean(f, ["denominator_quantity", "defect_quantity", "days_without_production"]);
    onSaved(await api<Effectiveness>(`/actions/${action_id}/checks`, { body: rest }));
  }
  void caseId;
  return (
    <Submitting title="Registrar verificación de eficacia" onClose={onClose} onSubmit={submit}>
      <Field label="Acción" required><select value={f.action_id} onChange={set("action_id")}>{actions.map((a) => <option key={a.id} value={a.id}>{a.description}</option>)}</select></Field>
      <Field label="Criterio aprobado" required><select value={f.criterion_id} onChange={set("criterion_id")}>{criteria.map((k) => <option key={k.id} value={k.id}>{k.description}</option>)}</select></Field>
      <div className="grid g2">
        <Field label="Inicio del periodo" required><input type="date" value={f.period_start} onChange={set("period_start")} required /></Field>
        <Field label="Fin del periodo" required><input type="date" value={f.period_end} onChange={set("period_end")} required max={new Date().toISOString().slice(0, 10)} /></Field>
        <Field label="Denominador (cantidad)" hint="Vacío = sin dato; no se toma como cero."><input type="number" min={0} value={f.denominator_quantity} onChange={set("denominator_quantity")} /></Field>
        <Field label="Defectos observados" hint="Vacío = sin dato; no se toma como cero."><input type="number" min={0} value={f.defect_quantity} onChange={set("defect_quantity")} /></Field>
        <Field label="Días sin producción en el periodo"><input type="number" min={0} value={f.days_without_production} onChange={set("days_without_production")} /></Field>
      </div>
      <Field label="Notas sobre los datos"><textarea value={f.data_notes} onChange={set("data_notes")} placeholder="Fuente, días faltantes, cambios de turno…" /></Field>
    </Submitting>
  );
}

function Decide({ check, onClose, onSaved }: { check: Check; onClose: () => void; onSaved: (e: Effectiveness) => void }) {
  const { f, set } = useForm({ result: check.allowed_decisions.includes(check.computed_result) ? check.computed_result : check.allowed_decisions[0], rationale: "" });
  return (
    <Submitting title="Registrar resultado" onClose={onClose} onSubmit={async () => onSaved(await api<Effectiveness>(`/checks/${check.id}/decide`, { body: f }))}>
      <div className="notice info small">Regla: <b>{EFFECT[check.computed_result]}</b> — {check.evaluation.reasons.join("; ")}</div>
      <Field label="Resultado" required><select value={f.result} onChange={set("result")}>{check.allowed_decisions.map((r) => <option key={r} value={r}>{EFFECT[r]}</option>)}</select></Field>
      <Field label="Justificación" required><textarea value={f.rationale} onChange={set("rationale")} minLength={5} required /></Field>
      <p className="small muted">El resultado no se puede modificar después; una nueva medición se registra como otra verificación.</p>
    </Submitting>
  );
}

export function EffectivenessPanel({ c, editable, onChanged }: { c: Case; editable: boolean; onChanged: () => void }) {
  const canEdit = useCan("effectiveness.edit") && editable;
  const canApprove = useCan("criteria.approve") && editable;
  const eff = useApi<Effectiveness>(`/cases/${c.id}/effectiveness`);
  const actions = useApi<Action[]>(`/cases/${c.id}/actions`);
  const [modal, setModal] = useState<"criterion" | "check" | Check | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const saved = (e: Effectiveness) => { eff.setData(e); void actions.reload(); onChanged(); };
  async function criterion(id: string, op: "approve" | "retire") {
    try { saved(await api<Effectiveness>(`/criteria/${id}/${op}`, { method: "POST" })); setErr(null); } catch (e) { setErr(errorText(e)); }
  }
  const implemented = actions.data?.filter((a) => ["approved", "verified", "ineffective"].includes(a.status)) ?? [];
  const approvedCriteria = eff.data?.criteria.filter((k) => k.status === "approved") ?? [];
  if (eff.loading && !eff.data) return <Loading rows={3} />;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <ErrorBox error={eff.error ?? err} onRetry={eff.reload} />
      <div className="card">
        <div className="card-head"><h2>Criterios de aceptación</h2>
          {canEdit && <div className="right"><button className="btn sm primary" onClick={() => setModal("criterion")}>+ Criterio</button></div>}</div>
        {!eff.data?.criteria.length ? <Empty title="Sin criterios">Define y aprueba cómo se juzgará la eficacia antes de medirla.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Criterio</th><th>Indicador / denominador</th><th>Límite</th><th>Periodo y mínimo</th><th>Estado</th><th></th></tr></thead>
            <tbody>{eff.data.criteria.map((k) => (
              <tr key={k.id}>
                <td>{k.description}</td>
                <td className="small">{k.metric_name} ({k.defect_unit}) / {k.denominator_label ?? eff.data!.denominators[k.denominator_type]}</td>
                <td className="small">{THRESHOLD[k.threshold_type]}: {Number(k.threshold_value)}</td>
                <td className="small">{k.min_period_days} días con producción · mín. {k.min_denominator}</td>
                <td><Badge tone={k.status === "approved" ? "green" : k.status === "draft" ? "blue" : ""}>{CRITERION_STATUS[k.status]}</Badge>
                  {k.approved_by_name && <div className="small muted">{k.approved_by_name}</div>}</td>
                <td>{canApprove && k.status === "draft" && <button className="btn sm ok" onClick={() => criterion(k.id, "approve")}>Aprobar</button>}
                  {canApprove && k.status === "approved" && <button className="btn sm" onClick={() => criterion(k.id, "retire")}>Retirar</button>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      <div className="card">
        <div className="card-head"><h2>Verificaciones de eficacia</h2>
          {canEdit && <div className="right"><button className="btn sm primary" disabled={!implemented.length || !approvedCriteria.length}
            title={!implemented.length ? "Requiere acciones implementadas y aprobadas" : !approvedCriteria.length ? "Requiere un criterio aprobado" : ""}
            onClick={() => setModal("check")}>+ Verificación</button></div>}</div>
        {!eff.data?.checks.length ? <Empty title="Sin verificaciones">Registra periodo, denominador y defectos de cada acción implementada.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Acción</th><th>Periodo</th><th>Defectos / denominador</th><th>Regla</th><th>Resultado</th><th></th></tr></thead>
            <tbody>{eff.data.checks.map((e) => (
              <tr key={e.id}>
                <td>{e.action_description}</td>
                <td className="small">{fmtDate(e.period_start)} – {fmtDate(e.period_end)}{e.days_without_production > 0 && <div className="muted">{e.days_without_production} día(s) sin producción</div>}</td>
                <td className="small">{e.defect_quantity ?? <b>sin dato</b>} / {e.denominator_quantity ?? <b>sin dato</b>}{e.data_notes && <div className="muted">{e.data_notes}</div>}</td>
                <td className="small"><Badge tone={EFFECT_TONE[e.computed_result]}>{EFFECT[e.computed_result]}</Badge><div className="muted">{e.evaluation.reasons.join("; ")}</div></td>
                <td><Badge tone={EFFECT_TONE[e.result]}>{EFFECT[e.result]}</Badge>
                  {e.rationale && <div className="small muted">{e.rationale}{e.decided_by_name && ` — ${e.decided_by_name}`}</div>}
                  <div className="small muted">{e.attachment_count} archivo(s)</div></td>
                <td>{canEdit && e.result === "pending" && <div className="stack" style={{ gap: 4, alignItems: "flex-start" }}>
                  <button className="btn sm primary" onClick={() => setModal(e)}>Registrar resultado</button>
                  <UploadButton caseId={c.id} extra={{ effectiveness_check_id: e.id }} onDone={eff.reload} label="Adjuntar datos" /></div>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      {modal === "criterion" && eff.data && <NewCriterion caseId={c.id} denominators={eff.data.denominators} onClose={() => setModal(null)} onSaved={saved} />}
      {modal === "check" && <NewCheck caseId={c.id} actions={implemented} criteria={approvedCriteria} onClose={() => setModal(null)} onSaved={saved} />}
      {modal && typeof modal === "object" && <Decide check={modal} onClose={() => setModal(null)} onSaved={saved} />}
    </div>
  );
}

// ---- Actualizaciones del sistema (D7) ----------------------------------------------------------

export function SystemUpdatesPanel({ c, editable, onChanged }: { c: Case; editable: boolean; onChanged: () => void }) {
  const canEdit = useCan("action.edit") && editable;
  const { data, setData, error, reload } = useApi<SystemUpdate[]>(`/cases/${c.id}/system-updates`);
  const [modal, setModal] = useState<"new" | SystemUpdate | null>(null);
  const saved = (rows: SystemUpdate[]) => { setData(rows); onChanged(); };
  return (
    <div className="card">
      <div className="card-head"><h2>Actualización de documentos del sistema</h2>
        {canEdit && <div className="right"><button className="btn sm primary" onClick={() => setModal("new")}>+ Actualización</button></div>}</div>
      <ErrorBox error={error} onRetry={reload} />
      {!data?.length ? <Empty title="Sin actualizaciones">AMEF, plan de control, instrucciones, ayudas visuales o capacitación.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Documento</th><th>Referencia</th><th>Responsable</th><th>Estado</th><th>Evidencia</th><th></th></tr></thead>
          <tbody>{data.map((u) => (
            <tr key={u.id}>
              <td>{UPDATE_TYPE[u.update_type]}</td><td>{u.document_reference}{u.description && <div className="small muted">{u.description}</div>}</td>
              <td>{u.responsible_name ?? "—"}</td>
              <td><Badge tone={u.status === "completed" ? "green" : u.status === "planned" ? "amber" : ""}>{UPDATE_STATUS[u.status]}</Badge>
                {u.completed_on && <div className="small muted">{fmtDate(u.completed_on)}</div>}</td>
              <td className="small">{u.evidence_notes ?? "—"}<div className="muted">{u.attachment_count} archivo(s)</div></td>
              <td>{canEdit && u.status === "planned" && <div className="stack" style={{ gap: 4, alignItems: "flex-start" }}>
                <button className="btn sm primary" onClick={() => setModal(u)}>Completar</button>
                <UploadButton caseId={c.id} extra={{ system_update_id: u.id }} onDone={reload} label="Adjuntar" /></div>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {modal === "new" && <NewUpdate caseId={c.id} onClose={() => setModal(null)} onSaved={saved} />}
      {modal && typeof modal === "object" && <CompleteUpdate u={modal} onClose={() => setModal(null)} onSaved={saved} />}
    </div>
  );
}

function NewUpdate({ caseId, onClose, onSaved }: { caseId: string; onClose: () => void; onSaved: (r: SystemUpdate[]) => void }) {
  const users = useApi<User[]>("/users");
  const { f, set } = useForm({ update_type: "pfmea", document_reference: "", description: "", responsible_user_id: "" });
  return (
    <Submitting title="Nueva actualización documental" onClose={onClose} onSubmit={async () => onSaved(await api<SystemUpdate[]>(`/cases/${caseId}/system-updates`, { body: clean(f) }))}>
      <div className="grid g2">
        <Field label="Documento" required><select value={f.update_type} onChange={set("update_type")}>{Object.entries(UPDATE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Referencia" required><input value={f.document_reference} onChange={set("document_reference")} required placeholder="PFMEA-CNC-12" /></Field>
      </div>
      <Field label="Cambio"><textarea value={f.description} onChange={set("description")} /></Field>
      <Field label="Responsable"><select value={f.responsible_user_id} onChange={set("responsible_user_id")}>
        <option value="">—</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
    </Submitting>
  );
}

function CompleteUpdate({ u, onClose, onSaved }: { u: SystemUpdate; onClose: () => void; onSaved: (r: SystemUpdate[]) => void }) {
  const { f, set } = useForm({ status: "completed", completed_on: new Date().toISOString().slice(0, 10), evidence_notes: "" });
  return (
    <Submitting title={`${UPDATE_TYPE[u.update_type]} ${u.document_reference}`} onClose={onClose} danger={f.status === "cancelled"}
      onSubmit={async () => onSaved(await api<SystemUpdate[]>(`/system-updates/${u.id}`, { method: "PATCH", body: f.status === "cancelled" ? { status: "cancelled" } : f }))}>
      <Field label="Resultado"><select value={f.status} onChange={set("status")}><option value="completed">Completada</option><option value="cancelled">Cancelada</option></select></Field>
      {f.status === "completed" && <>
        <Field label="Fecha" required><input type="date" value={f.completed_on} onChange={set("completed_on")} required /></Field>
        <Field label="Evidencia" required hint="Nueva revisión del documento, registro de capacitación…"><textarea value={f.evidence_notes} onChange={set("evidence_notes")} required /></Field>
      </>}
    </Submitting>
  );
}

// ---- Lecciones del caso (D8) -----------------------------------------------------------------

type CaseLessons = {
  origin: { id: string; folio: string; revision: number; title: string; status: string; published_at: string | null }[];
  applied: { id: string; lesson_id: string; folio: string; revision: number; title: string; outcome: string; evaluation: string; applied_at: string; applied_by_name: string }[];
};

export function CaseLessonsPanel({ c }: { c: Case }) {
  const router = useRouter();
  const canCreate = useCan("lesson.edit");
  const { data, error, reload } = useApi<CaseLessons>(`/cases/${c.id}/lessons`);
  const [err, setErr] = useState<string | null>(null);
  const d4 = c.workflow.find((d) => d.code === "D4")?.status === "approved";
  async function create() {
    try { const l = await api<Lesson>(`/cases/${c.id}/lessons`, { method: "POST" }); router.push(`/lecciones/${l.id}`); } catch (e) { setErr(errorText(e)); }
  }
  return (
    <div className="card">
      <div className="card-head"><h2>Lecciones aprendidas</h2>
        {canCreate && <div className="right"><button className="btn sm primary" onClick={create} disabled={!d4} title={d4 ? "" : "Requiere D4 aprobada"}>+ Crear lección desde el caso</button></div>}</div>
      <ErrorBox error={error ?? err} onRetry={reload} />
      <div className="card-pad stack">
        {!data?.origin.length ? <p className="muted small">Este caso aún no tiene lecciones. Se prellenan con la causa verificada, las acciones y la eficacia.</p> : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>{data.origin.map((l) => (
            <li key={l.id}><Link href={`/lecciones/${l.id}`}>{l.folio} rev. {l.revision}</Link> — {l.title} <Badge tone={l.status === "published" ? "green" : "blue"}>{LESSON_STATUS[l.status]}</Badge></li>))}</ul>
        )}
        {!!data?.applied.length && <>
          <h3>Lecciones reutilizadas en este caso</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{data.applied.map((a) => (
            <li key={a.id}><Link href={`/lecciones/${a.lesson_id}`}>{a.folio} rev. {a.revision}</Link> — {OUTCOME[a.outcome]}: {a.evaluation} <span className="small muted">({a.applied_by_name}, {fmtDate(a.applied_at)})</span></li>))}</ul>
        </>}
      </div>
    </div>
  );
}
