"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { ALERT_STATUS, fmtDate } from "@/lib/labels";
import type { Alert, Attachment, User } from "@/lib/types";
import { Badge, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";
import { UploadButton } from "@/components/case/Containment";

const TEXT_FIELDS: [keyof Alert, string, boolean][] = [
  ["what_happened", "¿Qué pasó?", true], ["when_happened", "¿Cuándo?", false], ["where_happened", "¿Dónde?", false],
  ["who_is_affected", "¿Quién / a quién afecta?", false], ["how_detected", "¿Cómo se detectó?", true],
  ["affected_areas", "Áreas afectadas", false], ["containment_summary", "Contención (D3)", true],
];

function Editor({ a, onSaved }: { a: Alert; onSaved: (a: Alert) => void }) {
  const users = useApi<User[]>("/users");
  const init = () => ({
    title: a.title, failure_type: a.failure_type, affected_quantity: a.affected_quantity?.toString() ?? "",
    responsible_user_id: a.responsible_user_id ?? "",
    ...Object.fromEntries(TEXT_FIELDS.map(([k]) => [k, (a[k] as string | null) ?? ""])),
  }) as Record<string, string>;
  const [f, setF] = useState(init);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setF(init()), [a.id]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : k === "affected_quantity" ? Number(v) : v]));
      onSaved(await api<Alert>(`/alerts/${a.id}`, { method: "PATCH", body }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card card-pad stack">
      <div className="grid g2">
        <div style={{ gridColumn: "1 / -1" }}><Field label="Título" required><input value={f.title} onChange={set("title")} maxLength={200} /></Field></div>
        <Field label="Tipo de falla" required><select value={f.failure_type} onChange={set("failure_type")}><option value="internal">Interna</option><option value="external">Externa</option></select></Field>
        <Field label="Cantidad afectada" required><input type="number" min={0} value={f.affected_quantity} onChange={set("affected_quantity")} /></Field>
        <Field label="Responsable" required><select value={f.responsible_user_id} onChange={set("responsible_user_id")}>
          <option value="">Seleccionar…</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
        {TEXT_FIELDS.map(([k, label, long]) => (
          <div key={k} style={long ? { gridColumn: "1 / -1" } : undefined}>
            <Field label={label} required={k !== "affected_areas"}>{long ? <textarea value={f[k]} onChange={set(k)} /> : <input value={f[k]} onChange={set(k)} />}</Field>
          </div>))}
      </div>
      <ErrorBox error={error} />
      <div className="row"><button className="btn primary right" onClick={save} disabled={busy}>{busy ? "Guardando…" : "Guardar borrador"}</button></div>
    </div>
  );
}

