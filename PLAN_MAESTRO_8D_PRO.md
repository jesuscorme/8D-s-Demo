# 8D PRO --- Plan maestro de desarrollo para Claude Code

**Versión:** 1.0 \| **Estado:** propuesta para validar en Fase 0

## Objetivo

Construir una aplicación web de calidad para gestionar casos 8D desde D0
hasta D8, con flujo guiado, causas potenciales e investigación, acciones
correctivas, verificación de eficacia, alertas, documentos versionados,
lecciones aprendidas y auditoría.

## Cómo usar este plan para optimizar tokens

-   Mantener este archivo en la raíz como `PLAN_MAESTRO_8D_PRO.md`.
-   Ejecutar una fase por vez; no pedir a Claude que implemente todo el
    producto en una sola sesión.
-   Al inicio de cada fase, leer este plan y `docs/PROGRESS.md`.
-   Inspeccionar el repositorio antes de editar. No reemplazar trabajo
    existente sin justificarlo.
-   No avanzar a otra fase hasta pasar los criterios de aceptación.
-   Al final, actualizar `docs/PROGRESS.md` con entregables, archivos
    modificados, pruebas ejecutadas, errores, riesgos y siguiente paso.
-   No implementar características futuras por adelantado, excepto
    arquitectura y estructura de datos necesarias.

## Flujo de información

``` mermaid
flowchart TD
 A[Usuarios / captura / archivos] --> B[Validación y normalización]
 B --> C[(PostgreSQL)]
 B --> D[(Almacenamiento privado de archivos)]
 C --> E[Expediente 8D D0-D8]
 E --> F[D3 contención]
 F --> G[Alerta de calidad PDF + QR]
 E --> H[Ishikawa + biblioteca de causas]
 H --> I[Matriz de validación con evidencia]
 I --> J[Acciones correctivas y preventivas]
 J --> K[Verificación de eficacia]
 K --> L[Lecciones aprendidas]
 E --> M[PDF completo / avance / Excel / KPIs]
 C --> N[Bitácora de auditoría]
 D --> O[Versiones + SHA-256]
 N --> P[Historial y auditoría]
 O --> P
```

## Principios del producto

1.  Flujo D0--D8 guiado: mostrar pendientes y bloquear transiciones si
    faltan requisitos obligatorios.
2.  No confirmar causa raíz solo por respuestas Sí/No; exigir método de
    verificación, evidencia y justificación.
3.  Diferenciar procedimiento inexistente/inadecuado de incumplimiento
    de un procedimiento existente.
4.  Documentos emitidos inmutables: una nueva emisión crea una nueva
    revisión; nunca sobrescribir el histórico.
5.  Permisos aplicados en backend, no solo ocultando controles en
    frontend.
6.  Preparar interfaz y documentos para español e inglés.
7.  El hash SHA-256 apoya la verificación de integridad; por sí solo no
    demuestra identidad ni validez legal de una firma.
8.  No prometer cumplimiento automático con IATF o requisitos de
    cliente; cada organización valida sus reglas.
9.  ERP/MES, correo, Teams, SharePoint/DMS, SSO e IA generativa son
    integraciones posteriores salvo aprobación expresa.

## Arquitectura propuesta

Inspeccionar primero el repositorio. Si ya existe un stack, conservarlo
salvo razón documentada. Si se parte de cero, proponer una aplicación
web modular con API, PostgreSQL, migraciones versionadas y
almacenamiento privado de archivos. Mantener secretos fuera del código.
Los PDFs y Excel deben generarse mediante servicios separados de la
lógica de negocio.

## Modelo de datos conceptual

