"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { DOC_TYPE, EVENT, fmtBytes, fmtDate } from "@/lib/labels";
import type { Attachment, AuditEvent, DocumentRow, IssuedDocument } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { useCan, useMe } from "@/components/Shell";
import { UploadButton } from "./Containment";

const GENERATE: [string, string, string][] = [
  ["8d_full", "Expediente 8D completo", "document.generate"], ["8d_progress", "Reporte de avance", "document.generate"],
  ["audit_report", "Reporte de auditoría", "audit.read"],
];

function Generate({ caseId, onDone }: { caseId: string; onDone: () => void }) {
  const me = useMe();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; id?: string } | null>(null);
  async function run(label: string, path: string) {
    setBusy(label);
    setMsg(null);
    try {
      const d = await api<IssuedDocument>(path, { method: "POST" });
      setMsg({ ok: true, text: `${d.file_name} emitido (rev. ${d.revision}).`, id: d.id });
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    } finally {
      setBusy(null);
    }
  }
  const can = (perm: string) => me.permissions.includes(perm);
  return (
    <div className="card">
      <div className="card-head"><h2>Generar documentos</h2><span className="small muted">La vista previa no se registra; la emisión queda versionada con SHA-256.</span></div>
      <div className="card-pad stack">
        <div className="table-wrap"><table><tbody>
          {GENERATE.filter(([, , perm]) => can(perm)).map(([kind, label]) => (
            <tr key={kind}><td><b>{label}</b></td>
              <td style={{ width: 300 }} className="row">
                <a className="btn sm" href={`/api/cases/${caseId}/documents/${kind}/preview`} target="_blank" rel="noreferrer">Vista previa</a>
                <button className="btn sm primary" disabled={!!busy} onClick={() => run(kind, `/cases/${caseId}/documents/${kind}`)}>{busy === kind ? "Generando…" : "Emitir PDF"}</button>
              </td></tr>))}
          {can("report.export") && <tr><td><b>Datos del caso (Excel)</b><div className="small muted">Caso, disciplinas, equipo, contención, causas, acciones, eficacia y bitácora.</div></td>
            <td className="row"><button className="btn sm primary" disabled={!!busy} onClick={() => run("xlsx", `/cases/${caseId}/export`)}>{busy === "xlsx" ? "Generando…" : "Exportar Excel"}</button></td></tr>}
        </tbody></table></div>
        {msg && <div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}{msg.id && <> <a href={`/api/documents/${msg.id}/content`} target="_blank" rel="noreferrer">Abrir</a></>}</div>}
      </div>
    </div>
  );
}

function Verify({ id, kind }: { id: string; kind: "documents" | "attachments" }) {
  const [state, setState] = useState<{ ok: boolean; detail: string } | null>(null);
  async function run() {
    try { setState(await api<{ ok: boolean; detail: string }>(`/${kind}/${id}/verify`)); } catch (e) { setState({ ok: false, detail: errorText(e) }); }
  }
  return state ? <Badge tone={state.ok ? "green" : "red"}>{state.detail}</Badge> : <button className="btn sm ghost" onClick={run}>Verificar</button>;
}

