"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { ANSWER, CAUSE_STATUS, fmtDate } from "@/lib/labels";
import type { Attachment, Case, Category, Cause, Idea, User, Validation } from "@/lib/types";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { UploadButton } from "./Containment";

const TONE: Record<string, string> = { pending: "", investigating: "blue", root_cause: "red", not_root_cause: "green", needs_more_investigation: "amber" };

function AddCause({ caseId, categories, category, parent, onClose, onSaved }: {
  caseId: string; categories: Category[]; category: string; parent?: Cause | null; onClose: () => void; onSaved: (c: Cause[]) => void;
}) {
  const ideas = useApi<Idea[]>("/cause-ideas");
  const [cat, setCat] = useState(category);
  const [text, setText] = useState("");
  const [ideaId, setIdeaId] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      onSaved(await api<Cause[]>(`/cases/${caseId}/causes`, { body: { category_id: parent?.category_id ?? cat, potential_cause: text || null, source_idea_id: ideaId || null, parent_cause_id: parent?.id ?? null } }));
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  const options = ideas.data?.filter((i) => i.category_id === cat) ?? [];
  return (
    <Modal title={parent ? `Subcausa de «${parent.potential_cause}»` : "Agregar causa potencial"} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        {!parent && <Field label="Categoría (6M)" required><select value={cat} onChange={(e) => { setCat(e.target.value); setIdeaId(""); }}>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name_es}</option>)}</select></Field>}
        <Field label="Desde la biblioteca" hint="Se copia el texto: si el catálogo cambia después, la causa del caso no cambia.">
          <select value={ideaId} onChange={(e) => setIdeaId(e.target.value)}>
            <option value="">— Escribir causa propia —</option>
            {options.map((i) => <option key={i.id} value={i.id}>{i.title_es}</option>)}
          </select></Field>
        {!ideaId && <Field label="Causa potencial" required><input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} required /></Field>}
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Agregar</button></div>
      </form>
    </Modal>
  );
}