``` mermaid
erDiagram
 ORGANIZATIONS ||--o{ PLANTS : contains
 ORGANIZATIONS ||--o{ USERS : employs
 PLANTS ||--o{ CASES_8D : owns
 USERS ||--o{ CASES_8D : opens
 CASES_8D ||--o{ CASE_TEAM : has
 CASES_8D ||--o{ CASE_DISCIPLINES : tracks
 CASES_8D ||--o{ CONTAINMENT_ACTIONS : contains
 CASES_8D ||--o{ ISHIKAWA_CAUSES : investigates
 ISHIKAWA_CATEGORIES ||--o{ ISHIKAWA_CAUSES : classifies
 ISHIKAWA_CAUSES ||--o{ CAUSE_VALIDATIONS : validates
 CASES_8D ||--o{ CORRECTIVE_ACTIONS : defines
 CORRECTIVE_ACTIONS ||--o{ EFFECTIVENESS_CHECKS : verifies
 CASES_8D ||--o{ QUALITY_ALERTS : issues
 CASES_8D ||--o{ DOCUMENTS : generates
 CASES_8D ||--o{ AUDIT_EVENTS : records
 LESSONS_LEARNED ||--o{ LESSON_APPLICATIONS : reused_in
 CASES_8D ||--o{ LESSON_APPLICATIONS : links
```

## Fases de desarrollo

### Fase 0 --- Descubrimiento y arquitectura

Inspeccionar stack, estructura, dependencias y pruebas. Definir
multiempresa/multiplanta, roles, estados D0--D8, reglas de transición,
estrategia de archivos, seguridad y migraciones. Revisar el DDL de abajo
sin ejecutarlo directamente.

