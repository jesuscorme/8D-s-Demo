# PROGRESS — 8D PRO

**Última actualización:** 2026-10-27 (sesión 2, bloque 2) · **Versión:** 1.0.0 · **Estado:** MVP D0–D8 integrado, listo para piloto controlado
**Avance funcional estimado del MVP (fases 0–11):** ≈ 95 % (cálculo abajo). Fase 12 (integraciones) fuera de alcance.

## Verificación real

| Comprobación | Resultado |
|---|---|
| `scripts/setup-db.ps1` + `migrate.ps1` (0001–0006) en `d8_demo` | ✅ aplicadas |
| `pytest -q` (apps/api) | ✅ **61 pasadas** (unitarias + integración en BD temporal `d8_demo_test`) |
| `scripts/e2e.ps1` (Playwright en Edge, BD y storage temporales) | ✅ **2 pasadas**: alta de caso → D0 con requisito visible → envío → aprobación por gerente → persistencia tras recargar → PDF real → bitácora; consulta solo lectura, 403 en API, reportes, lecciones, cierre de sesión |
| `npx tsc --noEmit` / `npm run build` (apps/web) | ✅ sin errores / 13 rutas |
| Recorrido por el proxy (login, cookie, CSRF, logout) | ✅ |
| Recorrido en Edge (Playwright): inicio, casos, alta de caso, D5–D8, emisión de PDF, bitácora, reportes, móvil 390 px | ✅ sin errores de consola (solo 404 de favicon) |
| `backup.ps1` → `restore.ps1 -Database d8_restore_check` | ✅ manifiesto verificado; base restaurada hasta 0006 |
| Lint | — no configurado (ESLint desactivado en el build; tipos estrictos con `tsc`) |

Prueba integral `test_complete_8d_cycle`: crear caso → equipo → D0–D4 (contención, alerta emitida, Ishikawa, causa validada con evidencia) → D5 correctiva ligada a causa raíz + criterio aprobado → D6 implementación con evidencia aprobada por otra persona, verificación con dato faltante (solo «datos insuficientes»), verificación eficaz → D7 preventiva con excepción justificada + AMEF actualizado → D8 lección aprobada → caso cerrado → lección publicada, reutilizada en otro caso y revisada (rev. 2 sustituye a rev. 1) → 8D completo PDF (rev. 1 → rev. 2 sustituida y conservada), avance, auditoría, lección PDF, Excel del caso, de casos y de bitácora → integridad (detecta archivo alterado) → bitácora con `request_id`/`txid` → KPIs → reapertura por D8.
Negativas: permisos (403 en cada aprobación/emisión/exportación), datos incompletos (409 con detalle), archivos inválidos (422), acceso entre organizaciones (404), fallo de generación de PDF (500 sin registro), bloqueo de login (429), inmutabilidad en BD.

## Estado por fase

| Fase | Estado | Notas |
|---|---|---|
| 0 Arquitectura | ✅ | Docs actualizados; pendientes de negocio en DECISIONS.md |
| 1 Interfaz y navegación | ✅ | Todas las secciones con datos reales |
| 2 Identidad y roles | ✅ | Cambio de contraseña (cierra otras sesiones), restablecimiento por admin, alta de plantas, roles por planta, bloqueo de login. Sin recuperación por correo (requiere correo/SSO) |
| 3 Casos y flujo D0–D8 | ✅ | Requisitos, bloqueos, aprobación, reapertura, cierre |
| 4 D3 y alerta | ✅ | Logo de la organización en todos los PDF (admin lo sube) |
| 5 Ishikawa y biblioteca | ✅ | Subcausas en árbol dentro de cada categoría |
| 6 Validación de causas | ✅ | 5 porqués estructurados en D4 |
| 7 Acciones | ✅ | Tipos, vínculo causa-acción-evidencia, aprobación con segregación, excepción justificada, vencimientos |
| 8 Eficacia | ✅ | Criterio configurable aprobado, denominador explícito, datos faltantes ≠ 0, días sin producción, historial inmutable |
| 9 Lecciones | ✅ | Estados, revisión por persona distinta, revisiones, búsqueda/filtros, reutilización trazada, PDF |
| 10 Documentos, Excel, KPIs, auditoría | ✅ | 6 entregables reales, vista previa, versiones, integridad, 9 KPIs definidos |
| 11 Pruebas, seguridad, piloto | 🟡 85 % | E2E automatizado y pruebas de concurrencia/doble envío hechas. Falta: piloto con casos reales y ejecución en un servidor de CI |
| 12 Integraciones | ⬜ | Interfaces documentadas en ARCHITECTURE.md |

