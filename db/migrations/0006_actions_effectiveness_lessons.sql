-- Fases 7-10: acciones correctivas/preventivas/sistémicas, actualizaciones del sistema (D7),
-- criterios y verificaciones de eficacia (D6), lecciones aprendidas (D8), documentos ampliados
-- y control de intentos de inicio de sesión.

alter table cases_8d add column target_close_date date;

-- ---- Acciones (D5-D7). La contención (D3) vive en containment_actions. ----
create table corrective_actions (
    id                      uuid primary key default gen_random_uuid(),
    organization_id         uuid not null references organizations(id),
    case_id                 uuid not null,
    cause_id                uuid,
    action_type             text not null check (action_type in ('corrective', 'preventive', 'systemic')),
    description             text not null check (length(trim(description)) between 3 and 2000),
    responsible_user_id     uuid,
    due_date                date,
    status                  text not null default 'open'
        check (status in ('open', 'in_progress', 'pending_approval', 'approved', 'verified', 'ineffective', 'cancelled')),
    implementation_evidence text,
    -- Excepción justificada cuando no existe evidencia documental (p. ej. cambio sin registro físico).
    evidence_exception      text,
    implemented_at          timestamptz,
    submitted_by            uuid,
    approved_by             uuid,
    approved_at             timestamptz,
    review_comment          text,
    cancel_reason           text,
    created_by              uuid not null,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    unique (organization_id, id),
    -- Una acción correctiva siempre ataca una causa del expediente.
    check (action_type <> 'corrective' or cause_id is not null),
    check (status not in ('pending_approval', 'approved', 'verified', 'ineffective')
           or length(trim(coalesce(implementation_evidence, ''))) > 0
           or length(trim(coalesce(evidence_exception, ''))) > 0),
    check (status not in ('approved', 'verified', 'ineffective') or (approved_by is not null and approved_at is not null)),
    check (status <> 'cancelled' or length(trim(coalesce(cancel_reason, ''))) > 0),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, cause_id) references ishikawa_causes(organization_id, id),
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, submitted_by) references users(organization_id, id),
    foreign key (organization_id, approved_by) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id)
);
create index idx_actions_case_status on corrective_actions(case_id, status);

-- ---- D7: actualización de AMEF, plan de control, instrucciones, ayudas visuales, capacitación ----
create table system_updates (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id),
    case_id             uuid not null,
    action_id           uuid,
    update_type         text not null
        check (update_type in ('pfmea', 'dfmea', 'control_plan', 'work_instruction', 'visual_aid', 'training', 'other')),
    document_reference  text not null check (length(trim(document_reference)) between 1 and 200),
    description         text,
    responsible_user_id uuid,
    status              text not null default 'planned' check (status in ('planned', 'completed', 'cancelled')),
    completed_on        date,
    evidence_notes      text,
    created_by          uuid not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (organization_id, id),
    check (status <> 'completed' or (completed_on is not null and length(trim(coalesce(evidence_notes, ''))) > 0)),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, action_id) references corrective_actions(organization_id, id),
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id)
);
create index idx_system_updates_case on system_updates(case_id);

-- ---- D6: criterios de eficacia configurables y aprobados ----
create table effectiveness_criteria (
    id                uuid primary key default gen_random_uuid(),
    organization_id   uuid not null references organizations(id),
    case_id           uuid not null,
    description       text not null check (length(trim(description)) between 3 and 1000),
    metric_name       text not null check (length(trim(metric_name)) > 0),
    -- Unidad del numerador (p. ej. «piezas con rebaba») y tipo de denominador explícito.
    defect_unit       text not null check (length(trim(defect_unit)) > 0),
    denominator_type  text not null check (denominator_type in ('units_produced', 'units_inspected', 'lots_received', 'shipments', 'other')),
    denominator_label text,
    threshold_type    text not null check (threshold_type in ('max_defects', 'max_rate_ppm', 'max_rate_percent')),
    threshold_value   numeric(14, 4) not null check (threshold_value >= 0),
    min_period_days   integer not null check (min_period_days between 1 and 730),
    min_denominator   integer not null default 1 check (min_denominator >= 1),
    status            text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
    approved_by       uuid,
    approved_at       timestamptz,
    created_by        uuid not null,
    created_at        timestamptz not null default now(),
    unique (organization_id, id),
    check (denominator_type <> 'other' or length(trim(coalesce(denominator_label, ''))) > 0),
    check (status = 'draft' or (approved_by is not null and approved_at is not null)),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, approved_by) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id)
);