function CausePanel({ caseId, cause, editable, onClose, onSaved, onAddSub }: {
  caseId: string; cause: Cause; editable: boolean; onClose: () => void; onSaved: (c: Cause[]) => void; onAddSub: () => void;
}) {
  const canValidate = useCan("cause.validate") && editable;
  const canEditCause = useCan("cause.edit") && editable;
  const users = useApi<User[]>("/users");
  const history = useApi<Validation[]>(`/causes/${cause.id}/validations`);
  const files = useApi<Attachment[]>(`/cases/${caseId}/attachments`);
  const [f, setF] = useState({
    documented_answer: cause.documented_answer ?? "unknown", followed_process_answer: cause.followed_process_answer ?? "unknown",
    verification_method: cause.verification_method ?? "", evidence_summary: cause.evidence_summary ?? "", rationale: cause.rationale ?? "",
    decision: cause.investigation_status === "pending" ? "investigating" : cause.investigation_status,
    responsible_user_id: cause.responsible_user_id ?? "", due_date: cause.due_date ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const deciding = f.decision === "root_cause" || f.decision === "not_root_cause";
  const evidenceFiles = files.data?.filter((a) => a.cause_id === cause.id) ?? [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
      const result = await api<Cause[]>(`/causes/${cause.id}/validations`, { body });
      onSaved(result);
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  async function remove() {
    try {
      onSaved(await api<Cause[]>(`/causes/${cause.id}`, { method: "DELETE" }));
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Modal title={cause.potential_cause} onClose={onClose}>
      <div className="stack">
        <div className="row"><Badge>{cause.category_name}</Badge><Badge tone={TONE[cause.investigation_status]}>{CAUSE_STATUS[cause.investigation_status]}</Badge>
          <span className="small muted">Agregó {cause.added_by_name}{cause.source_idea_id && " · desde la biblioteca"}</span></div>
        {cause.procedure_finding && <div className="notice info"><b>{cause.procedure_finding.label}.</b> {cause.procedure_finding.hint}</div>}
        {canValidate && (
          <form className="stack card card-pad" onSubmit={submit}>
            <h3>Registrar validación</h3>
            <div className="grid g2">
              <Field label="¿Está documentado el proceso?"><select value={f.documented_answer} onChange={set("documented_answer")}>
                {Object.entries(ANSWER).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="¿Se siguió el proceso?"><select value={f.followed_process_answer} onChange={set("followed_process_answer")}>
                {Object.entries(ANSWER).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            </div>
            <Field label="Método de verificación" required={deciding}><textarea value={f.verification_method} onChange={set("verification_method")} placeholder="p. ej. Reproducción controlada, análisis de datos, prueba A/B" /></Field>
            <Field label="Evidencia" required={deciding}><textarea value={f.evidence_summary} onChange={set("evidence_summary")} placeholder="Resultados obtenidos; adjunta archivos abajo" /></Field>
            <Field label="Justificación" required={deciding}><textarea value={f.rationale} onChange={set("rationale")} placeholder="Por qué la evidencia confirma o descarta la causa" /></Field>
            <div className="grid g3">
              <Field label="Decisión" required><select value={f.decision} onChange={set("decision")}>
                {Object.entries(CAUSE_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Responsable"><select value={f.responsible_user_id} onChange={set("responsible_user_id")}>
                <option value="">—</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
              <Field label="Fecha compromiso"><input type="date" value={f.due_date} onChange={set("due_date")} /></Field>
            </div>
            {deciding && <div className="notice warn small">Las respuestas Sí/No no bastan: confirmar o descartar exige método, evidencia y justificación.</div>}
            <ErrorBox error={error} />
            <div className="row">
              {cause.validation_count === 0 && <button type="button" className="btn danger sm" onClick={remove}>Eliminar causa</button>}
              {canEditCause && <button type="button" className="btn sm" onClick={onAddSub}>+ Subcausa</button>}
              <button className="btn primary right">Guardar validación</button>
            </div>
          </form>
        )}
        <div>
          <div className="row" style={{ marginBottom: 6 }}><h3>Evidencias</h3>
            {canValidate && <span className="right"><UploadButton caseId={caseId} extra={{ cause_id: cause.id }} onDone={files.reload} /></span>}</div>
          {evidenceFiles.length === 0 ? <p className="small muted">Sin archivos.</p> : (
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{evidenceFiles.map((a) => (
              <li key={a.id}><a href={`/api/attachments/${a.id}/content`} target="_blank" rel="noreferrer">{a.file_name}</a> · {a.uploaded_by_name}</li>))}</ul>
          )}
        </div>
        <div>
          <h3 style={{ marginBottom: 6 }}>Historial de decisiones</h3>
          {history.loading && !history.data ? <Loading rows={1} /> : !history.data?.length ? <p className="small muted">Aún sin validaciones.</p> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Fecha</th><th>Decisión</th><th>Doc./Siguió</th><th>Método · Evidencia · Justificación</th><th>Por</th></tr></thead>
              <tbody>{history.data.map((v) => (
                <tr key={v.id}>
                  <td className="small">{fmtDate(v.validated_at, true)}</td>
                  <td><Badge tone={TONE[v.decision]}>{CAUSE_STATUS[v.decision]}</Badge></td>
                  <td className="small">{ANSWER[v.documented_answer]} / {ANSWER[v.followed_process_answer]}</td>
                  <td className="small">{[v.verification_method, v.evidence_summary, v.rationale].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="small">{v.validated_by_name}</td>
                </tr>))}
              </tbody>
            </table></div>
          )}
        </div>
      </div>
    </Modal>
  );
}

export function IshikawaPanel({ c, editable, onChanged }: { c: Case; editable: boolean; onChanged: () => void }) {
  const canEdit = useCan("cause.edit") && editable;
  const categories = useApi<Category[]>("/ishikawa/categories");
  const causes = useApi<Cause[]>(`/cases/${c.id}/causes`);
  const suggestions = useApi<Idea[]>(`/cases/${c.id}/suggestions`);
  const [adding, setAdding] = useState<string | null>(null);
  const [subOf, setSubOf] = useState<Cause | null>(null);
  const [selected, setSelected] = useState<Cause | null>(null);
  const [error, setError] = useState<string | null>(null);

  function saved(list: Cause[]) {
    causes.setData(list);
    void suggestions.reload();
    onChanged();
  }
  async function addIdea(idea: Idea) {
    try {
      saved(await api<Cause[]>(`/cases/${c.id}/causes`, { body: { category_id: idea.category_id, source_idea_id: idea.id } }));
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (categories.loading && !categories.data) return <Loading rows={4} />;
  const cats = categories.data ?? [];
  const byCat = (id: string) => causes.data?.filter((x) => x.category_id === id) ?? [];
  // Orden en árbol: cada causa seguida de sus subcausas (sangría por nivel).
  const tree = (id: string) => {
    const list = byCat(id);
    const out: { cause: Cause; depth: number }[] = [];
    const walk = (parent: string | null, depth: number) => list.filter((x) => (x.parent_cause_id ?? null) === parent)
      .forEach((x) => { out.push({ cause: x, depth }); walk(x.id, depth + 1); });
    walk(null, 0);
    return out;
  };
  const bone = (cat: Category, row: number, col: number) => (
    <div key={cat.id} className="bone" style={{ gridRow: row, gridColumn: col }}>
      <h3>{cat.name_es}<span className="n">{byCat(cat.id).length}</span></h3>
      {tree(cat.id).map(({ cause: x, depth }) => (
        <button key={x.id} className={`chip ${selected?.id === x.id ? "sel" : ""}`} onClick={() => setSelected(x)} title={CAUSE_STATUS[x.investigation_status]}
          style={depth ? { marginLeft: depth * 14, width: `calc(100% - ${depth * 14}px)` } : undefined}>
          <span className={`st ${x.investigation_status}`} />{depth > 0 && <span className="muted">↳</span>}{x.potential_cause}
        </button>))}
      {canEdit && <button className="btn sm ghost" style={{ alignSelf: "flex-start" }} onClick={() => setAdding(cat.id)}>+ Agregar</button>}
    </div>
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      <ErrorBox error={categories.error ?? causes.error ?? error} />
      <div className="card card-pad">
        <div className="row" style={{ marginBottom: 12 }}>
          <h2>Diagrama de Ishikawa</h2>
          <div className="right row small muted">{Object.entries(CAUSE_STATUS).map(([k, v]) => <span key={k} className="row" style={{ gap: 4 }}><span className={`st ${k}`} style={{ width: 8, height: 8, borderRadius: 4, background: "#b8c2d1", display: "inline-block" }} />{v}</span>)}</div>
        </div>
        <div className="fish">
          {cats.slice(0, 3).map((cat, i) => bone(cat, 1, i + 1))}
          <div className="spine" />
          {cats.slice(3, 6).map((cat, i) => bone(cat, 3, i + 1))}
          <div className="head"><small>Efecto / problema</small>{c.title}</div>
        </div>
      </div>

      {canEdit && (
        <div className="card">
          <div className="card-head"><h2>Sugerencias de la biblioteca</h2><span className="small muted">Hipótesis por coincidencia de proceso/defecto; no son conclusiones.</span></div>
          {!suggestions.data?.length ? <Empty title="Sin sugerencias">Describe proceso y defecto (D2) para recibir sugerencias, o agrega causas manualmente.</Empty> : (
            <div className="table-wrap"><table><tbody>{suggestions.data.map((s) => (
              <tr key={s.id}>
                <td><b>{s.title_es}</b><div className="small muted">{s.reasons?.join(" · ")}</div></td>
                <td><Badge>{cats.find((k) => k.id === s.category_id)?.name_es}</Badge></td>
                <td style={{ width: 160 }}><button className="btn sm" onClick={() => addIdea(s)}>Agregar al Ishikawa</button></td>
              </tr>))}</tbody></table></div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h2>Matriz de validación de causas</h2></div>
        {!causes.data?.length ? <Empty title="Sin causas potenciales">Agrega causas en el diagrama.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Categoría</th><th>Causa potencial</th><th>¿Documentado?</th><th>¿Se siguió?</th><th>Método</th><th>Evidencia</th><th>Justificación</th><th>Responsable</th><th>Fecha</th><th>Estado</th></tr></thead>
            <tbody>{causes.data.map((x) => (
              <tr key={x.id} className={`click ${selected?.id === x.id ? "selected" : ""}`} onClick={() => setSelected(x)}>
                <td className="small">{x.category_name}</td><td><b>{x.potential_cause}</b></td>
                <td>{x.documented_answer ? ANSWER[x.documented_answer] : "—"}</td>
                <td>{x.followed_process_answer ? ANSWER[x.followed_process_answer] : "—"}</td>
                <td className="small">{x.verification_method ?? "—"}</td>
                <td className="small">{x.evidence_summary ?? "—"}{x.attachment_count > 0 && <div className="muted">{x.attachment_count} archivo(s)</div>}</td>
                <td className="small">{x.rationale ?? "—"}</td>
                <td className="small">{x.responsible_name ?? "—"}</td>
                <td className="small">{fmtDate(x.validated_at)}</td>
                <td><Badge tone={TONE[x.investigation_status]}>{CAUSE_STATUS[x.investigation_status]}</Badge></td>
              </tr>))}
            </tbody>
          </table></div>
        )}
      </div>
      {adding && <AddCause caseId={c.id} categories={cats} category={adding} onClose={() => setAdding(null)} onSaved={saved} />}
      {subOf && <AddCause caseId={c.id} categories={cats} category={subOf.category_id} parent={subOf} onClose={() => setSubOf(null)} onSaved={saved} />}
      {selected && <CausePanel key={selected.id} caseId={c.id} cause={selected} editable={editable} onClose={() => setSelected(null)} onSaved={saved}
        onAddSub={() => { setSubOf(selected); setSelected(null); }} />}
    </div>
  );
}
