"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { LESSON_STATUS, OUTCOME, fmtDate } from "@/lib/labels";
import type { Attachment, CaseSummary, IssuedDocument, Lesson } from "@/lib/types";
import { Badge, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan, useMe } from "@/components/Shell";

const TEXT: [keyof Lesson, string, boolean][] = [
  ["problem_summary", "Problema original", true], ["verified_root_cause", "Causa raíz verificada", true],
  ["actions_summary", "Acciones implementadas", true], ["effectiveness_summary", "Resultados de eficacia", true],
  ["before_summary", "Situación antes", true], ["after_summary", "Situación después", true],
  ["training_summary", "Capacitación requerida o impartida", false],
];
const LISTS: [keyof Lesson, string][] = [
  ["documents_updated", "Documentos actualizados"], ["products", "Productos"], ["processes", "Procesos"],
  ["plant_codes", "Plantas"], ["situations", "Situaciones a las que aplica"],
];

function Editor({ l, onSaved }: { l: Lesson; onSaved: (l: Lesson) => void }) {
  const init = () => ({
    title: l.title, language_code: l.language_code,
    ...Object.fromEntries(TEXT.map(([k]) => [k, (l[k] as string | null) ?? ""])),
    ...Object.fromEntries(LISTS.map(([k]) => [k, (l[k] as string[]).join(", ")])),
  }) as Record<string, string>;
  const [f, setF] = useState(init);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setF(init()), [l.id]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => { setF({ ...f, [k]: e.target.value }); setOk(false); };
  async function save() {
    try {
      const body: Record<string, unknown> = { title: f.title, language_code: f.language_code };
      for (const [k] of TEXT) body[k] = f[k as string] || null;
      for (const [k] of LISTS) body[k] = f[k as string].split(",").map((s) => s.trim()).filter(Boolean);
      onSaved(await api<Lesson>(`/lessons/${l.id}`, { method: "PATCH", body }));
      setError(null);
      setOk(true);
    } catch (e) {
      setError(errorText(e));
    }
  }
  return (
    <div className="card card-pad stack">
      <div className="grid g2">
        <div style={{ gridColumn: "1 / -1" }}><Field label="Título" required><input value={f.title} onChange={set("title")} maxLength={200} /></Field></div>
        {TEXT.map(([k, label, req]) => <div key={k} style={{ gridColumn: "1 / -1" }}><Field label={label} required={req}><textarea value={f[k as string]} onChange={set(k as string)} /></Field></div>)}
        {LISTS.map(([k, label]) => <Field key={k} label={label} hint="Separados por coma"><input value={f[k as string]} onChange={set(k as string)} /></Field>)}
        <Field label="Idioma"><select value={f.language_code} onChange={set("language_code")}><option value="es">Español</option><option value="en">Inglés</option></select></Field>
      </div>
      <ErrorBox error={error} />
      <div className="row">{ok && <span className="small" style={{ color: "var(--ok)" }}>Guardado</span>}<button className="btn primary right" onClick={save}>Guardar borrador</button></div>
    </div>
  );
}

