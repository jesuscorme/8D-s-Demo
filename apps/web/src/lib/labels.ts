export const CASE_STATUS: Record<string, string> = {
  draft: "Borrador", open: "Abierto", in_progress: "En proceso", pending_review: "En revisión",
  approved: "Aprobado", closed: "Cerrado", cancelled: "Cancelado",
};
export const SEVERITY: Record<string, string> = { low: "Baja", medium: "Media", high: "Alta", critical: "Crítica" };
export const SOURCE: Record<string, string> = {
  customer_complaint: "Reclamación de cliente", internal: "Detección en planta", supplier: "Proveedor", audit: "Auditoría", other: "Otro",
};
export const DISCIPLINE_STATUS: Record<string, string> = {
  not_started: "Sin iniciar", in_progress: "En curso", pending_review: "En revisión", approved: "Aprobada", blocked: "Bloqueada",
};
export const CONTAINMENT_STATUS: Record<string, string> = {
  open: "Abierta", in_progress: "En curso", implemented: "Implementada", verified: "Verificada", cancelled: "Cancelada",
};
export const ALERT_STATUS: Record<string, string> = {
  draft: "Borrador", issued: "Vigente", superseded: "Sustituida", retired: "Retirada",
};
export const CAUSE_STATUS: Record<string, string> = {
  pending: "Pendiente", investigating: "En investigación", root_cause: "Causa raíz",
  not_root_cause: "No es causa raíz", needs_more_investigation: "Requiere más investigación",
};
export const ANSWER: Record<string, string> = { yes: "Sí", no: "No", unknown: "Sin dato", not_applicable: "N/A" };
export const TEAM_ROLE: Record<string, string> = { leader: "Líder", champion: "Patrocinador", member: "Integrante" };
export const EVENT: Record<string, string> = {
  "case.created": "Caso creado", "case.updated": "Caso actualizado", "case.cancelled": "Caso cancelado",
  "case.team_changed": "Equipo modificado", "discipline.updated": "Disciplina editada",
  "discipline.submitted": "Enviada a revisión", "discipline.approved": "Disciplina aprobada",
  "discipline.rejected": "Disciplina rechazada", "discipline.reopened": "Disciplina reabierta",
  "containment.created": "Contención registrada", "containment.updated": "Contención actualizada",
  "attachment.uploaded": "Archivo adjuntado", "alert.created": "Alerta creada", "alert.updated": "Alerta editada",
  "alert.photos_changed": "Fotos de alerta", "alert.issued": "Alerta emitida", "alert.revision_started": "Nueva revisión de alerta",
  "cause.added": "Causa agregada", "cause.updated": "Causa editada", "cause.deleted": "Causa eliminada",
  "cause.validated": "Validación de causa", "comment.created": "Comentario",
};

export function fmtDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return withTime
    ? d.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" })
    : d.toLocaleDateString("es-MX", { dateStyle: "medium" });
}