create function effectiveness_criteria_immutable() returns trigger language plpgsql as $$
begin
    if old.status <> 'draft'
       and (to_jsonb(new) - 'status') <> (to_jsonb(old) - 'status') then
        raise exception 'El criterio de eficacia ya fue aprobado: retíralo y crea uno nuevo';
    end if;
    return new;
end $$;
create trigger trg_effectiveness_criteria_immutable before update on effectiveness_criteria
    for each row execute function effectiveness_criteria_immutable();

create table effectiveness_checks (
    id                      uuid primary key default gen_random_uuid(),
    organization_id         uuid not null references organizations(id),
    case_id                 uuid not null,
    action_id               uuid not null,
    criterion_id            uuid not null,
    period_start            date not null,
    period_end              date not null,
    -- NULL = sin dato. Un dato faltante nunca equivale a cero.
    denominator_quantity    integer check (denominator_quantity is null or denominator_quantity >= 0),
    defect_quantity         integer check (defect_quantity is null or defect_quantity >= 0),
    days_without_production integer not null default 0 check (days_without_production >= 0),
    data_notes              text,
    computed_result         text not null default 'pending'
        check (computed_result in ('pending', 'effective', 'ineffective', 'insufficient_data')),
    result                  text not null default 'pending'
        check (result in ('pending', 'effective', 'ineffective', 'insufficient_data')),
    rationale               text,
    responsible_user_id     uuid,
    decided_by              uuid,
    decided_at              timestamptz,
    created_by              uuid not null,
    created_at              timestamptz not null default now(),
    unique (organization_id, id),
    check (period_end >= period_start),
    check (days_without_production <= period_end - period_start + 1),
    check (result = 'pending' or (decided_by is not null and decided_at is not null
                                   and length(trim(coalesce(rationale, ''))) > 0)),
    check (result not in ('effective', 'ineffective') or (denominator_quantity is not null and defect_quantity is not null)),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, action_id) references corrective_actions(organization_id, id) on delete cascade,
    foreign key (organization_id, criterion_id) references effectiveness_criteria(organization_id, id),
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, decided_by) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id)
);
create index idx_effectiveness_action on effectiveness_checks(action_id, created_at desc);

create function effectiveness_checks_immutable() returns trigger language plpgsql as $$
begin
    if old.result <> 'pending' then
        raise exception 'La verificación de eficacia ya tiene resultado: registra una nueva verificación';
    end if;
    return new;
end $$;
create trigger trg_effectiveness_checks_immutable before update on effectiveness_checks
    for each row execute function effectiveness_checks_immutable();

-- ---- Fase 9: lecciones aprendidas (cada revisión es una fila) ----
create table lessons_learned (
    id                    uuid primary key default gen_random_uuid(),
    organization_id       uuid not null references organizations(id),
    source_case_id        uuid not null,
    lesson_number         bigint not null check (lesson_number > 0),
    revision              integer not null default 1 check (revision > 0),
    title                 text not null check (length(trim(title)) between 3 and 200),
    problem_summary       text not null default '',
    verified_root_cause   text not null default '',
    actions_summary       text not null default '',
    effectiveness_summary text,
    before_summary        text,
    after_summary         text,
    documents_updated     text[] not null default '{}',
    training_summary      text,
    products              text[] not null default '{}',
    processes             text[] not null default '{}',
    plant_codes           text[] not null default '{}',
    situations            text[] not null default '{}',
    language_code         text not null default 'es' check (language_code in ('es', 'en')),
    status                text not null default 'draft'
        check (status in ('draft', 'in_review', 'approved', 'published', 'superseded', 'retired')),
    revision_reason       text,
    created_by            uuid not null,
    submitted_by          uuid,
    submitted_at          timestamptz,
    reviewed_by           uuid,
    reviewed_at           timestamptz,
    review_comment        text,
    published_by          uuid,
    published_at          timestamptz,
    retired_by            uuid,
    retired_at            timestamptz,
    retire_reason         text,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    unique (organization_id, lesson_number, revision),
    unique (organization_id, id),
    check (revision = 1 or length(trim(coalesce(revision_reason, ''))) > 0),
    check (status not in ('approved', 'published', 'superseded') or (reviewed_by is not null and reviewed_at is not null)),
    check (status not in ('published', 'superseded') or (published_by is not null and published_at is not null)),
    check (status <> 'retired' or length(trim(coalesce(retire_reason, ''))) > 0),
    foreign key (organization_id, source_case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, created_by) references users(organization_id, id),
    foreign key (organization_id, submitted_by) references users(organization_id, id),
    foreign key (organization_id, reviewed_by) references users(organization_id, id),
    foreign key (organization_id, published_by) references users(organization_id, id),
    foreign key (organization_id, retired_by) references users(organization_id, id)
);
create index idx_lessons_search on lessons_learned(organization_id, status);
create unique index uq_lesson_one_open on lessons_learned(organization_id, lesson_number) where status in ('draft', 'in_review', 'approved');
create unique index uq_lesson_one_published on lessons_learned(organization_id, lesson_number) where status = 'published';