function Photos({ a, editable, onSaved }: { a: Alert; editable: boolean; onSaved: (a: Alert) => void }) {
  const files = useApi<Attachment[]>(`/cases/${a.case_id}/attachments`);
  const images = files.data?.filter((x) => x.mime_type.startsWith("image/")) ?? [];
  const current = (kind: string) => a.photos.find((p) => p.kind === kind)?.attachment_id ?? "";
  const [error, setError] = useState<string | null>(null);
  async function choose(kind: "nok" | "ok", id: string) {
    const other = kind === "nok" ? "ok" : "nok";
    const photos = [...(id ? [{ attachment_id: id, kind }] : []), ...(current(other) ? [{ attachment_id: current(other), kind: other }] : [])];
    try {
      onSaved(await api<Alert>(`/alerts/${a.id}/photos`, { method: "PUT", body: { photos } }));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }
  return (
    <div className="card">
      <div className="card-head"><h2>Fotografías NOK / OK</h2>
        {editable && <span className="right"><UploadButton caseId={a.case_id} purpose="photo" accept="image/png,image/jpeg" label="Subir foto" onDone={files.reload} /></span>}</div>
      <div className="card-pad grid g2">
        {(["nok", "ok"] as const).map((kind) => {
          const id = current(kind);
          return (
            <div key={kind} className="stack" style={{ gap: 8 }}>
              <Badge tone={kind === "nok" ? "red" : "green"}>{kind === "nok" ? "NOK — condición incorrecta" : "OK — condición correcta"}</Badge>
              <div style={{ border: "1px dashed var(--line)", borderRadius: 8, minHeight: 160, display: "grid", placeItems: "center", overflow: "hidden", background: "#fafbfd" }}>
                {id ? <img src={`/api/attachments/${id}/content`} alt={kind} style={{ maxWidth: "100%", maxHeight: 220 }} /> : <span className="muted small">Sin foto</span>}
              </div>
              {editable && (
                <select value={id} onChange={(e) => choose(kind, e.target.value)} aria-label={`Foto ${kind}`}>
                  <option value="">— Sin foto —</option>{images.map((x) => <option key={x.id} value={x.id}>{x.file_name}</option>)}
                </select>)}
            </div>);
        })}
      </div>
      <div style={{ padding: "0 18px 14px" }}><ErrorBox error={error ?? files.error} /></div>
    </div>
  );
}

export default function AlertPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: a, setData, error, loading, reload } = useApi<Alert>(`/alerts/${id}`);
  const canEdit = useCan("alert.edit");
  const canIssue = useCan("alert.issue");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [revising, setRevising] = useState(false);
  const [reason, setReason] = useState("");

  if (loading && !a) return <Loading rows={6} />;
  if (error && !a) return <ErrorBox error={error} onRetry={reload} />;
  if (!a) return null;
  const draft = a.status === "draft";
  const current = a.revisions.find((r) => r.id === a.id);

  async function issue() {
    setBusy(true);
    setErr(null);
    try { setData(await api<Alert>(`/alerts/${a!.id}/issue`, { method: "POST" })); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  async function revise(e: React.FormEvent) {
    e.preventDefault();
    try {
      const next = await api<Alert>(`/alerts/${a!.id}/revise`, { body: { reason } });
      setRevising(false);
      router.push(`/alertas/${next.id}`);
    } catch (x) { setErr(errorText(x)); setRevising(false); }
  }

  return (
    <>
      <div className="small muted" style={{ marginBottom: 6 }}><Link href="/alertas">Alertas</Link> / {a.folio} rev. {a.revision}</div>
      <div className="page-head">
        <div>
          <div className="row"><span className="mono badge navy">{a.folio} · Rev. {a.revision}</span>
            <Badge tone={a.status === "issued" ? "green" : draft ? "blue" : ""}>{ALERT_STATUS[a.status]}</Badge>
            <Badge tone={a.failure_type === "external" ? "red" : "blue"}>Falla {a.failure_type === "external" ? "externa" : "interna"}</Badge></div>
          <h1 style={{ marginTop: 8 }}>{a.title}</h1>
          <div className="sub">Caso <Link href={`/casos/${a.case_id}`}>{a.case_folio}</Link> · {a.case_title}{a.revision_reason && ` · Motivo de revisión: ${a.revision_reason}`}</div>
        </div>
        <div className="actions">
          {current?.document_id && <a className="btn" href={`/api/documents/${current.document_id}/content`} target="_blank" rel="noreferrer">Abrir PDF</a>}
          {draft && canIssue && <button className="btn ok" onClick={issue} disabled={busy || a.missing_to_issue.length > 0}>{busy ? "Emitiendo…" : "Emitir alerta PDF"}</button>}
          {a.status === "issued" && canEdit && <button className="btn primary" onClick={() => setRevising(true)}>Nueva revisión</button>}
        </div>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        {draft && a.missing_to_issue.length > 0 && <div className="notice warn">Para emitir falta: {a.missing_to_issue.join(", ")}.</div>}
        {draft && !canIssue && <div className="notice info">La emisión la realiza un gerente de calidad.</div>}
        <ErrorBox error={err} />
        {draft && canEdit ? <Editor a={a} onSaved={setData} /> : (
          <div className="card"><div className="table-wrap"><table><tbody>
            {TEXT_FIELDS.map(([k, label]) => <tr key={k}><th style={{ width: 220 }}>{label}</th><td style={{ whiteSpace: "pre-wrap" }}>{(a[k] as string) ?? "—"}</td></tr>)}
            <tr><th>Cantidad afectada</th><td>{a.affected_quantity ?? "—"}</td></tr>
            <tr><th>Responsable</th><td>{a.responsible_name ?? "—"}</td></tr>
            <tr><th>Emitida</th><td>{a.issued_at ? `${fmtDate(a.issued_at, true)} por ${a.issued_by_name}` : "—"}</td></tr>
          </tbody></table></div></div>
        )}
        <Photos a={a} editable={draft && canEdit} onSaved={setData} />
        <div className="card">
          <div className="card-head"><h2>Revisiones</h2><span className="small muted">Las revisiones emitidas son inmutables.</span></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Rev.</th><th>Estado</th><th>Emitida</th><th>Motivo</th><th>SHA-256 del PDF</th><th></th></tr></thead>
            <tbody>{a.revisions.map((r) => (
              <tr key={r.id} className={r.id === a.id ? "selected" : ""}>
                <td><Link href={`/alertas/${r.id}`}>{r.revision}</Link></td>
                <td><Badge tone={r.status === "issued" ? "green" : r.status === "draft" ? "blue" : ""}>{ALERT_STATUS[r.status]}</Badge></td>
                <td className="small">{fmtDate(r.issued_at, true)}</td><td className="small">{r.revision_reason ?? "—"}</td>
                <td className="mono" title={r.sha256_hex ?? ""}>{r.sha256_hex ? `${r.sha256_hex.slice(0, 20)}…` : "—"}</td>
                <td>{r.document_id && <a href={`/api/documents/${r.document_id}/content`} target="_blank" rel="noreferrer">PDF</a>}</td>
              </tr>))}</tbody>
          </table></div>
        </div>
      </div>
      {revising && (
        <Modal title={`Nueva revisión de ${a.folio}`} onClose={() => setRevising(false)}>
          <form className="stack" onSubmit={revise}>
            <Field label="Motivo de la revisión" required><textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required /></Field>
            <p className="small muted">Se crea un borrador rev. {a.revision + 1} con el contenido actual. La rev. {a.revision} sigue vigente hasta emitir la nueva.</p>
            <div className="row"><button type="button" className="btn" onClick={() => setRevising(false)}>Cancelar</button><button className="btn primary right">Crear borrador</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
