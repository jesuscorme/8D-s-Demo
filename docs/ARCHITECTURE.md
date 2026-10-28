# Arquitectura — 8D PRO

## Vista general

```
Navegador ──► Next.js (apps/web, :3010) ──/api/*──► FastAPI (apps/api, :8010) ──► PostgreSQL 16 (d8_demo)
                 │  proxy mismo origen                     ├──► storage/ (archivos privados)
                 │  cookie httpOnly d8_session             ├──► reportlab (PDF + QR) · openpyxl (Excel)
                 │  middleware: redirige a /login          └──► audit_events (solo inserción)
```

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| Interfaz | `apps/web` (Next.js 15, React 19, TS) | Pantallas y estados de carga/vacío/error. No decide reglas: refleja lo que devuelve la API. |
| Proxy | `apps/web/src/app/api/[...path]/route.ts` | Reenvía cookies y cabeceras; mismo origen, sin CORS. |
| API | `apps/api/app/routers/*` | Autenticación, permiso por endpoint, validación Pydantic, una transacción por petición. |
| Reglas puras | `workflow.py` (D0–D8), `causes_rules.py`, `effectiveness_rules.py` | Requisitos, transiciones, sugerencias, regla de eficacia. Sin E/S; pruebas unitarias. |
| Servicios | `pdf_alert.py`, `pdf_reports.py`, `excel.py`, `storage.py`, `audit.py` | Presentación (solo dibujan datos ya autorizados), archivos, bitácora. |
| Datos | `db/migrations/0001…0006` | Esquema, restricciones y disparadores de inmutabilidad. |

| Router | Alcance |
|---|---|
| `auth_routes` | login (con bloqueo temporal), logout, sesión |
| `core` | usuarios, plantas, tablero de inicio, administración |
| `cases_routes` | casos, equipo, disciplinas y transiciones, comentarios, bitácora |
| `containment` / `alerts` | D3, adjuntos, alertas versionadas, descarga de documentos |
| `ishikawa` | D4: catálogo, sugerencias, causas, validaciones |
| `actions` | D5–D7: acciones, actualizaciones del sistema, criterios y verificaciones de eficacia |
| `lessons` | biblioteca, revisión/aprobación/publicación/retiro, revisiones, reutilización |
| `reports` | PDF (8D, avance, auditoría, lección), vista previa, Excel, integridad, KPIs |

## Petición típica
1. Middleware: identificador de solicitud (`X-Request-ID`) y defensa CSRF (cabecera `x-d8-client`).
2. `require("permiso")` carga la sesión y registra un evento de seguridad si se deniega.
3. `load_case(..., for_update=True)` filtra organización y planta y bloquea la fila del caso: las operaciones del mismo caso se serializan.
4. Se construye la `Snapshot` y el módulo puro valida (`RuleError` → 409 con detalle).
5. Se escribe el cambio y `audit.record` guarda antes/después, solicitud y `txid` de PostgreSQL.
6. `refresh_case_status` recalcula el estado (D8 aprobada → cerrado con fecha).

## Flujo D0–D8
- Estados por disciplina: `not_started → in_progress → pending_review → approved`; rechazo → `in_progress`; reapertura (comentario) solo de la última enviada/aprobada. Caso cerrado: solo se reabre D8.
- Cada disciplina congela su sección al enviarse: campos de D0/D2, equipo (D1), contención (D3), causas (D4), definición de correctivas (D5), implementación y eficacia (D6), preventivas y documentos (D7).
- Requisitos: ver `requirements()` en `app/workflow.py` (se muestran tal cual en la interfaz).

## Documentos
`issue_document()` guarda un archivo nuevo, registra la fila en `documents` con revisión transaccional (`counters`) y marca
«sustituida» la emisión vigente anterior del mismo alcance. Los disparadores impiden modificar el contenido de documentos,
alertas emitidas, lecciones no borrador, criterios aprobados y verificaciones decididas. Si la generación falla, la
transacción se revierte y la API responde `500 document_failed` sin registrar emisión.

## Integraciones futuras (Fase 12, no implementadas)
| Integración | Interfaz prevista |
|---|---|
| ERP/MES | Importar producción/defectos como `effectiveness_checks` (mismo endpoint `POST /actions/{id}/checks`); maestro de partes/clientes |
| Correo / Teams | Suscriptor a `audit_events` (aprobaciones pendientes, vencimientos) |
| SharePoint/DMS | Publicar `documents` emitidos (archivo + SHA-256 + revisión) |
| SSO (OIDC/SAML) | `users.auth_provider/auth_subject` ya existen; reemplaza el login local |
| IA contextual | Sugerencias en `/cases/{id}/suggestions`, siempre como hipótesis; requiere aprobación de privacidad, costo y evaluación |