-- Solo el borrador cambia de contenido; después solo cambian estado y datos del flujo.
create function lessons_learned_immutable() returns trigger language plpgsql as $$
declare
    flow text[] := array['status', 'updated_at', 'submitted_by', 'submitted_at', 'reviewed_by', 'reviewed_at',
                         'review_comment', 'published_by', 'published_at', 'retired_by', 'retired_at', 'retire_reason'];
begin
    if old.status <> 'draft' and (to_jsonb(new) - flow) <> (to_jsonb(old) - flow) then
        raise exception 'La lección % rev % ya no es borrador: crea una nueva revisión', old.lesson_number, old.revision;
    end if;
    return new;
end $$;
create trigger trg_lessons_learned_immutable before update on lessons_learned
    for each row execute function lessons_learned_immutable();

create table lesson_applications (
    id                uuid primary key default gen_random_uuid(),
    organization_id   uuid not null references organizations(id),
    lesson_id         uuid not null,
    target_case_id    uuid not null,
    evaluation        text not null check (length(trim(evaluation)) between 5 and 4000),
    outcome           text not null check (outcome in ('applied', 'partially_applied', 'not_applicable')),
    application_notes text,
    applied_by        uuid not null,
    applied_at        timestamptz not null default now(),
    unique (lesson_id, target_case_id),
    foreign key (organization_id, lesson_id) references lessons_learned(organization_id, id) on delete cascade,
    foreign key (organization_id, target_case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, applied_by) references users(organization_id, id)
);

create function lesson_applications_immutable() returns trigger language plpgsql as $$
begin
    raise exception 'El registro de aplicación de una lección no se modifica';
end $$;
create trigger trg_lesson_applications_immutable before update on lesson_applications
    for each row execute function lesson_applications_immutable();

-- ---- Archivos y documentos ----
alter table attachments add column action_id uuid;
alter table attachments add column effectiveness_check_id uuid;
alter table attachments add column system_update_id uuid;
alter table attachments add foreign key (organization_id, action_id) references corrective_actions(organization_id, id) on delete cascade;
alter table attachments add foreign key (organization_id, effectiveness_check_id) references effectiveness_checks(organization_id, id) on delete cascade;
alter table attachments add foreign key (organization_id, system_update_id) references system_updates(organization_id, id) on delete cascade;

alter table documents alter column case_id drop not null;
alter table documents add column lesson_id uuid;
alter table documents add foreign key (organization_id, lesson_id) references lessons_learned(organization_id, id) on delete cascade;
alter table documents add constraint documents_subject_check
    check (case_id is not null or lesson_id is not null or document_type in ('excel_export', 'audit_report'));
create index idx_documents_lesson on documents(lesson_id);

-- ---- Seguridad: intentos de inicio de sesión (para bloqueo temporal) ----
create table login_attempts (
    id           bigint generated always as identity primary key,
    email        text not null,
    ip_address   inet,
    success      boolean not null,
    attempted_at timestamptz not null default now()
);
create index idx_login_attempts_email on login_attempts(email, attempted_at desc);