export function fmtBytes(n: number): string {
  return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

export const ACTION_TYPE: Record<string, string> = { corrective: "Correctiva", preventive: "Preventiva", systemic: "Sistémica" };
export const ACTION_STATUS: Record<string, string> = {
  open: "Abierta", in_progress: "En curso", pending_approval: "Pendiente de aprobación", approved: "Implementada y aprobada",
  verified: "Eficaz (verificada)", ineffective: "No eficaz", cancelled: "Cancelada",
};
export const UPDATE_TYPE: Record<string, string> = {
  pfmea: "AMEF de proceso", dfmea: "AMEF de diseño", control_plan: "Plan de control", work_instruction: "Instrucción de trabajo",
  visual_aid: "Ayuda visual", training: "Capacitación", other: "Otro",
};
export const UPDATE_STATUS: Record<string, string> = { planned: "Planificada", completed: "Completada", cancelled: "Cancelada" };
export const EFFECT: Record<string, string> = {
  pending: "Pendiente", effective: "Eficaz", ineffective: "No eficaz", insufficient_data: "Datos insuficientes",
};
export const THRESHOLD: Record<string, string> = { max_defects: "Máximo de defectos", max_rate_ppm: "Tasa máxima (ppm)", max_rate_percent: "Tasa máxima (%)" };
export const CRITERION_STATUS: Record<string, string> = { draft: "Borrador", approved: "Aprobado", retired: "Retirado" };
export const LESSON_STATUS: Record<string, string> = {
  draft: "Borrador", in_review: "En revisión", approved: "Aprobada", published: "Publicada", superseded: "Sustituida", retired: "Retirada",
};
export const OUTCOME: Record<string, string> = { applied: "Aplicada", partially_applied: "Aplicada parcialmente", not_applicable: "No aplica" };
export const DOC_TYPE: Record<string, string> = {
  "8d_full": "Expediente 8D", "8d_progress": "Reporte de avance", quality_alert: "Alerta de calidad", lesson_learned: "Lección aprendida",
  audit_report: "Reporte de auditoría", excel_export: "Exportación Excel", other: "Otro",
};
Object.assign(EVENT, {
  "action.created": "Acción creada", "action.updated": "Acción editada", "action.started": "Acción iniciada",
  "action.submitted": "Acción enviada a aprobación", "action.approved": "Acción aprobada", "action.rejected": "Acción rechazada",
  "action.reopened": "Acción reabierta", "action.cancelled": "Acción cancelada", "system_update.created": "Actualización documental",
  "system_update.updated": "Actualización documental editada", "criterion.created": "Criterio de eficacia", "criterion.approved": "Criterio aprobado",
  "criterion.retired": "Criterio retirado", "effectiveness.recorded": "Verificación registrada", "effectiveness.decided": "Resultado de eficacia",
  "lesson.created": "Lección creada", "lesson.updated": "Lección editada", "lesson.submitted": "Lección enviada a revisión",
  "lesson.approved": "Lección aprobada", "lesson.rejected": "Lección rechazada", "lesson.published": "Lección publicada",
  "lesson.superseded": "Lección sustituida", "lesson.retired": "Lección retirada", "lesson.revision_started": "Nueva revisión de lección",
  "lesson.applied": "Lección reutilizada", "document.issued": "Documento emitido", "document.downloaded": "Documento descargado",
  "integrity.verified": "Integridad verificada", "lesson.photos_changed": "Fotos antes/después de la lección",
});
export const CASE_TYPE: Record<string, string> = { internal: "Interno", external: "Externo" };
// Orígenes válidos por tipo de 8D.
export const SOURCES_BY_TYPE: Record<string, string[]> = {
  external: ["customer_complaint", "other"],
  internal: ["internal", "supplier", "audit", "other"],
};
export const SEGMENTS = ["OEM", "OES", "AM"];
// Sugerencias para «Cliente»: armadoras automotrices (el campo admite otro nombre).
export const OEM_CUSTOMERS = ["Ford", "General Motors", "Toyota", "Stellantis", "Nissan", "Honda", "Volkswagen", "BMW",
  "Mercedes-Benz", "Hyundai", "Kia", "Mazda", "Tesla"];
export const DISPOSITION: Record<string, string> = {
  released: "Liberado", rework: "Retrabajo", scrap: "Desecho", returned: "Devuelto", on_hold: "Retenido",
};
export const MILESTONE_STATUS: Record<string, string> = { on_time: "A tiempo", late: "Tarde", pending: "En plazo", overdue: "Vencido" };
export const EMAIL_EVENT: Record<string, string> = {
  containment_started: "Aviso a logística", alert_issued: "Alerta emitida", test: "Prueba",
};
Object.assign(EVENT, {
  "containment.started": "Contención iniciada (aviso a logística)", "containment.notified": "Aviso a logística reenviado",
  "containment.lot_added": "Lote revisado", "containment.lot_deleted": "Lote eliminado", "containment.ended": "Contención finalizada",
});