function BeforeAfter({ l, editable, onSaved }: { l: Lesson; editable: boolean; onSaved: (l: Lesson) => void }) {
  const files = useApi<Attachment[]>(editable ? `/cases/${l.source_case_id}/attachments` : null);
  const [caption, setCaption] = useState<Record<string, string>>({ before: "", after: "" });
  const [pick, setPick] = useState<Record<string, string>>({ before: "", after: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const images = files.data?.filter((f) => f.mime_type.startsWith("image/") && !l.photos.some((p) => p.attachment_id === f.id)) ?? [];

  async function save(photos: Lesson["photos"]) {
    setBusy(true);
    try {
      onSaved(await api<Lesson>(`/lessons/${l.id}/photos`, { method: "PUT", body: { photos: photos.map(({ attachment_id, kind, caption }) => ({ attachment_id, kind, caption })) } }));
      setError(null);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function upload(kind: string, file: File) {
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (caption[kind]) form.append("caption", caption[kind]);
    try {
      onSaved(await api<Lesson>(`/lessons/${l.id}/photos/upload`, { form }));
      setCaption({ ...caption, [kind]: "" });
      setError(null);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  const column = (kind: "before" | "after") => {
    const before = kind === "before";
    const list = l.photos.filter((p) => p.kind === kind);
    return (
      <div className="stack" style={{ border: `2px solid ${before ? "var(--bad)" : "var(--ok)"}`, borderRadius: 10, padding: 0, overflow: "hidden" }}>
        <div style={{ background: before ? "var(--bad)" : "var(--ok)", color: "#fff", fontWeight: 700, padding: "6px 12px" }}>{before ? "ANTES" : "DESPUÉS"}</div>
        <div className="stack" style={{ padding: "0 12px 12px" }}>
          <div style={{ whiteSpace: "pre-wrap" }} className="small">{(before ? l.before_summary : l.after_summary) || <span className="muted">Sin descripción.</span>}</div>
          {!list.length && <div className="muted small">Sin fotografía.</div>}
          {list.map((p) => (
            <figure key={p.attachment_id} style={{ margin: 0 }}>
              <img src={`/api/attachments/${p.attachment_id}/content`} alt={p.caption ?? p.file_name} style={{ width: "100%", maxHeight: 320, objectFit: "contain", background: "#fafbfd", borderRadius: 6 }} />
              <figcaption className="small muted row">{p.caption ?? p.file_name}
                {editable && <button className="btn sm ghost right" disabled={busy} onClick={() => save(l.photos.filter((x) => x.attachment_id !== p.attachment_id))}>Quitar</button>}</figcaption>
            </figure>))}
          {editable && (
            <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--line-2)", paddingTop: 8 }}>
              <input placeholder="Leyenda (opcional)" value={caption[kind]} maxLength={300} onChange={(e) => setCaption({ ...caption, [kind]: e.target.value })} />
              <div className="row">
                <label className="btn sm">{busy ? "Subiendo…" : "Subir foto"}
                  <input type="file" accept="image/png,image/jpeg" hidden disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(kind, f); }} /></label>
                <select value={pick[kind]} onChange={(e) => setPick({ ...pick, [kind]: e.target.value })} style={{ maxWidth: 220 }} aria-label="Imagen del caso">
                  <option value="">…o una imagen del caso</option>{images.map((f) => <option key={f.id} value={f.id}>{f.description ?? f.file_name}</option>)}
                </select>
                <button className="btn sm" disabled={!pick[kind] || busy} onClick={() => {
                  void save([...l.photos, { attachment_id: pick[kind], kind, caption: caption[kind] || null, file_name: "" }]);
                  setPick({ ...pick, [kind]: "" }); setCaption({ ...caption, [kind]: "" });
                }}>Agregar</button>
              </div>
            </div>)}
        </div>
      </div>
    );
  };

  return (
    <div className="card">
      <div className="card-head"><h2>Antes y después</h2><span className="small muted">Obligatorio: al menos una foto de cada lado para enviar a revisión.</span></div>
      <div className="card-pad stack">
        <div className="grid g2">{column("before")}{column("after")}</div>
        <ErrorBox error={error ?? files.error} />
      </div>
    </div>
  );
}

function Apply({ l, onClose, onSaved }: { l: Lesson; onClose: () => void; onSaved: (l: Lesson) => void }) {
  const cases = useApi<CaseSummary[]>("/cases");
  const [f, setF] = useState({ target_case_id: "", outcome: "applied", evaluation: "", application_notes: "" });
  const [error, setError] = useState<string | null>(null);
  const options = cases.data?.filter((c) => c.id !== l.source_case_id && !["closed", "cancelled"].includes(c.status)) ?? [];
  const set = (k: string) => (e: React.ChangeEvent<HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={`Reutilizar ${l.folio} rev. ${l.revision}`} onClose={onClose}>
      <form className="stack" onSubmit={async (e) => {
        e.preventDefault();
        try { onSaved(await api<Lesson>(`/lessons/${l.id}/apply`, { body: { ...f, application_notes: f.application_notes || null } })); onClose(); } catch (x) { setError(errorText(x)); }
      }}>
        <p className="small muted">Se registra en el caso destino. La lección y su caso de origen no se modifican.</p>
        <Field label="Caso destino (abierto)" required><select value={f.target_case_id} onChange={set("target_case_id")} required>
          <option value="">Seleccionar…</option>{options.map((c) => <option key={c.id} value={c.id}>{c.folio} — {c.title}</option>)}</select></Field>
        <Field label="Cómo se evaluó" required><textarea value={f.evaluation} onChange={set("evaluation")} minLength={5} required /></Field>
        <Field label="Resultado" required><select value={f.outcome} onChange={set("outcome")}>{Object.entries(OUTCOME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Cómo se aplicó"><textarea value={f.application_notes} onChange={set("application_notes")} /></Field>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Registrar</button></div>
      </form>
    </Modal>
  );
}

export default function LessonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const me = useMe();
  const { data: l, setData, error, loading, reload } = useApi<Lesson>(`/lessons/${id}`);
  const can = (p: string) => me.permissions.includes(p);
  const canEdit = useCan("lesson.edit");
  const [dialog, setDialog] = useState<"reject" | "approve" | "retire" | "revise" | "apply" | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [doc, setDoc] = useState<IssuedDocument | null>(null);

  if (loading && !l) return <Loading rows={6} />;
  if (error && !l) return <ErrorBox error={error} onRetry={reload} />;
  if (!l) return null;
  const draft = l.status === "draft";
  const isAuthor = me.user.id === l.created_by;

  async function act(path: string, body?: unknown, navigate = false) {
    try {
      const r = await api<Lesson>(`/lessons/${l!.id}/${path}`, { method: "POST", body });
      setDialog(null);
      setText("");
      setErr(null);
      if (navigate) router.push(`/lecciones/${r.id}`); else setData(r);
    } catch (e) {
      setErr(errorText(e));
      setDialog(null);
    }
  }
  async function issue() {
    try { setDoc(await api<IssuedDocument>(`/lessons/${l!.id}/document`, { method: "POST" })); void reload(); setErr(null); } catch (e) { setErr(errorText(e)); }
  }

  return (
    <>
      <div className="small muted" style={{ marginBottom: 6 }}><Link href="/lecciones">Lecciones aprendidas</Link> / {l.folio} rev. {l.revision}</div>
      <div className="page-head">
        <div>
          <div className="row"><span className="mono badge navy">{l.folio} · Rev. {l.revision}</span><Badge tone={l.status === "published" ? "green" : l.status === "in_review" ? "amber" : "blue"}>{LESSON_STATUS[l.status]}</Badge>
            <Badge>{l.language_code.toUpperCase()}</Badge></div>
          <h1 style={{ marginTop: 8 }}>{l.title}</h1>
          <div className="sub">Caso de origen <Link href={`/casos/${l.source_case_id}`}>{l.source_folio}</Link> · Autor {l.created_by_name}
            {l.reviewed_by_name && ` · Revisó ${l.reviewed_by_name}`}{l.published_by_name && ` · Publicó ${l.published_by_name}`}</div>
        </div>
        <div className="actions">
          {can("document.generate") && <a className="btn" href={`/api/lessons/${l.id}/document/preview`} target="_blank" rel="noreferrer">Vista previa PDF</a>}
          {can("document.generate") && ["approved", "published", "superseded", "retired"].includes(l.status) && <button className="btn" onClick={issue}>Emitir PDF</button>}
          {draft && canEdit && <button className="btn primary" disabled={l.missing_to_submit.length > 0} onClick={() => act("submit")}>Enviar a revisión</button>}
          {l.status === "in_review" && can("lesson.review") && !isAuthor && <>
            <button className="btn" onClick={() => setDialog("reject")}>Rechazar</button><button className="btn ok" onClick={() => setDialog("approve")}>Aprobar</button></>}
          {l.status === "approved" && can("lesson.publish") && <button className="btn ok" onClick={() => act("publish")}>Publicar</button>}
          {l.status === "published" && can("lesson.apply") && <button className="btn primary" onClick={() => setDialog("apply")}>Reutilizar en un caso</button>}
          {["published", "retired"].includes(l.status) && canEdit && <button className="btn" onClick={() => setDialog("revise")}>Nueva revisión</button>}
          {l.status === "published" && can("lesson.retire") && <button className="btn danger" onClick={() => setDialog("retire")}>Retirar</button>}
        </div>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        {draft && l.missing_to_submit.length > 0 && <div className="notice warn">Para enviar a revisión falta: {l.missing_to_submit.join(", ")}.</div>}
        {l.status === "in_review" && isAuthor && <div className="notice info">La revisión la hace una persona distinta del autor.</div>}
        {l.review_comment && <div className="notice info">Comentario de revisión: «{l.review_comment}»</div>}
        {l.status === "retired" && <div className="notice error">Retirada: {l.retire_reason}</div>}
        {doc && <div className="notice ok">{doc.file_name} emitido. <a href={`/api/documents/${doc.id}/content`} target="_blank" rel="noreferrer">Abrir</a></div>}
        <ErrorBox error={err} />
        {draft && canEdit ? <Editor l={l} onSaved={setData} /> : (
          <div className="card"><div className="table-wrap"><table><tbody>
            {TEXT.filter(([k]) => k !== "before_summary" && k !== "after_summary").map(([k, label]) => <tr key={k}><th style={{ width: 230 }}>{label}</th><td style={{ whiteSpace: "pre-wrap" }}>{(l[k] as string) || "—"}</td></tr>)}
            {LISTS.map(([k, label]) => <tr key={k}><th>{label}</th><td>{(l[k] as string[]).join(", ") || "—"}</td></tr>)}
          </tbody></table></div></div>
        )}
        <BeforeAfter l={l} editable={draft && canEdit} onSaved={setData} />
        <div className="grid g2">
          <div className="card">
            <div className="card-head"><h2>Revisiones</h2></div>
            <div className="table-wrap"><table>
              <thead><tr><th>Rev.</th><th>Estado</th><th>Motivo</th><th>Publicada</th></tr></thead>
              <tbody>{l.revisions.map((r) => (
                <tr key={r.id} className={r.id === l.id ? "selected" : ""}><td><Link href={`/lecciones/${r.id}`}>{r.revision}</Link></td>
                  <td><Badge>{LESSON_STATUS[r.status]}</Badge></td><td className="small">{r.revision_reason ?? "—"}</td><td className="small">{fmtDate(r.published_at)}</td></tr>))}</tbody>
            </table></div>
          </div>
          <div className="card">
            <div className="card-head"><h2>Reutilización</h2></div>
            {!l.applications.length ? <p className="card-pad muted small">Aún no se ha reutilizado.</p> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Caso</th><th>Rev.</th><th>Resultado</th><th>Evaluación</th></tr></thead>
                <tbody>{l.applications.map((a) => (
                  <tr key={a.id}><td className="mono"><Link href={`/casos/${a.target_case_id}`}>{a.target_folio}</Link></td><td>{a.revision}</td>
                    <td>{OUTCOME[a.outcome]}</td><td className="small">{a.evaluation}<div className="muted">{a.applied_by_name} · {fmtDate(a.applied_at)}</div></td></tr>))}</tbody>
              </table></div>
            )}
          </div>
        </div>
        {!!l.documents.length && <div className="card">
          <div className="card-head"><h2>PDF emitidos</h2></div>
          <div className="table-wrap"><table><tbody>{l.documents.map((d) => (
            <tr key={d.id}><td><a href={`/api/documents/${d.id}/content`} target="_blank" rel="noreferrer">{d.file_name}</a></td><td>{d.status === "issued" ? "Vigente" : "Sustituido"}</td>
              <td className="small">{fmtDate(d.generated_at, true)}</td><td className="mono">{d.sha256_hex.slice(0, 16)}…</td></tr>))}</tbody></table></div>
        </div>}
      </div>
      {dialog === "apply" && <Apply l={l} onClose={() => setDialog(null)} onSaved={setData} />}
      {dialog && dialog !== "apply" && (
        <Modal title={{ approve: "Aprobar lección", reject: "Rechazar lección", retire: "Retirar lección", revise: "Nueva revisión" }[dialog]} onClose={() => setDialog(null)}>
          <form className="stack" onSubmit={(e) => {
            e.preventDefault();
            if (dialog === "approve") void act("review", { decision: "approve", comment: text || null });
            if (dialog === "reject") void act("review", { decision: "reject", comment: text });
            if (dialog === "retire") void act("retire", { reason: text });
            if (dialog === "revise") void act("revise", { reason: text }, true);
          }}>
            <Field label={dialog === "approve" ? "Comentario" : "Motivo"} required={dialog !== "approve"}>
              <textarea value={text} onChange={(e) => setText(e.target.value)} required={dialog !== "approve"} minLength={dialog === "approve" ? 0 : 5} /></Field>
            {dialog === "revise" && <p className="small muted">La revisión vigente sigue publicada hasta que se publique la nueva.</p>}
            <div className="row"><button type="button" className="btn" onClick={() => setDialog(null)}>Cancelar</button><button className="btn primary right">Confirmar</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
