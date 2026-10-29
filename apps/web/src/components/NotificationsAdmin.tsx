"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { EMAIL_EVENT, fmtDate } from "@/lib/labels";
import type { EmailRow, Plant } from "@/lib/types";
import { Badge, ErrorBox, Field } from "@/components/ui";
import { useMe } from "@/components/Shell";

type Data = {
  recipients: { id: string; event: string; email: string; name: string | null; plant_code: string | null }[];
  events: Record<string, string>;
  settings: { transport: string; from: string; smtp_host: string | null; smtp_port: number | null; smtp_user: string | null; file_dir: string | null };
};

/** Destinatarios por evento, correo de prueba y bandeja de salida. */
export function NotificationsAdmin({ plants }: { plants: Plant[] }) {
  const { data, setData, error, reload } = useApi<Data>("/admin/notifications");
  const outbox = useApi<EmailRow[]>("/admin/email/outbox");
  const [f, setF] = useState({ event: "containment_started", email: "", name: "", plant_id: "" });
  const me = useMe();
  const [testTo, setTestTo] = useState(me.user.email);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      setData(await api<Data>("/admin/notifications", { body: { event: f.event, email: f.email, name: f.name || null, plant_id: f.plant_id || null } }));
      setF({ ...f, email: "", name: "" });
      setMsg(null);
    } catch (x) { setMsg({ ok: false, text: errorText(x) }); }
  }
  async function remove(id: string) {
    try { setData(await api<Data>(`/admin/notifications/${id}`, { method: "DELETE" })); } catch (x) { setMsg({ ok: false, text: errorText(x) }); }
  }
  async function test() {
    try {
      await api("/admin/email/test", { body: { to: testTo } });
      setMsg({ ok: true, text: `Correo de prueba enviado a ${testTo}. Revisa su estado en la bandeja de salida.` });
      setTimeout(() => void outbox.reload(), 2500);
    } catch (x) { setMsg({ ok: false, text: errorText(x) }); }
  }
  async function retry(id: string) {
    try { await api(`/admin/email/outbox/${id}/retry`, { method: "POST" }); setTimeout(() => void outbox.reload(), 2000); } catch (x) { setMsg({ ok: false, text: errorText(x) }); }
  }

  const s = data?.settings;
  return (
    <div className="card">
      <div className="card-head"><h2>Notificaciones por correo</h2>
        {s && <Badge tone={s.transport === "smtp" ? "green" : "amber"}>{s.transport === "smtp" ? `SMTP ${s.smtp_host}:${s.smtp_port}` : "Modo archivo (.eml)"}</Badge>}</div>
      <div className="card-pad stack">
        <ErrorBox error={error} onRetry={reload} />
        {s?.transport === "file" && <div className="notice warn small">Sin servidor SMTP configurado: los correos se guardan como archivos .eml en
          <span className="mono"> {s.file_dir}</span> (se abren con Outlook). Para envío real define SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD y EMAIL_FROM en .env.</div>}
        <div className="grid g2">
          {Object.entries(data?.events ?? {}).map(([event, label]) => (
            <div key={event} className="card" style={{ padding: 14 }}>
              <h3 style={{ marginBottom: 6 }}>{label}</h3>
              <p className="small muted" style={{ margin: "0 0 8px" }}>{event === "containment_started"
                ? "Al iniciar la contención: detener material para re-inspección (adjunta la alerta en PDF)."
                : "Al emitir la alerta de calidad: se envía al equipo del 8D y a esta lista (adjunta el PDF)."}</p>
              {(data?.recipients.filter((r) => r.event === event) ?? []).map((r) => (
                <div key={r.id} className="row small" style={{ padding: "4px 0", borderBottom: "1px solid var(--line-2)" }}>
                  <span className="mono">{r.email}</span>{r.name && <span className="muted">{r.name}</span>}
                  <Badge>{r.plant_code ?? "Todas las plantas"}</Badge>
                  <button className="btn sm ghost right" onClick={() => remove(r.id)}>Quitar</button>
                </div>))}
              {!data?.recipients.some((r) => r.event === event) && <p className="small muted">Sin destinatarios.</p>}
            </div>))}
        </div>
        <form className="row" onSubmit={add} style={{ alignItems: "flex-end" }}>
          <Field label="Evento"><select value={f.event} onChange={(e) => setF({ ...f, event: e.target.value })}>
            {Object.entries(data?.events ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Correo"><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} placeholder="logistica@empresa.com" /></Field>
          <Field label="Nombre"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Planta"><select value={f.plant_id} onChange={(e) => setF({ ...f, plant_id: e.target.value })}>
            <option value="">Todas</option>{plants.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}</select></Field>
          <button className="btn primary">Agregar</button>
        </form>
        <div className="row" style={{ alignItems: "flex-end", borderTop: "1px solid var(--line-2)", paddingTop: 12 }}>
          <Field label="Enviar correo de prueba a"><input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} style={{ minWidth: 280 }} /></Field>
          <button className="btn" onClick={test} type="button">Enviar prueba</button>
        </div>
        {msg && <div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}</div>}
        <div>
          <div className="row" style={{ marginBottom: 6 }}><h3>Bandeja de salida</h3><button className="btn sm ghost right" onClick={() => void outbox.reload()}>Actualizar</button></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Fecha</th><th>Evento</th><th>Caso</th><th>Para</th><th>Asunto</th><th>Adjuntos</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {!outbox.data?.length && <tr><td colSpan={8} className="muted">Sin correos.</td></tr>}
              {outbox.data?.map((m) => (
                <tr key={m.id}>
                  <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtDate(m.created_at, true)}</td>
                  <td><Badge tone="navy">{EMAIL_EVENT[m.event] ?? m.event}</Badge></td>
                  <td className="mono small">{m.case_folio ?? "—"}</td>
                  <td className="small">{m.to_addresses.join(", ")}</td>
                  <td className="small">{m.subject}</td>
                  <td className="small">{m.attachments?.map((a) => a.file_name).join(", ") || "—"}</td>
                  <td><Badge tone={m.status === "sent" ? "green" : m.status === "failed" ? "red" : "amber"}>{m.status === "sent" ? "Enviado" : m.status === "failed" ? "Falló" : "En cola"}</Badge>
                    <div className="small muted">{m.transport === "file" ? "archivo .eml" : m.transport ?? ""}</div>
                    {m.last_error && <div className="small" style={{ color: "var(--bad)" }}>{m.last_error}</div>}</td>
                  <td>{m.status === "failed" && <button className="btn sm" onClick={() => retry(m.id)}>Reintentar</button>}</td>
                </tr>))}
            </tbody>
          </table></div>
        </div>
      </div>
    </div>
  );
}
