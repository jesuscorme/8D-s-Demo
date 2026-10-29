"use client";

import { useState } from "react";
import { api, errorText } from "@/lib/api";
import { CASE_TYPE, DISCIPLINE_STATUS, SEVERITY, SOURCE, fmtDate } from "@/lib/labels";
import type { Case, Discipline } from "@/lib/types";
import { Badge, ErrorBox, Field, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { DisciplineForm, type FieldSpec } from "./DisciplineForm";
import { TeamEditor } from "./TeamEditor";
import { CaseAlerts, ContainmentPanel } from "./Containment";
import { IshikawaPanel } from "./Ishikawa";
import { ActionsPanel, CaseLessonsPanel, EffectivenessPanel, SystemUpdatesPanel } from "./Actions";
import { ContainmentRecordPanel } from "./ContainmentRecord";

const FIELDS: Record<string, FieldSpec[]> = {
  D0: [
    { key: "title", label: "Título del caso", target: "case", required: true, wide: true },
    { key: "case_type", label: "Tipo de 8D", target: "case", kind: "select", options: CASE_TYPE, required: true },
    { key: "source_type", label: "Origen", target: "case", kind: "select", options: SOURCE, required: true },
    { key: "report_date", label: "Fecha de reporte", target: "case", kind: "date", required: true, hint: "Inicio de los plazos del concentrado (24 h, 48 h, 7 y 14 días)." },
    { key: "severity", label: "Severidad", target: "case", kind: "select", options: SEVERITY, required: true },
    { key: "target_close_date", label: "Fecha objetivo de cierre", target: "case", kind: "date", hint: "Se usa para el indicador de casos vencidos." },
    { key: "emergency_response", label: "Acciones de respuesta de emergencia (ERA)", target: "content", kind: "textarea", required: true,
      hint: "Qué se hizo de inmediato para proteger al cliente; si no aplica, justifícalo." },
    { key: "justification", label: "¿Por qué se requiere un 8D?", target: "content", kind: "textarea", required: true },
  ],
  D2: [
    { key: "problem_description", label: "Descripción del problema", target: "case", kind: "textarea", required: true, hint: "Mínimo 20 caracteres; hechos, no causas." },
    { key: "part_number", label: "Número de parte", target: "case", required: true },
    { key: "product_name", label: "Producto", target: "case" },
    { key: "customer_name", label: "Cliente", target: "case", hint: "Obligatorio en 8D externos." },
    { key: "market_segment", label: "Mercado (OEM | OES | AM)", target: "case", kind: "select", options: { OEM: "OEM", OES: "OES", AM: "AM" } },
    { key: "main_defect", label: "Defecto principal", target: "case" },
    { key: "process_name", label: "Proceso", target: "case" },
    { key: "lot_number", label: "Lote", target: "case" },
    { key: "defect_date", label: "Fecha de detección", target: "case", kind: "date", required: true },
    { key: "detected_quantity", label: "Cantidad detectada", target: "case", kind: "number", required: true },
    { key: "affected_quantity", label: "Cantidad potencialmente afectada", target: "case", kind: "number" },
    { key: "what", label: "¿Qué? — defecto observado", target: "content", kind: "textarea", required: true },
    { key: "where", label: "¿Dónde se detectó?", target: "content", required: true },
    { key: "when", label: "¿Cuándo se detectó?", target: "content", required: true },
    { key: "who", label: "¿Quién lo detectó?", target: "content" },
    { key: "how_detected", label: "¿Cómo se detectó?", target: "content", required: true },
    { key: "is_not", label: "Es / No es (opcional)", target: "content", kind: "textarea" },
  ],
  D3: [{ key: "effectiveness_notes", label: "Notas sobre la eficacia de la contención", target: "content", kind: "textarea" }],
  D4: [
    { key: "occurrence_cause", label: "Causa de ocurrencia", target: "content", kind: "textarea", required: true, hint: "Resume la(s) causa(s) raíz validada(s) en la matriz." },
    { key: "escape_point", label: "Punto de escape / causa de no detección", target: "content", kind: "textarea", required: true },
    { key: "notes", label: "Notas de la investigación (datos, análisis)", target: "content", kind: "textarea" },
  ],
  D5: [
    { key: "verification_plan", label: "Plan para verificar que la acción elimina la causa", target: "content", kind: "textarea", required: true,
      hint: "Prueba piloto, reproducción, simulación… antes de implementarla de forma permanente." },
    { key: "notes", label: "Notas", target: "content", kind: "textarea" },
  ],
  D6: [
    { key: "validation_summary", label: "Resumen de la implementación y validación", target: "content", kind: "textarea", required: true },
    { key: "notes", label: "Notas", target: "content", kind: "textarea" },
  ],
  D7: [
    { key: "horizontal_deployment", label: "Despliegue horizontal (otras líneas, productos o plantas)", target: "content", kind: "textarea", required: true },
    { key: "no_update_justification", label: "Justificación si no se actualiza ningún documento del sistema", target: "content", kind: "textarea" },
    { key: "no_preventive_justification", label: "Justificación si no hay acción preventiva/sistémica", target: "content", kind: "textarea" },
  ],
  D8: [
    { key: "closure_summary", label: "Resumen de cierre", target: "content", kind: "textarea", required: true },
    { key: "team_recognition", label: "Reconocimiento al equipo", target: "content", kind: "textarea", required: true },
    { key: "notes", label: "Notas", target: "content", kind: "textarea" },
  ],
};

function ReviewDialog({ c, d, action, onClose, onDone }: {
  c: Case; d: Discipline; action: "approve" | "reject" | "reopen"; onClose: () => void; onDone: (c: Case) => void;
}) {
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const title = { approve: "Aprobar", reject: "Rechazar", reopen: "Reabrir" }[action];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      onDone(await api<Case>(`/cases/${c.id}/disciplines/${d.code}/${action}`, { body: { comment: comment || null } }));
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title={`${title} ${d.code} — ${d.name}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Comentario" required={action !== "approve"}><textarea value={comment} onChange={(e) => setComment(e.target.value)} required={action !== "approve"} maxLength={2000} /></Field>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className={`btn right ${action === "approve" ? "ok" : "primary"}`}>{title}</button></div>
      </form>
    </Modal>
  );
}

function FiveWhys({ c, editable, onSaved }: { c: Case; editable: boolean; onSaved: (c: Case) => void }) {
  const stored = c.workflow.find((d) => d.code === "D4")?.content?.five_whys;
  const initial = () => Array.from({ length: 5 }, (_, i) => (Array.isArray(stored) ? stored[i] ?? "" : ""));
  const [whys, setWhys] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const dirty = whys.join("\u0000") !== initial().join("\u0000");
  async function save() {
    try {
      // Se guardan en orden y sin huecos al final.
      const list = whys.map((w) => w.trim());
      while (list.length && !list[list.length - 1]) list.pop();
      onSaved(await api<Case>(`/cases/${c.id}/disciplines/D4`, { method: "PATCH", body: { content: { five_whys: list } } }));
      setError(null);
      setOk(true);
    } catch (e) {
      setError(errorText(e));
    }
  }
  return (
    <div className="card card-pad stack">
      <h3>5 porqués</h3>
      {whys.map((w, i) => (
        <Field key={i} label={`¿Por qué? ${i + 1}`}>
          <input value={w} maxLength={500} disabled={!editable} onChange={(e) => { setWhys(whys.map((x, j) => (j === i ? e.target.value : x))); setOk(false); }} />
        </Field>))}
      <ErrorBox error={error} />
      {editable && <div className="row">{ok && <span className="small" style={{ color: "var(--ok)" }}>Guardado</span>}
        <button className="btn primary right" disabled={!dirty} onClick={save}>Guardar 5 porqués</button></div>}
    </div>
  );
}

const DOT: Record<string, string> = { not_started: "", in_progress: "in_progress", pending_review: "pending_review", approved: "approved", blocked: "" };

export function WorkflowTab({ c, setCase, reload }: { c: Case; setCase: (c: Case) => void; reload: () => void }) {
  const canEdit = useCan("case.edit");
  const canApprove = useCan("discipline.approve");
  const first = c.workflow.find((d) => d.status !== "approved" && d.available) ?? c.workflow[0];
  const [code, setCode] = useState(first.code);
  const [review, setReview] = useState<"approve" | "reject" | "reopen" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = c.workflow.find((x) => x.code === code)!;
  const open = !["cancelled", "closed"].includes(c.status);
  const unlocked = open && d.available && ["not_started", "in_progress"].includes(d.status);
  const editable = unlocked && canEdit;
  const canReopen = canApprove && d.status === "approved" && (open || (c.status === "closed" && d.code === "D8"));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setCase(await api<Case>(`/cases/${c.id}/disciplines/${d.code}/submit`, { method: "POST" }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flow">
      <div className="card steps">
        {c.workflow.map((x) => (
          <button key={x.code} className={`step ${x.code === code ? "active" : ""}`} onClick={() => { setCode(x.code); setError(null); }}>
            <span className={`dot ${x.available ? DOT[x.status] : "na"}`}>{x.status === "approved" ? "✓" : x.code}</span>
            <span style={{ minWidth: 0 }}>
              <div className="t">{x.code} · {x.name}</div>
              <div className="s">{!x.available ? "No disponible en esta versión" : DISCIPLINE_STATUS[x.status]
                + (x.pending_count && x.status !== "approved" ? ` · ${x.pending_count} pendiente(s)` : "")}</div>
            </span>
          </button>))}
      </div>

      <div className="stack" style={{ gap: 16, minWidth: 0 }}>
        <div className="card">
          <div className="card-head">
            <h2>{d.code} — {d.name}</h2>
            <Badge tone={d.status === "approved" ? "green" : d.status === "pending_review" ? "amber" : d.status === "in_progress" ? "blue" : ""}>{DISCIPLINE_STATUS[d.status]}</Badge>
            <div className="right row">
              {open && canEdit && d.available && ["not_started", "in_progress"].includes(d.status) && (
                <button className="btn primary" onClick={submit} disabled={busy || !d.can_submit} title={d.can_submit ? "" : "Hay requisitos pendientes"}>Enviar a revisión</button>)}
              {open && canApprove && d.status === "pending_review" && <>
                <button className="btn" onClick={() => setReview("reject")}>Rechazar</button>
                <button className="btn ok" onClick={() => setReview("approve")}>Aprobar</button></>}
              {canReopen && <button className="btn" onClick={() => setReview("reopen")}>{c.status === "closed" ? "Reabrir caso (D8)" : "Reabrir"}</button>}
            </div>
          </div>
          <div className="card-pad stack">
            {!d.available ? (
              <div className="notice warn">{d.requirements[0]?.label}. Esta disciplina no puede editarse ni aprobarse hasta que el módulo exista; no se simula.</div>
            ) : (
              <>
                <div>
                  <h3 style={{ marginBottom: 8 }}>Requisitos para enviar a revisión</h3>
                  <ul className="reqs">
                    {d.blockers.filter((b) => b.startsWith("Requiere ")).map((b) => <li key={b}><span className="ic n">!</span>{b}</li>)}
                    {d.requirements.map((r) => <li key={r.key}><span className={`ic ${r.met ? "y" : "n"}`}>{r.met ? "✓" : "✕"}</span>{r.label}</li>)}
                  </ul>
                </div>
                {(d.submitted_at || d.approved_at || d.review_comment) && (
                  <div className="small muted">
                    {d.submitted_at && <>Enviada por {d.submitted_by_name} el {fmtDate(d.submitted_at, true)}. </>}
                    {d.approved_at && <>Aprobada por {d.approved_by_name} el {fmtDate(d.approved_at, true)}. </>}
                    {d.review_comment && <>Comentario de revisión: «{d.review_comment}»</>}
                  </div>)}
                {!editable && open && d.available && ["pending_review", "approved"].includes(d.status) && (
                  <div className="notice info small">La disciplina está {DISCIPLINE_STATUS[d.status].toLowerCase()}: su contenido queda congelado{canApprove ? "; puedes reabrirla" : ""}.</div>)}
                <ErrorBox error={error} />
              </>
            )}
          </div>
        </div>

        {d.code === "D1" && <div className="card card-pad"><TeamEditor c={c} editable={editable} onSaved={setCase} /></div>}
        {FIELDS[d.code] && <div className="card card-pad"><DisciplineForm c={c} code={d.code} fields={FIELDS[d.code]} editable={editable} onSaved={setCase} /></div>}
        {d.code === "D3" && <>
          <ContainmentPanel caseId={c.id} editable={editable} onChanged={reload} />
          <CaseAlerts caseId={c.id} open={open} />
          <ContainmentRecordPanel c={c} editable={unlocked} onChanged={reload} />
        </>}
        {d.code === "D4" && <><FiveWhys c={c} editable={editable} onSaved={setCase} /><IshikawaPanel c={c} editable={editable} onChanged={reload} /></>}
        {d.code === "D5" && <ActionsPanel c={c} types={["corrective"]} canDefine={unlocked} canExecute={false} title="Acciones correctivas permanentes" onChanged={reload} />}
        {d.code === "D6" && <>
          <ActionsPanel c={c} types={["corrective"]} canDefine={false} canExecute={unlocked} title="Implementación de acciones correctivas" onChanged={reload} />
          <EffectivenessPanel c={c} editable={unlocked} onChanged={reload} />
        </>}
        {d.code === "D7" && <>
          <ActionsPanel c={c} types={["preventive", "systemic"]} canDefine={unlocked} canExecute={unlocked} title="Acciones preventivas y sistémicas" onChanged={reload} />
          <SystemUpdatesPanel c={c} editable={unlocked} onChanged={reload} />
        </>}
        {d.code === "D8" && <CaseLessonsPanel c={c} />}
      </div>
      {review && <ReviewDialog c={c} d={d} action={review} onClose={() => setReview(null)} onDone={setCase} />}
    </div>
  );
}