**Cálculo:** pesos F0 5, F1 6, F2 9, F3 12, F4 9, F5 7, F6 7, F7 10, F8 7, F9 8, F10 10, F11 10 × avance (F0 100, F1 100, F2 100, F3 100, F4 100, F5 100, F6 100, F7 100, F8 100, F9 100, F10 95, F11 85) ≈ **98 %**; se declara ≈ 95 % porque el piloto con usuarios reales no se ha hecho.

## Cambios de esta sesión
- **Migraciones:** `0005_alert_photos_cascade.sql` (defecto encontrado al ejecutar las pruebas), `0006_actions_effectiveness_lessons.sql`.
- **API nuevos:** `routers/actions.py`, `routers/lessons.py`, `routers/reports.py`, `effectiveness_rules.py`, `pdf_reports.py`, `excel.py`.
- **API modificados:** `workflow.py` (D5–D8 y cierre), `cases.py`, `permissions.py`, `auth.py` (eventos de seguridad), `audit.py` (`txid`, eventos de seguridad), `routers/auth_routes.py` (bloqueo), `routers/containment.py` (vínculos de adjuntos), `routers/alerts.py` (descarga autorizada y auditada), `routers/core.py` (alertas del tablero), `routers/cases_routes.py` (fecha objetivo), `storage.py` (verificación, Excel), `main.py` (request-id), `requirements.txt` (+openpyxl).
- **Web:** `components/case/Actions.tsx` (nuevo), `Workflow.tsx`, `Tabs.tsx`, `DisciplineForm.tsx`, páginas `lecciones`, `lecciones/[id]`, `reportes`, inicio; `lib/types.ts`, `lib/labels.ts`, `Shell.tsx`.
- **Pruebas:** `test_effectiveness_reports.py`, `integration/test_full_cycle.py`; actualizadas `test_workflow.py`, `test_units.py`, `integration/test_flow.py`.
- **Scripts:** `backup.ps1`, `restore.ps1`, `start-web.ps1`. **Docs:** README, ARCHITECTURE, DATA_MODEL, SECURITY, DECISIONS, USER_GUIDE.
- **Datos:** BD `d8_demo` con seed (organización, 2 plantas, 6 usuarios). Los 2 casos de prueba creados durante la verificación se borraron; sus eventos de bitácora permanecen (solo inserción) y el siguiente folio será `…-0003`.

## Limitaciones conocidas y pendientes reales
1. Piloto con casos representativos (Fase 11) — requiere usuarios del cliente.
2. Ejecutar `pytest` + `scripts/e2e.ps1` en un servidor de CI (hoy se ejecutan en este equipo). Sin pruebas de carga.
3. Recuperación de contraseña por correo (depende de la integración de correo o SSO).
4. Plantillas PDF solo en español.
5. Idioma: el contenido de las lecciones admite es/en; la interfaz y las plantillas solo están en español.
6. Firma electrónica legal no implementada (ver SECURITY.md).
7. Limpieza de archivos huérfanos de `storage/` y política de retención.
8. Puertos 3000/8000 ocupados en este equipo por la demo SPC: 8D PRO usa 3010/8010.

## Bloque 2 de la sesión 2
- Migración `0007_org_logo.sql`. API: `POST /auth/password`, restablecimiento y plantas visibles en `PATCH /admin/users`, `POST /admin/plants`, logo (`POST /admin/organization/logo`, `GET /organization/logo`) dibujado en alerta y reportes.
- Web: diálogo «Contraseña», administración (plantas, plantas por usuario, restablecer, logo), subcausas, 5 porqués.
- Pruebas: `integration/test_admin_concurrency.py` (8 altas en paralelo con folios consecutivos únicos; doble envío y doble aprobación simultáneos → 200/409 con un solo evento), `apps/web/e2e/flow.spec.ts`, `scripts/e2e.ps1`.
- Scripts nuevos guardados con BOM UTF-8 (PowerShell 5.1 mostraba mal los acentos).

## Siguiente bloque recomendado
Piloto controlado: cargar 3–5 casos reales con usuarios de calidad, recoger defectos y decidir los pendientes P1–P7 de
DECISIONS.md. En paralelo, E2E en CI (Playwright en Edge) a partir del recorrido usado en esta sesión.