**Entregables:** `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
`docs/DATA_MODEL.md`, `docs/SECURITY.md`, `docs/PROGRESS.md`.

**Aceptación:** decisiones técnicas documentadas, pendientes explícitos,
DDL revisado y estrategia de migraciones aprobada. No implementar
funciones de negocio.

### Fase 1 --- Esqueleto visual y navegación

Crear layout, navegación lateral, encabezado y páginas base: Inicio,
Casos 8D, Catálogo de causas, Lecciones aprendidas, Alertas, Reportes y
Administración. Estilo: sidebar azul marino, fondo claro, acento azul,
tablas/tarjetas minimalistas.

**Aceptación:** navegación funcional, diseño responsivo y estados de
carga/vacío/error; cualquier dato simulado debe estar identificado.

### Fase 2 --- Identidad, roles y organizaciones

Implementar autenticación según arquitectura, organizaciones, plantas,
usuarios, roles y permisos. Verificar autorización en servidor y
aislamiento entre organizaciones.

**Aceptación:** pruebas positivas y negativas de acceso; ningún usuario
puede leer o modificar datos ajenos sin permiso.

### Fase 3 --- Casos 8D y flujo D0--D8

Crear, editar, buscar, filtrar y asignar casos; folio único; problema,
cliente, producto/número de parte, proceso, lote, fecha, cantidades,
severidad, equipo y responsables. Estados por disciplina, requisitos
pendientes, comentarios y adjuntos.

**Aceptación:** borradores guardables; backend impide avanzar con
requisitos obligatorios faltantes; cambios críticos auditables.

### Fase 4 --- D3 y alerta de calidad

Registrar contención, responsable, vencimiento y evidencia. Generar
alerta PDF con logo/encabezado, tipo interno/externo, folio,
qué/cuándo/dónde/quién/cómo, áreas y cantidad afectada, fotos NOK/OK,
fecha y responsable. QR debe llevar a una página autenticada.

**Aceptación:** PDF imprimible, control de tamaño/tipo de archivo,
revisión versionada y versiones previas preservadas.

### Fase 5 --- Ishikawa y biblioteca de causas

Diagrama editable con Método, Máquina, Material, Mano de obra, Medición
y Medio ambiente. Biblioteca de ideas con etiquetas de proceso/defecto y
sugerencias contextuales basadas inicialmente en reglas. Las sugerencias
son hipótesis, no conclusiones.

**Aceptación:** causas del caso no cambian si después se modifica el
catálogo; IA generativa queda fuera hasta aprobar privacidad, costo y
evaluación.

### Fase 6 --- Validación de causas

Matriz con causa potencial, ¿documentada?, ¿se siguió el proceso?,
método de verificación, evidencia, justificación, responsable, fecha y
estado: pendiente, en investigación, causa raíz, no es causa raíz o
requiere más investigación. Incluir 5 porqués y causa de ocurrencia/no
detección/punto de escape cuando se priorice.

**Aceptación:** no se confirma causa raíz automáticamente por Sí/No;
historial de decisión disponible.

### Fase 7 --- Acciones correctivas y preventivas

Vincular acciones con causas, responsables, fechas, estado, evidencia y
aprobación. Registrar actualización de AMEF/FMEA, plan de control,
instrucciones, ayudas visuales y capacitación cuando aplique.

**Aceptación:** implementación requiere evidencia o excepción
justificada; vencimientos visibles y vínculo causa-acción-evidencia.

### Fase 8 --- Eficacia

Registrar periodo, producción, defectos, criterio de aceptación,
evidencia, responsable y resultado. Configurar criterio por
caso/producto/cliente. Manejar días sin producción y datos faltantes.

**Aceptación:** no asumir universalmente cero defectos por 30 días;
datos faltantes nunca equivalen a cero.

### Fase 9 --- Lecciones aprendidas

Biblioteca independiente con problema, causa verificada, acciones,
eficacia, antes/después, documentos actualizados, capacitación,
aplicabilidad y español/inglés. Estados: borrador, revisión, aprobada,
publicada, retirada. Búsqueda, difusión y reutilización vinculada a otro
caso sin modificar el original.

**Aceptación:** solo lecciones publicadas pueden reutilizarse; las
revisiones anteriores quedan disponibles.

### Fase 10 --- Documentos, Excel, reportes y auditoría

Generar: 8D completo PDF, avance PDF, alerta D3 PDF, lección aprendida
PDF, reporte de auditoría/historial y exportaciones Excel. Añadir
indicadores iniciales acordados, plantillas versionadas, emisor, fecha,
revisión, hash y registro de sustitución.

**Aceptación:** nueva emisión no sobrescribe la anterior; exportaciones
respetan permisos; auditoría registra usuario, fecha, entidad y cambios
aplicables.

### Fase 11 --- Pruebas, seguridad y piloto

Pruebas unitarias, integración y extremo a extremo; permisos, archivos
inválidos, doble envío, errores de PDF, concurrencia, instalación
limpia, migraciones, respaldo y restauración. Ejecutar piloto con casos
representativos.

**Aceptación:** flujo completo probado desde apertura hasta documentos y
lecciones; sin defectos críticos/altos abiertos sin aceptación formal
del riesgo.

### Fase 12 --- Integraciones posteriores

Priorizar ERP/MES, importación de producción, correo/Teams,
SharePoint/DMS, SSO, IA contextual y KPIs avanzados solo después de
estabilizar el MVP.

## Contrato de trabajo para Claude Code

En cada fase: 1. Lee este archivo y `docs/PROGRESS.md`. 2. Inspecciona
el código actual antes de editar. 3. Resume alcance y archivos
previstos. 4. Implementa exclusivamente la fase solicitada. 5. No añadas
dependencias sin justificarlo. 6. Ejecuta pruebas reales; no declares
éxito si no se ejecutaron. 7. Actualiza `docs/PROGRESS.md`. 8. Informa
archivos modificados, pruebas, pendientes, riesgos y comandos para
validar. 9. Si una decisión cambia seguridad, datos o flujo de negocio,
pregunta antes de asumir.

### Prompt de inicio --- Fase 0

``` text
Lee PLAN_MAESTRO_8D_PRO.md completo y revisa el repositorio. No implementes funciones de negocio todavía.

