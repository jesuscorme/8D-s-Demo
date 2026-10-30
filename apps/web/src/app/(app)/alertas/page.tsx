"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { ALERT_STATUS, fmtDate } from "@/lib/labels";
import type { AlertSummary } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";

export default function AlertsPage() {
  const { data, error, loading, reload } = useApi<AlertSummary[]>("/alerts");
  return (
    <>
      <div className="page-head"><div><h1>Alertas de calidad</h1><div className="sub">Todas las revisiones; solo una vigente por alerta.</div></div></div>
      <div className="card">
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <div className="card-pad"><Loading /></div> : !data?.length ? (
          <Empty title="Sin alertas">Las alertas se crean desde la disciplina D3 de un caso.</Empty>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>Folio</th><th>Rev.</th><th>Tipo</th><th>Título</th><th>Caso</th><th>Estado</th><th>Emitida</th><th>PDF</th></tr></thead>
            <tbody>{data.map((a) => (
              <tr key={a.id}>
                <td className="mono"><Link href={`/alertas/${a.id}`}>{a.folio}</Link></td><td>{a.revision}</td>
                <td><Badge tone={a.failure_type === "external" ? "red" : "blue"}>{a.failure_type === "external" ? "Externa" : "Interna"}</Badge></td>
                <td>{a.title}</td><td className="mono"><Link href={`/casos/${a.case_id}`}>{a.case_folio}</Link></td>
                <td><Badge tone={a.status === "issued" ? "green" : a.status === "draft" ? "blue" : ""}>{ALERT_STATUS[a.status]}</Badge></td>
                <td className="small">{fmtDate(a.issued_at, true)}</td>
                <td>{a.document_id ? <a href={`/api/documents/${a.document_id}/content`} target="_blank" rel="noreferrer">PDF</a> : "—"}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}