## Bloque 3 (2026-10-27)
- Lecciones con **antes y después visual**: fotos con leyenda por lado (migraciones `0008_lesson_photos.sql`, `0009_lesson_photos_cascade.sql`), obligatorias para enviar a revisión, copiadas en cada nueva revisión e inmutables fuera de borrador (disparador). Sección «Antes y después» en pantalla y en el PDF (una foto por celda; corrige un fallo de reportlab al partir celdas con varias imágenes).
- Se importó un 8D real de cliente en la base local (sus datos y el documento original no se versionan). Lecciones publicadas en rev. 2 con fotos.
- `pytest`: **62 pasadas**.

## Bloque 4 (2026-10-29)
- **8D internos y externos**: `cases_8d.case_type` obligatorio en la interfaz (la API lo deduce del origen si falta); orígenes por tipo; cliente obligatorio solo en externos; la alerta toma el tipo del caso. Campos del concentrado: `report_date`, `market_segment` (OEM/OES/AM), `main_defect`.
- **Ishikawa con incidencias**: `incidence_count` por causa (editable aun con la causa decidida), participación por categoría, orden por incidencias e historial automático (en cuántos 8D apareció la causa y en cuántos fue raíz); sugerencias del catálogo ordenadas también por historial.
- **Registro de contención (D3)**: inicio, fin, lotes (revisadas/rechazadas/disposición), totales y resultado con justificación. D3 exige inicio, lotes y fin con resultado.
- **Correo**: bandeja `email_outbox` (envío tras el commit, estado y error, reintento), destinatarios por evento y planta. Iniciar la contención → aviso a logística «detener material para re-inspección» con la alerta vigente en PDF; emitir la alerta → equipo del 8D y lista de difusión con el PDF. Transporte SMTP o archivo .eml (por defecto sin SMTP_HOST).
- **Tablero visual** (KPIs, dona de estados, 8D por cliente, abiertos vs cerrados 6 meses, recientes con fecha límite, mis tareas) y **Concentrado** con hitos D3 24 h · D4 48 h · D5–D7 7 días · D8 14 días desde el reporte, filtros y Excel.
- Migración `0010_internal_containment_email.sql`. `pytest`: **66 pasadas**; E2E **2/2**.
- Datos de demostración: se eliminó de la base local el 8D importado del cliente (caso, lecciones, archivos, planta y usuarios; dos usuarios referenciados por la bitácora quedaron anonimizados e inactivos). Nuevo caso demo cerrado `case_closed_ford` en `app.demo_data` (externo, Ford, hitos en plazo); los clientes demo son armadoras.
- **Tablero interactivo** (tipo Power BI): filtros de tipo, estado, cliente, mes trabajado, defecto, planta y mercado; clic en tarjetas, dona, barras y meses filtra todo el tablero (cada gráfico no se filtra por su propia dimensión); nuevos gráficos de defecto principal y cumplimiento de hitos. Se calcula en el navegador a partir de `/reports/register`.
- **Historial demo** `python -m app.demo_history`: 23 8D de mayo a octubre (9 armadoras, internos y externos, 16 cerrados), creados por la API y con fechas de reporte, aprobación y cierre ajustadas a la línea de tiempo simulada (la bitácora conserva la fecha real).
- **Fotografías en alertas** (se ven en el detalle de cada alerta, sección «Fotografías NOK / OK»; la lista de alertas no cambia). Los datos demo generan ilustraciones NOK/OK por tipo de defecto (`demo_data.photo`, `Demo.alert_photos`) y las asignan a la alerta antes de emitirla. En la base local, las alertas de casos abiertos que no tenían fotos recibieron revisiones nuevas con fotos (rev. 2 y rev. 3, que corrige la leyenda); las alertas de casos cerrados no admiten revisión y siguen sin fotos.
- **Seed de la base demo** en `db/seed/` (CSV por tabla, archivos y `load_seed.py`; ver su README). Sin hashes de contraseña ni correos reales; la contraseña se asigna al cargar con `--password`.
- **Navegación simplificada**: «Casos 8D» es la única lista (tabla del concentrado con hitos, filtros y Excel); «Concentrado» y «Reportes» salen del menú y sus rutas redirigen ahí. Los documentos emitidos se consultan en cada caso (pestaña «Documentos y archivos»); la vista global de indicadores y las exportaciones de casos y bitácora quedan sin pantalla (los endpoints siguen). El Inicio queda solo con el selector Externos/Internos y gráficos cruzados (se agrega «8D por responsable», por líder del 8D); sin barra de filtros ni tabla. El historial demo reparte el liderazgo entre 4 ingenieros.
- `scripts/start-web.ps1` no compila: después de cambiar la web hay que ejecutar `npm run build` antes de arrancar.
- Pendiente: **envío real de correo** — requiere credenciales SMTP (ver SECURITY.md); hoy los correos se generan como .eml en `storage/outbox`.
