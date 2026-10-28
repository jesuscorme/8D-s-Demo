# Modelo de datos

Migraciones en `db/migrations/` (aplicar con `scripts/migrate.ps1`):

| Archivo | Contenido |
|---|---|
| `0001_identity.sql` | organizations, plants, users, roles, user_roles, sessions, counters, audit_events (+ disparadores de solo inserción) |
| `0002_cases.sql` | cases_8d, case_team, case_disciplines, case_comments |
| `0003_containment_documents.sql` | containment_actions, attachments, quality_alerts, alert_photos, documents (+ inmutabilidad) |
| `0004_ishikawa.sql` | ishikawa_categories (6M), cause_ideas (24 ideas base), ishikawa_causes, cause_validations (+ disparadores) |
| `0005_alert_photos_cascade.sql` | Corrección: borrado en cascada de fotos de alerta |
| `0006_actions_effectiveness_lessons.sql` | corrective_actions, system_updates, effectiveness_criteria, effectiveness_checks, lessons_learned, lesson_applications, login_attempts; vínculos de adjuntos y documentos; `cases_8d.target_close_date` |

## Fases 7–10 (migración 0006)

- **corrective_actions:** tipos `corrective | preventive | systemic` (la contención sigue en `containment_actions`). CHECK: una correctiva exige `cause_id`; el backend exige además que sea causa raíz confirmada. Pasar a `pending_approval`/`approved` exige evidencia **o** excepción justificada; aprobado exige aprobador y fecha.
- **system_updates (D7):** AMEF, plan de control, instrucción, ayuda visual, capacitación; «completada» exige fecha y evidencia.
- **effectiveness_criteria:** indicador, unidad del defecto, **denominador explícito** (`units_produced`, `units_inspected`, `lots_received`, `shipments`, `other` + etiqueta), límite (`max_defects`, `max_rate_ppm`, `max_rate_percent`), días mínimos con producción y denominador mínimo. Aprobado = inmutable (disparador); se retira y se crea otro.
- **effectiveness_checks:** periodo, `denominator_quantity`/`defect_quantity` **NULL = sin dato** (nunca cero), días sin producción, `computed_result` (regla) y `result` (decisión con justificación). «Eficaz/no eficaz» exige ambos datos (CHECK). Decidida = inmutable (disparador). La regla `defect_quantity <= denominador` del DDL original se aplica solo cuando el denominador son unidades.
- **lessons_learned:** una fila por revisión (`lesson_number`, `revision`); estados `draft → in_review → approved → published → superseded | retired`; una revisión abierta y una publicada por número (índices parciales); solo el borrador cambia de contenido (disparador). Autor, quien envió, revisor/aprobador, publicador y retiro con fechas.
- **lesson_applications:** revisión publicada × caso destino, evaluación y resultado; no se modifica (disparador).
- **documents:** `case_id` opcional (exportaciones de organización), `lesson_id`; `metadata.scope` agrupa las revisiones de un mismo documento.
- **login_attempts:** intentos para el bloqueo temporal (5 fallos / 15 min).

## Cambios respecto al DDL de referencia del plan

1. **Aislamiento multiempresa:** toda relación entre tablas de negocio usa clave compuesta `(organization_id, id)`. El DDL original no la tenía en `cause_validations.cause_id`, `corrective_actions.cause_id`, `effectiveness_checks.action_id`, `documents.alert_id`, `attachments.*` ni `lesson_applications.lesson_id`.
2. **`user_roles`:** la PK original incluía `plant_id` nullable (no válido en PostgreSQL). Ahora: `id` + `unique nulls not distinct (user_id, role_id, plant_id)`.
3. **Usuarios:** `password_hash` (scrypt) y correo único global.
4. **Sesiones** (`sessions`) con hash del token y revocación.
5. **Numeración:** tabla `counters` y `cases_8d.folio` único por organización.
6. **Casos:** `problem_description` admite vacío en borrador (D2 lo exige); `detected_quantity`, `cancel_reason`, `is_demo`, `version` (concurrencia optimista).
7. **Disciplinas:** `submitted_by/at`, `review_comment`; `content` JSONB solo con campos permitidos por disciplina (validados en backend).
8. **Contención:** implementar/verificar exige evidencia (CHECK); `verified_by`, cantidades revisadas/rechazadas.
9. **Alertas:** una sola revisión vigente y un solo borrador por número (índices parciales); revisiones emitidas inmutables (disparador); `revision_reason` obligatorio desde rev. 2; `alert_photos` NOK/OK.
10. **Documentos:** `superseded_by`, `template_version` obligatoria; contenido inmutable (disparador).
11. **Causas:** `parent_cause_id` (subcausas), estado vigente solo vía validación (disparador); `cause_validations` con `decision`, responsable y fecha; CHECK: causa raíz/descartada exige método, evidencia y justificación; historial de solo inserción.
12. **Catálogo:** `cause_ideas.organization_id` nullable (NULL = catálogo base compartido de solo lectura).
13. **Auditoría:** `case_id` para consultar la bitácora por expediente; UPDATE/DELETE/TRUNCATE bloqueados por disparador.
14. Sin `pgcrypto`: `gen_random_uuid()` es nativo desde PostgreSQL 13.

## Pendientes del modelo
- Retención y archivado (no definidos por el negocio).
- Tabla de revisiones de plantillas: hoy la versión de plantilla está en código (`pdf_reports.TEMPLATES`) y se registra en cada documento.

| `0008_lesson_photos.sql` / `0009_…` | Fotos antes/después de la lección (solo editables en borrador) |