Trabaja exclusivamente en Fase 0:
- Inspecciona stack, estructura, dependencias, pruebas y estado actual.
- Compara el repositorio con el plan.
- Identifica decisiones pendientes, contradicciones y riesgos.
- Revisa el DDL de referencia sin ejecutarlo.
- Propón arquitectura y estrategia de migraciones compatibles con el proyecto.
- Crea/actualiza únicamente los documentos de Fase 0.
- No borres ni reescribas trabajo existente sin justificarlo.
- Ejecuta comprobaciones disponibles y reporta resultados reales.

Entrega decisiones confirmadas/pendientes, archivos modificados, pruebas, riesgos y criterio de aprobación. No avances a Fase 1.
```

### Prompt reutilizable para fases posteriores

``` text
Lee PLAN_MAESTRO_8D_PRO.md y docs/PROGRESS.md.
Implementa exclusivamente la Fase [NÚMERO — NOMBRE].
Inspecciona el código antes de editar y conserva decisiones aprobadas.
No implementes fases futuras ni añadas dependencias sin justificarlo.
Trabaja incrementalmente, ejecuta pruebas y actualiza docs/PROGRESS.md.
Si falta una decisión que afecte el modelo de datos, seguridad o flujo de negocio, detente y pregunta.
Entrega archivos modificados, pruebas reales, pendientes, riesgos y criterio de aceptación.
```

## DDL inicial de referencia --- PostgreSQL

**Advertencia:** esquema conceptual inicial, no migración lista para
producción. Revisar relaciones, aislamiento multiempresa, restricciones,
borrado, índices y numeración. Convertir a migraciones versionadas y
probar antes de ejecutar.

``` sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE organizations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 name TEXT NOT NULL,
 code TEXT NOT NULL UNIQUE,
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE plants (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 code TEXT NOT NULL,
 name TEXT NOT NULL,
 timezone TEXT NOT NULL DEFAULT 'America/Mexico_City',
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (organization_id, code),
 UNIQUE (organization_id, id)
);

CREATE TABLE users (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 email TEXT NOT NULL,
 display_name TEXT NOT NULL,
 auth_provider TEXT,
 auth_subject TEXT,
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (organization_id, email),
 UNIQUE (auth_provider, auth_subject),
 UNIQUE (organization_id, id)
);

CREATE TABLE roles (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 code TEXT NOT NULL,
 name TEXT NOT NULL,
 UNIQUE (organization_id, code),
 UNIQUE (organization_id, id)
);

CREATE TABLE user_roles (
 organization_id UUID NOT NULL REFERENCES organizations(id),
 user_id UUID NOT NULL,
 role_id UUID NOT NULL,
 plant_id UUID,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY (user_id, role_id, plant_id),
 FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id),
 FOREIGN KEY (organization_id, role_id) REFERENCES roles(organization_id, id),
 FOREIGN KEY (organization_id, plant_id) REFERENCES plants(organization_id, id)
);

CREATE TABLE cases_8d (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 plant_id UUID NOT NULL,
 case_number BIGINT NOT NULL,
 title TEXT NOT NULL,
 problem_description TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft'
  CHECK (status IN ('draft','open','in_progress','pending_review','approved','closed','cancelled')),
 severity TEXT NOT NULL DEFAULT 'medium'
  CHECK (severity IN ('low','medium','high','critical')),
 source_type TEXT,
 customer_name TEXT,
 product_name TEXT,
 part_number TEXT,
 process_name TEXT,
 lot_number TEXT,
 defect_date DATE,
 affected_quantity INTEGER CHECK (affected_quantity IS NULL OR affected_quantity >= 0),
 opened_by UUID NOT NULL,
 owner_user_id UUID,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 closed_at TIMESTAMPTZ,
 UNIQUE (organization_id, plant_id, case_number),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, plant_id) REFERENCES plants(organization_id, id),
 FOREIGN KEY (organization_id, opened_by) REFERENCES users(organization_id, id),
 FOREIGN KEY (organization_id, owner_user_id) REFERENCES users(organization_id, id)
);

