"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { ALERT_STATUS, fmtDate } from "@/lib/labels";
import type { AlertSummary } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading, Modal } from "@/components/ui";

const src = (id: string) => `/api/attachments/${id}/content`;

function Thumb({ id, kind, size }: { id: string | null; kind: "nok" | "ok"; size: number }) {
  return (
    <span className={`athumb ${kind}`} style={{ width: size, height: Math.round(size * 0.66) }}>
      {id ? <img src={src(id)} alt={kind === "nok" ? "Foto NOK" : "Foto OK"} loading="lazy" /> : <span className="muted small">—</span>}
    </span>
  );
}

export default function AlertsPage() {
  const { data, error, loading, reload } = useApi<AlertSummary[]>("/alerts");
  const [view, setView] = useState<AlertSummary | null>(null);
  // Revisión vigente de cada alerta (la lista viene por número desc. y revisión desc.).
  const latest = (data ?? []).filter((a, i, all) => all.findIndex((b) => b.alert_number === a.alert_number) === i && a.status !== "superseded");
  const gallery = latest.filter((a) => a.nok_photo_id || a.ok_photo_id).slice(0, 5);
  return (
    <>
      <div className="page-head"><div><h1>Alertas de calidad</h1><div className="sub">Todas las revisiones; solo una vigente por alerta.</div></div></div>
      {gallery.length > 0 && (
        <div className="agallery">
          {gallery.map((a) => (
            <button key={a.id} className="card acard" onClick={() => setView(a)} title="Ver fotografías">
              <div className="apair"><Thumb id={a.nok_photo_id} kind="nok" size={110} /><Thumb id={a.ok_photo_id} kind="ok" size={110} /></div>
              <div className="row" style={{ gap: 6 }}><span className="mono small">{a.folio}</span>
                <Badge tone={a.failure_type === "external" ? "red" : "blue"}>{a.failure_type === "external" ? "Externa" : "Interna"}</Badge></div>
              <div className="atitle">{a.title}</div>
            </button>))}
        </div>
      )}
      <div className="card">
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <div className="card-pad"><Loading /></div> : !data?.length ? (
          <Empty title="Sin alertas">Las alertas se crean desde la disciplina D3 de un caso.</Empty>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>Folio</th><th>Rev.</th><th>Fotos</th><th>Tipo</th><th>Título</th><th>Caso</th><th>Estado</th><th>Emitida</th><th>PDF</th></tr></thead>
            <tbody>{data.map((a) => (
              <tr key={a.id}>
                <td className="mono"><Link href={`/alertas/${a.id}`}>{a.folio}</Link></td><td>{a.revision}</td>
                <td>{a.nok_photo_id || a.ok_photo_id ? (
                  <button className="apair link" onClick={() => setView(a)} aria-label={`Ver fotografías de ${a.folio}`}>
                    <Thumb id={a.nok_photo_id} kind="nok" size={46} /><Thumb id={a.ok_photo_id} kind="ok" size={46} /></button>
                ) : <span className="muted small">Sin fotos</span>}</td>
                <td><Badge tone={a.failure_type === "external" ? "red" : "blue"}>{a.failure_type === "external" ? "Externa" : "Interna"}</Badge></td>
                <td>{a.title}</td><td className="mono"><Link href={`/casos/${a.case_id}`}>{a.case_folio}</Link></td>
                <td><Badge tone={a.status === "issued" ? "green" : a.status === "draft" ? "blue" : ""}>{ALERT_STATUS[a.status]}</Badge></td>
                <td className="small">{fmtDate(a.issued_at, true)}</td>
                <td>{a.document_id ? <a href={`/api/documents/${a.document_id}/content`} target="_blank" rel="noreferrer">PDF</a> : "—"}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      {view && (
        <Modal title={`${view.folio} rev. ${view.revision} · ${view.title}`} onClose={() => setView(null)}>
          <div className="grid g2">
            {(["nok", "ok"] as const).map((kind) => {
              const id = kind === "nok" ? view.nok_photo_id : view.ok_photo_id;
              return (
                <div key={kind} className="stack" style={{ gap: 8 }}>
                  <Badge tone={kind === "nok" ? "red" : "green"}>{kind === "nok" ? "NOK — condición incorrecta" : "OK — condición correcta"}</Badge>
                  <div className="aview">{id ? <img src={src(id)} alt={kind} /> : <span className="muted small">Sin foto</span>}</div>
                </div>);
            })}
          </div>
          <div className="row" style={{ marginTop: 14 }}><Link className="btn primary right" href={`/alertas/${view.id}`}>Abrir alerta</Link></div>
        </Modal>
      )}
    </>
  );
}
