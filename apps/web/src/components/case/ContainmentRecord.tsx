"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { DISPOSITION, EMAIL_EVENT, fmtDate } from "@/lib/labels";
import type { Case, ContainmentRecord as Rec } from "@/lib/types";
import { Badge, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";

const nowLocal = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div style={{ background: "#fff", border: "1px solid var(--line)", borderRadius: 10, padding: "10px 14px", minWidth: 120 }}>
      <div className="small muted">{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: tone }}>{value}</div>
    </div>
  );
}

/** D3: inicio (aviso a logística con la alerta en PDF), lotes revisados y fin con resultado. */
export function ContainmentRecordPanel({ c, editable, onChanged }: { c: Case; editable: boolean; onChanged: () => void }) {
  const canEdit = useCan("containment.edit") && editable;
  const { data, setData, error, loading, reload } = useApi<Rec>(`/cases/${c.id}/containment-record`);
  const [modal, setModal] = useState<"start" | "lot" | "end" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState<Record<string, string>>({});
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  async function call(path: string, body: unknown, method = "POST") {
    setBusy(true);
    try {
      const r = await api<Rec>(path, { method, body });
      setData(r);
      setErr(null);
      setModal(null);
      setF({});
      onChanged();
      // El correo se envía tras guardar: se refresca su estado en un momento.
      setTimeout(() => void reload(), 2500);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading rows={2} />;
  const rec = data?.record;
  const t = data?.totals;
  const phase = !rec ? "Sin iniciar" : rec.ended_at ? "Finalizada" : "En curso";

  return (
    <div className="card">
      <div className="card-head"><h2>Registro de contención</h2>
        <Badge tone={!rec ? "" : rec.ended_at ? (rec.result === "effective" ? "green" : "red") : "amber"}>{phase}</Badge>
        <div className="right row">
          {canEdit && !rec && <button className="btn primary sm" onClick={() => setModal("start")}>Iniciar contención</button>}
          {canEdit && rec && !rec.ended_at && <>
            <button className="btn sm" onClick={() => setModal("lot")}>+ Lote revisado</button>
            <button className="btn ok sm" onClick={() => setModal("end")} disabled={!data?.lots.length}>Finalizar contención</button></>}
          {canEdit && rec && <button className="btn ghost sm" disabled={busy} onClick={() => call(`/cases/${c.id}/containment-record/notify`, {})}>Reenviar a logística</button>}
        </div></div>
      <div className="card-pad stack">
        <ErrorBox error={error ?? err} onRetry={reload} />
        {!rec ? (
          <div className="notice info small">Al iniciar, se envía un correo a <b>logística</b> para detener el material para su re-inspección, con la
            alerta de calidad vigente en PDF. Requiere la alerta emitida y los correos de logística configurados en Administración.</div>
        ) : (
          <>
            <div className="row" style={{ alignItems: "stretch" }}>
              <Stat label="Inicio" value={fmtDate(rec.started_at, true)} />
              <Stat label="Fin" value={rec.ended_at ? fmtDate(rec.ended_at, true) : "—"} />
              <Stat label="Lotes" value={t?.lots ?? 0} />
              <Stat label="Piezas validadas" value={(t?.inspected ?? 0).toLocaleString("es-MX")} />
              <Stat label="OK" value={(t?.ok ?? 0).toLocaleString("es-MX")} tone="var(--ok)" />
              <Stat label="Rechazadas" value={(t?.rejected ?? 0).toLocaleString("es-MX")} tone={t?.rejected ? "var(--bad)" : undefined} />
            </div>
            {rec.ended_at && <div className={`notice ${rec.result === "effective" ? "ok" : "error"} small`}>
              <b>Resultado: {rec.result === "effective" ? "contención eficaz" : "contención no eficaz"}.</b> {rec.result_notes} — {rec.ended_by_name}</div>}
            <div className="table-wrap"><table>
              <thead><tr><th>Lote</th><th>Ubicación</th><th>Revisadas</th><th>Rechazadas</th><th>Disposición</th><th>Notas</th><th></th></tr></thead>
              <tbody>
                {!data?.lots.length && <tr><td colSpan={7} className="muted">Aún no hay lotes registrados.</td></tr>}
                {data?.lots.map((l) => (
                  <tr key={l.id}><td className="mono">{l.lot_number}</td><td>{l.location ?? "—"}</td>
                    <td>{l.quantity_inspected.toLocaleString("es-MX")}</td><td>{l.quantity_rejected.toLocaleString("es-MX")}</td>
                    <td>{l.disposition ? DISPOSITION[l.disposition] : "—"}</td><td className="small">{l.notes ?? "—"}</td>
                    <td>{canEdit && !rec.ended_at && <button className="btn sm ghost" onClick={() => call(`/containment-lots/${l.id}`, undefined, "DELETE")}>Quitar</button>}</td></tr>))}
              </tbody>
            </table></div>
          </>
        )}
        {!!data?.emails.length && (
          <div>
            <h3 style={{ marginBottom: 6 }}>Correos del caso</h3>
            <div className="table-wrap"><table><tbody>{data.emails.map((m) => (
              <tr key={m.id}>
                <td className="small">{fmtDate(m.created_at, true)}</td>
                <td><Badge tone="navy">{EMAIL_EVENT[m.event] ?? m.event}</Badge></td>
                <td className="small">{m.to_addresses.join(", ")}</td>
                <td><Badge tone={m.status === "sent" ? "green" : m.status === "failed" ? "red" : "amber"}>
                  {m.status === "sent" ? `Enviado${m.transport === "file" ? " (archivo .eml)" : ""}` : m.status === "failed" ? "Falló" : "En cola"}</Badge>
                  {m.last_error && <div className="small" style={{ color: "var(--bad)" }}>{m.last_error}</div>}</td>
              </tr>))}</tbody></table></div>
          </div>
        )}
      </div>
      {modal && (
        <Modal title={{ start: "Iniciar contención", lot: "Lote revisado", end: "Finalizar contención" }[modal]} onClose={() => setModal(null)}>
          <form className="stack" onSubmit={(e) => {
            e.preventDefault();
            if (modal === "start") void call(`/cases/${c.id}/containment-record/start`, { started_at: f.started_at ? new Date(f.started_at).toISOString() : null });
            if (modal === "lot") void call(`/cases/${c.id}/containment-lots`, { lot_number: f.lot_number, location: f.location || null,
              quantity_inspected: Number(f.quantity_inspected || 0), quantity_rejected: Number(f.quantity_rejected || 0),
              disposition: f.disposition || null, notes: f.notes || null });
            if (modal === "end") void call(`/cases/${c.id}/containment-record/end`, { result: f.result || "effective", result_notes: f.result_notes,
              ended_at: f.ended_at ? new Date(f.ended_at).toISOString() : null });
          }}>
            {modal === "start" && <>
              <Field label="Inicio de la contención" hint="Por defecto, ahora."><input type="datetime-local" value={f.started_at ?? nowLocal()} max={nowLocal()} onChange={set("started_at")} /></Field>
              <div className="notice warn small">Se enviará el aviso a logística para <b>detener el material</b>, con la alerta de calidad en PDF.</div>
            </>}
            {modal === "lot" && <div className="grid g2">
              <Field label="Lote" required><input value={f.lot_number ?? ""} onChange={set("lot_number")} required maxLength={100} /></Field>
              <Field label="Ubicación"><input value={f.location ?? ""} onChange={set("location")} placeholder="Almacén, tránsito, cliente…" /></Field>
              <Field label="Piezas revisadas" required><input type="number" min={0} value={f.quantity_inspected ?? ""} onChange={set("quantity_inspected")} required /></Field>
              <Field label="Piezas rechazadas"><input type="number" min={0} value={f.quantity_rejected ?? ""} onChange={set("quantity_rejected")} /></Field>
              <Field label="Disposición"><select value={f.disposition ?? ""} onChange={set("disposition")}>
                <option value="">—</option>{Object.entries(DISPOSITION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Notas"><input value={f.notes ?? ""} onChange={set("notes")} /></Field>
            </div>}
            {modal === "end" && <>
              <Field label="Resultado" required><select value={f.result ?? "effective"} onChange={set("result")}>
                <option value="effective">Contención eficaz</option><option value="not_effective">Contención no eficaz</option></select></Field>
              <Field label="Justificación del resultado" required><textarea value={f.result_notes ?? ""} onChange={set("result_notes")} minLength={5} required /></Field>
              <Field label="Fin de la contención" hint="Por defecto, ahora."><input type="datetime-local" value={f.ended_at ?? nowLocal()} max={nowLocal()} onChange={set("ended_at")} /></Field>
            </>}
            <ErrorBox error={err} />
            <div className="row"><button type="button" className="btn" onClick={() => setModal(null)}>Cancelar</button>
              <button className="btn primary right" disabled={busy}>{busy ? "Guardando…" : "Confirmar"}</button></div>
          </form>
        </Modal>
      )}
    </div>
  );
}