CREATE INDEX idx_cases_org_status ON cases_8d(organization_id, status);
CREATE INDEX idx_cases_plant_updated ON cases_8d(plant_id, updated_at DESC);

CREATE TABLE case_team (
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 user_id UUID NOT NULL,
 team_role TEXT NOT NULL DEFAULT 'member',
 added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY (case_id, user_id),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id)
);

CREATE TABLE case_disciplines (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 discipline_code TEXT NOT NULL CHECK (discipline_code IN ('D0','D1','D2','D3','D4','D5','D6','D7','D8')),
 status TEXT NOT NULL DEFAULT 'not_started'
  CHECK (status IN ('not_started','in_progress','pending_review','approved','blocked')),
 content JSONB NOT NULL DEFAULT '{}'::JSONB,
 owner_user_id UUID,
 completed_at TIMESTAMPTZ,
 approved_by UUID,
 approved_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (case_id, discipline_code),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, owner_user_id) REFERENCES users(organization_id, id),
 FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id)
);

CREATE TABLE containment_actions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 description TEXT NOT NULL,
 responsible_user_id UUID,
 due_date DATE,
 status TEXT NOT NULL DEFAULT 'open'
  CHECK (status IN ('open','in_progress','implemented','verified','cancelled')),
 evidence_notes TEXT,
 implemented_at TIMESTAMPTZ,
 verified_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, responsible_user_id) REFERENCES users(organization_id, id)
);

CREATE TABLE ishikawa_categories (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 code TEXT NOT NULL UNIQUE,
 name_es TEXT NOT NULL,
 name_en TEXT NOT NULL,
 display_order SMALLINT NOT NULL
);

INSERT INTO ishikawa_categories (code, name_es, name_en, display_order) VALUES
 ('METHOD','Método','Method',1),
 ('MACHINE','Máquina','Machine',2),
 ('MATERIAL','Material','Material',3),
 ('MANPOWER','Mano de obra','Manpower',4),
 ('MEASUREMENT','Medición','Measurement',5),
 ('ENVIRONMENT','Medio ambiente','Mother Nature / Environment',6)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE cause_ideas (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 category_id UUID NOT NULL REFERENCES ishikawa_categories(id),
 title_es TEXT NOT NULL,
 title_en TEXT,
 description_es TEXT,
 description_en TEXT,
 process_tags TEXT[] NOT NULL DEFAULT '{}',
 defect_tags TEXT[] NOT NULL DEFAULT '{}',
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ishikawa_causes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 category_id UUID NOT NULL REFERENCES ishikawa_categories(id),
 source_idea_id UUID REFERENCES cause_ideas(id),
 potential_cause TEXT NOT NULL,
 added_by UUID,
 investigation_status TEXT NOT NULL DEFAULT 'pending'
  CHECK (investigation_status IN ('pending','investigating','root_cause','not_root_cause','needs_more_investigation')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, added_by) REFERENCES users(organization_id, id)
);

CREATE TABLE cause_validations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 cause_id UUID NOT NULL REFERENCES ishikawa_causes(id),
 documented_answer TEXT NOT NULL DEFAULT 'unknown'
  CHECK (documented_answer IN ('yes','no','unknown','not_applicable')),
 followed_process_answer TEXT NOT NULL DEFAULT 'unknown'
  CHECK (followed_process_answer IN ('yes','no','unknown','not_applicable')),
 verification_method TEXT,
 evidence_summary TEXT,
 rationale TEXT,
 validated_by UUID,
 validated_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (organization_id, validated_by) REFERENCES users(organization_id, id)
);