export function FilesTab({ caseId, open }: { caseId: string; open: boolean }) {
  const canUpload = useCan("attachment.upload") && open;
  const files = useApi<Attachment[]>(`/cases/${caseId}/attachments`);
  const docs = useApi<DocumentRow[]>(`/cases/${caseId}/documents`);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <Generate caseId={caseId} onDone={docs.reload} />
      <div className="card">
        <div className="card-head"><h2>Documentos emitidos</h2><span className="small muted">Inmutables; cada emisión crea una revisión nueva.</span></div>
        <ErrorBox error={docs.error} onRetry={docs.reload} />
        {docs.loading && !docs.data ? <div className="card-pad"><Loading rows={1} /></div> : !docs.data?.length ? <Empty title="Sin documentos emitidos" /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Archivo</th><th>Tipo</th><th>Rev.</th><th>Estado</th><th>Emitido</th><th>SHA-256</th><th>Integridad</th></tr></thead>
            <tbody>{docs.data.map((d) => (
              <tr key={d.id}>
                <td><a href={`/api/documents/${d.id}/content`} target="_blank" rel="noreferrer">{d.file_name}</a><div className="small muted">{fmtBytes(d.file_size_bytes)} · {d.template_version}</div></td>
                <td>{DOC_TYPE[d.document_type] ?? d.document_type}</td><td>{d.revision}</td>
                <td><Badge tone={d.status === "issued" ? "green" : ""}>{d.status === "issued" ? "Vigente" : "Sustituido"}</Badge></td>
                <td className="small">{fmtDate(d.generated_at, true)}<div className="muted">{d.generated_by_name}</div></td>
                <td className="mono" title={d.sha256_hex}>{d.sha256_hex.slice(0, 16)}…</td>
                <td><Verify id={d.id} kind="documents" /></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      <div className="card">
        <div className="card-head"><h2>Archivos adjuntos</h2>
          {canUpload && <span className="right"><UploadButton caseId={caseId} purpose="general" label="Subir archivo" onDone={files.reload} /></span>}</div>
        <ErrorBox error={files.error} onRetry={files.reload} />
        {files.loading && !files.data ? <div className="card-pad"><Loading rows={1} /></div> : !files.data?.length ? <Empty title="Sin archivos">PNG, JPEG o PDF de hasta 10 MB.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Archivo</th><th>Uso</th><th>Vinculado a</th><th>Subido</th><th>SHA-256</th></tr></thead>
            <tbody>{files.data.map((a) => (
              <tr key={a.id}>
                <td><a href={`/api/attachments/${a.id}/content`} target="_blank" rel="noreferrer">{a.file_name}</a><div className="small muted">{fmtBytes(a.file_size_bytes)}</div></td>
                <td>{{ evidence: "Evidencia", photo: "Foto", general: "General" }[a.purpose] ?? a.purpose}</td>
                <td className="small">{a.containment_id ? "Contención (D3)" : a.cause_id ? "Causa (D4)" : a.action_id ? "Acción (D5–D7)"
                  : a.effectiveness_check_id ? "Eficacia (D6)" : a.system_update_id ? "Documento del sistema (D7)" : "Caso"}</td>
                <td className="small">{fmtDate(a.uploaded_at, true)}<div className="muted">{a.uploaded_by_name}</div></td>
                <td className="mono" title={a.sha256_hex}>{a.sha256_hex.slice(0, 16)}… <Verify id={a.id} kind="attachments" /></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}

type Comment = { id: string; body: string; discipline_code: string | null; created_at: string; author_name: string };

export function CommentsTab({ caseId }: { caseId: string }) {
  const canComment = useCan("comment.create");
  const { data, error, loading, reload, setData } = useApi<Comment[]>(`/cases/${caseId}/comments`);
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    try {
      const c = await api<Comment>(`/cases/${caseId}/comments`, { body: { body } });
      setData([...(data ?? []), c]);
      setBody("");
    } catch (x) {
      setErr(errorText(x));
    }
  }
  return (
    <div className="card">
      <div className="card-head"><h2>Comentarios</h2></div>
      <ErrorBox error={error ?? err} onRetry={reload} />
      <div className="card-pad stack">
        {loading && !data ? <Loading rows={2} /> : !data?.length ? <p className="muted">Sin comentarios.</p> : data.map((c) => (
          <div key={c.id} style={{ borderLeft: "3px solid var(--line)", paddingLeft: 10 }}>
            <div className="small muted"><b style={{ color: "var(--text)" }}>{c.author_name}</b> · {fmtDate(c.created_at, true)}{c.discipline_code && ` · ${c.discipline_code}`}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{c.body}</div>
          </div>))}
        {canComment && (
          <form className="row" onSubmit={send}>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Escribe un comentario…" maxLength={4000} required style={{ minHeight: 44, flex: 1 }} />
            <button className="btn primary">Enviar</button>
          </form>)}
      </div>
    </div>
  );
}

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v).length > 120 ? `${String(v).slice(0, 120)}…` : String(v);
}

export function AuditTab({ caseId }: { caseId: string }) {
  const { data, error, loading, reload } = useApi<AuditEvent[]>(`/cases/${caseId}/audit`);
  return (
    <div className="card">
      <div className="card-head"><h2>Bitácora de auditoría</h2><span className="small muted">Solo inserción: los eventos no se editan ni se borran.</span></div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <div className="card-pad"><Loading /></div> : !data?.length ? <Empty title="Sin eventos" /> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Fecha</th><th>Usuario</th><th>Evento</th><th>Cambios</th></tr></thead>
          <tbody>{data.map((e) => {
            const keys = Array.from(new Set([...Object.keys(e.old_values ?? {}), ...Object.keys(e.new_values ?? {})]));
            const meta = e.metadata as { discipline?: string; comment?: string };
            return (
              <tr key={e.id}>
                <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtDate(e.occurred_at, true)}</td>
                <td>{e.actor_name ?? "—"}</td>
                <td>{EVENT[e.event_type] ?? e.event_type}{meta.discipline && <> <Badge tone="navy">{meta.discipline}</Badge></>}</td>
                <td className="small">
                  {keys.slice(0, 6).map((k) => <div key={k}><span className="muted">{k}:</span> {show(e.old_values?.[k])} → <b>{show(e.new_values?.[k])}</b></div>)}
                  {meta.comment && <div className="muted">«{meta.comment}»</div>}
                </td>
              </tr>);
          })}</tbody>
        </table></div>
      )}
    </div>
  );
}
