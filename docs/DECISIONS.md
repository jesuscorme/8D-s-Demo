# Decisiones técnicas

## Confirmadas (2026-10-27)

| # | Decisión | Motivo |
|---|---|---|
| 1 | Stack: FastAPI + psycopg 3 + PostgreSQL 16 nativo; Next.js 15 + TypeScript | Mismo stack ya probado en el proyecto SPC del equipo (Windows, sin Docker). Menos piezas nuevas. |
| 2 | Migraciones SQL numeradas aplicadas por `scripts/migrate.ps1` con SHA-256 | DDL legible y revisable; una migración aplicada nunca se edita. |
| 3 | Sesiones de servidor con cookie httpOnly + SameSite=Lax; solo se guarda el SHA-256 del token | Revocables al cerrar sesión o desactivar usuario. Sin JWT que no se pueda invalidar. |
| 4 | Contraseñas con `hashlib.scrypt` (biblioteca estándar) | Sin dependencia nueva; parámetros n=2^14, r=8, p=1. |
| 5 | Roles fijos por organización: admin, quality_manager, engineer, viewer; permisos en `app/permissions.py` | Suficiente para el MVP; matriz explícita y probada. |
| 6 | Correo único global | El inicio de sesión no pide organización. |
| 7 | Folios: `8D-<PLANTA>-<AÑO>-<NNNN>` con contador por planta (no reinicia por año); alertas `QA-NNNN` por organización | Numeración transaccional (`INSERT … ON CONFLICT … RETURNING`), nunca `MAX()+1`. |
| 8 | Flujo D0–D8 secuencial con aprobación por gerente de calidad | Regla simple y auditable; ver pendiente P2. |
| 9 | `reportlab` + `pillow` para PDF y QR | Única dependencia nueva de negocio; genera PDF y QR sin servicios externos. |
| 10 | Archivos en `storage/` (privado), tipo validado por firma real (PNG/JPEG/PDF), máx. 10 MB, nunca se sobrescriben | Plan: almacenamiento privado y versiones preservadas. |
| 11 | Causas del caso copian el texto de la idea del catálogo | Cambios posteriores del catálogo no alteran expedientes. |
| 12 | Historial de validación de causas de solo inserción; el estado vigente lo fija un disparador | El estado no puede cambiar sin una validación registrada. |
| 13 | Defensa CSRF: SameSite=Lax + cabecera obligatoria `x-d8-client: web` en métodos que modifican | Un formulario de otro sitio no puede añadir la cabecera. |
| 14 | Sugerencias de causas por reglas (etiquetas de proceso/defecto) | IA generativa fuera hasta aprobar privacidad, costo y evaluación (plan, Fase 5). |

| 15 | Acciones en tabla propia; la contención sigue en `containment_actions` | Ciclos de vida distintos (D3 vs D5–D7) |
| 16 | Segregación: quien envía una acción no la aprueba; el autor/remitente de una lección no la revisa | Control mínimo de cuatro ojos donde el plan exige aprobación |
| 17 | Eficacia: «eficaz» solo si la regla con datos completos lo respalda; dato faltante = NULL, nunca cero | Principio del plan (Fase 8) |
| 18 | D8 exige lección aprobada o publicada; su aprobación cierra el caso | Cierre con conocimiento reutilizable |
| 19 | Documentos: revisión por alcance (`counters`), emisión anterior «sustituida», archivos nunca sobrescritos | Plan: nueva emisión no sobrescribe |
| 20 | `openpyxl` para Excel | Misma versión que el proyecto SPC; sin alternativa en la biblioteca estándar |
| 21 | Bloqueo de login 5 fallos / 15 min por correo | Mitigación de fuerza bruta sin infraestructura externa |

## Pendientes (requieren decisión del negocio)

| # | Tema | Situación actual |
|---|---|---|
| P1 | ¿El aprobador de una **disciplina** puede ser quien la envió? | Hoy sí (registrado). Para acciones y lecciones ya se exige otra persona. |
| P2 | ¿D3 puede avanzar en paralelo a D2? | Hoy es estrictamente secuencial. |
| P3 | ¿Toda D3 exige alerta emitida? | Hoy sí, para cualquier origen. |
| P4 | Tamaño mínimo del equipo D1 | Hoy 3 integrantes con líder. |
| P5 | Alta de plantas y roles por planta desde la interfaz | El modelo lo soporta (`user_roles.plant_id`); la UI solo asigna roles a toda la organización. |
| P6 | Logo de la organización en la alerta | Hoy el encabezado muestra el nombre de la organización (sin logo). |
| P7 | Política de retención, firma electrónica y respaldo | No definidas. |
| P8 | Umbrales de los KPIs (n mínimo 3 y 5) | Valores iniciales propuestos; ajustar con el cliente. |