CREATE TABLE corrective_actions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 cause_id UUID REFERENCES ishikawa_causes(id),
 action_type TEXT NOT NULL DEFAULT 'corrective'
  CHECK (action_type IN ('containment','corrective','preventive','systemic')),
 description TEXT NOT NULL,
 responsible_user_id UUID,
 due_date DATE,
 status TEXT NOT NULL DEFAULT 'open'
  CHECK (status IN ('open','in_progress','implemented','pending_approval','approved','rejected','verified','cancelled')),
 implementation_evidence TEXT,
 implemented_at TIMESTAMPTZ,
 approved_by UUID,
 approved_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, responsible_user_id) REFERENCES users(organization_id, id),
 FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id)
);

CREATE TABLE effectiveness_checks (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 action_id UUID NOT NULL REFERENCES corrective_actions(id),
 period_start DATE NOT NULL,
 period_end DATE NOT NULL,
 production_quantity INTEGER NOT NULL CHECK (production_quantity >= 0),
 defect_quantity INTEGER NOT NULL CHECK (defect_quantity >= 0),
 acceptance_criteria TEXT NOT NULL,
 result TEXT NOT NULL DEFAULT 'pending'
  CHECK (result IN ('pending','effective','ineffective','insufficient_data')),
 evidence_summary TEXT,
 checked_by UUID,
 checked_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK (period_end >= period_start),
 CHECK (defect_quantity <= production_quantity OR production_quantity = 0),
 FOREIGN KEY (organization_id, checked_by) REFERENCES users(organization_id, id)
);

CREATE TABLE quality_alerts (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID NOT NULL,
 alert_number BIGINT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
 failure_type TEXT NOT NULL CHECK (failure_type IN ('internal','external')),
 title TEXT NOT NULL,
 what_happened TEXT,
 when_happened TEXT,
 where_happened TEXT,
 who_is_affected TEXT,
 how_detected TEXT,
 affected_areas TEXT,
 affected_quantity INTEGER CHECK (affected_quantity IS NULL OR affected_quantity >= 0),
 containment_summary TEXT,
 status TEXT NOT NULL DEFAULT 'draft'
  CHECK (status IN ('draft','issued','superseded','retired')),
 issued_by UUID,
 issued_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (organization_id, alert_number, revision),
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, issued_by) REFERENCES users(organization_id, id)
);

CREATE TABLE lessons_learned (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 source_case_id UUID NOT NULL,
 title TEXT NOT NULL,
 problem_summary TEXT NOT NULL,
 verified_root_cause TEXT NOT NULL,
 actions_summary TEXT NOT NULL,
 effectiveness_summary TEXT,
 before_after_summary TEXT,
 documents_updated TEXT[] NOT NULL DEFAULT '{}',
 training_summary TEXT,
 applicability_tags TEXT[] NOT NULL DEFAULT '{}',
 language_code TEXT NOT NULL DEFAULT 'es' CHECK (language_code IN ('es','en')),
 status TEXT NOT NULL DEFAULT 'draft'
  CHECK (status IN ('draft','in_review','approved','published','retired')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
 created_by UUID,
 approved_by UUID,
 approved_at TIMESTAMPTZ,
 published_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (source_case_id, revision),
 FOREIGN KEY (organization_id, source_case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, created_by) REFERENCES users(organization_id, id),
 FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id)
);

CREATE TABLE lesson_applications (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 lesson_id UUID NOT NULL REFERENCES lessons_learned(id),
 target_case_id UUID NOT NULL,
 application_notes TEXT,
 applied_by UUID,
 applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 outcome TEXT,
 FOREIGN KEY (organization_id, target_case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, applied_by) REFERENCES users(organization_id, id)
);

CREATE TABLE documents (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID,
 alert_id UUID REFERENCES quality_alerts(id),
 lesson_id UUID REFERENCES lessons_learned(id),
 document_type TEXT NOT NULL
  CHECK (document_type IN ('8d_full','8d_progress','quality_alert','lesson_learned','audit_report','excel_export','other')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
 storage_key TEXT NOT NULL,
 file_name TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 file_size_bytes BIGINT CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
 sha256_hex CHAR(64) NOT NULL,
 status TEXT NOT NULL DEFAULT 'issued'
  CHECK (status IN ('draft','issued','superseded','retired')),
 template_version TEXT,
 generated_by UUID,
 generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, generated_by) REFERENCES users(organization_id, id),
 CHECK (num_nonnulls(case_id, alert_id, lesson_id) >= 1)
);

CREATE TABLE attachments (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 case_id UUID,
 cause_id UUID REFERENCES ishikawa_causes(id),
 action_id UUID REFERENCES corrective_actions(id),
 storage_key TEXT NOT NULL,
 file_name TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes >= 0),
 sha256_hex CHAR(64) NOT NULL,
 uploaded_by UUID,
 uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 description TEXT,
 FOREIGN KEY (organization_id, case_id) REFERENCES cases_8d(organization_id, id),
 FOREIGN KEY (organization_id, uploaded_by) REFERENCES users(organization_id, id)
);

CREATE TABLE audit_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 organization_id UUID NOT NULL REFERENCES organizations(id),
 actor_user_id UUID,
 event_type TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id UUID,
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 request_id TEXT,
 ip_address INET,
 user_agent TEXT,
 old_values JSONB,
 new_values JSONB,
 metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
 FOREIGN KEY (organization_id, actor_user_id) REFERENCES users(organization_id, id)
);

CREATE INDEX idx_audit_org_time ON audit_events(organization_id, occurred_at DESC);
CREATE INDEX idx_audit_entity ON audit_events(entity_type, entity_id);
CREATE INDEX idx_causes_case ON ishikawa_causes(case_id);
CREATE INDEX idx_actions_case_status ON corrective_actions(case_id, status);
CREATE INDEX idx_alerts_case ON quality_alerts(case_id);
CREATE INDEX idx_lessons_search ON lessons_learned(organization_id, status);
CREATE INDEX idx_documents_case ON documents(case_id, generated_at DESC);
CREATE INDEX idx_attachments_case ON attachments(case_id, uploaded_at DESC);
```

## Advertencias del DDL

-   `case_disciplines.content JSONB` da flexibilidad inicial, pero las
    reglas y datos críticos deben validarse en backend; no guardar toda
    la aplicación en JSONB.
-   La numeración debe ser transaccional; nunca calcularla con
    `MAX()+1`.
-   Las claves foráneas no sustituyen autorización. Revisar claves
    compuestas en todas las relaciones para impedir vínculos entre
    organizaciones.
-   Considerar tablas de revisiones inmutables para documentos y
    lecciones.
-   Proteger `audit_events` contra modificaciones ordinarias;
    centralizar la escritura de eventos.
-   Revisar la regla `defect_quantity <= production_quantity`: no
    siempre el denominador de defectos es unidades producidas. Ajustar
    según la métrica.
-   Definir políticas de retención, firma electrónica y aprobaciones
    según requisitos reales.
-   Probar migración desde instalación limpia y actualización desde la
    versión anterior.

## Definición de MVP

El MVP debe permitir: crear un caso, completar D0--D8 con bloqueos por
pendientes, registrar contención y emitir alerta PDF versionada, crear
Ishikawa, validar causas con evidencia, administrar acciones, medir
eficacia con criterio configurable, publicar y reutilizar lecciones,
generar PDFs y Excel y consultar la auditoría.

## Checklist para cerrar una fase

-   [ ] Criterios de aceptación cumplidos.
-   [ ] Pruebas ejecutadas y resultados reales documentados.
-   [ ] Migraciones probadas cuando aplique.
-   [ ] Permisos backend verificados cuando aplique.
-   [ ] Errores y riesgos conocidos registrados.
-   [ ] `docs/PROGRESS.md` actualizado.
-   [ ] Sin avances accidentales a fases futuras.

**Siguiente paso:** abrir Claude Code en el repositorio y ejecutar
exclusivamente el prompt de Fase 0. No comenzar por el DDL ni por la
pantalla de 8D hasta validar arquitectura y modelo de datos.
