-- Expedientes 8D, equipo, disciplinas D0-D8 y comentarios.

create table cases_8d (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id),
    plant_id            uuid not null,
    case_number         bigint not null check (case_number > 0),
    -- Folio legible: 8D-<PLANTA>-<AÑO>-<NNNN>; se asigna en la misma transacción que case_number.
    folio               text not null,
    title               text not null check (length(trim(title)) > 0),
    -- Vacío permitido en borrador; D2 exige su contenido para enviarse a revisión.
    problem_description text not null default '',
    status              text not null default 'draft'
        check (status in ('draft', 'open', 'in_progress', 'pending_review', 'approved', 'closed', 'cancelled')),
    severity            text not null default 'medium' check (severity in ('low', 'medium', 'high', 'critical')),
    source_type         text check (source_type in ('customer_complaint', 'internal', 'supplier', 'audit', 'other')),
    customer_name       text,
    product_name        text,
    part_number         text,
    process_name        text,
    lot_number          text,
    defect_date         date,
    detected_quantity   integer check (detected_quantity is null or detected_quantity >= 0),
    affected_quantity   integer check (affected_quantity is null or affected_quantity >= 0),
    opened_by           uuid not null,
    owner_user_id       uuid,
    cancel_reason       text,
    is_demo             boolean not null default false,
    -- Control de concurrencia optimista: cada actualización incrementa version.
    version             integer not null default 1 check (version > 0),
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    closed_at           timestamptz,
    unique (organization_id, plant_id, case_number),
    unique (organization_id, folio),
    unique (organization_id, id),
    check (status <> 'cancelled' or length(trim(coalesce(cancel_reason, ''))) > 0),
    foreign key (organization_id, plant_id) references plants(organization_id, id),
    foreign key (organization_id, opened_by) references users(organization_id, id),
    foreign key (organization_id, owner_user_id) references users(organization_id, id)
);
create index idx_cases_org_status on cases_8d(organization_id, status);
create index idx_cases_plant_updated on cases_8d(plant_id, updated_at desc);

create table case_team (
    organization_id uuid not null references organizations(id),
    case_id         uuid not null,
    user_id         uuid not null,
    team_role       text not null default 'member' check (team_role in ('leader', 'champion', 'member')),
    added_at        timestamptz not null default now(),
    primary key (case_id, user_id),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, user_id) references users(organization_id, id)
);
-- Un único líder por caso.
create unique index uq_case_team_leader on case_team(case_id) where team_role = 'leader';

create table case_disciplines (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    case_id         uuid not null,
    discipline_code text not null check (discipline_code in ('D0','D1','D2','D3','D4','D5','D6','D7','D8')),
    status          text not null default 'not_started'
        check (status in ('not_started', 'in_progress', 'pending_review', 'approved', 'blocked')),
    -- Campos narrativos de la disciplina; las reglas se validan en el backend (app/workflow.py).
    content         jsonb not null default '{}'::jsonb check (jsonb_typeof(content) = 'object'),
    owner_user_id   uuid,
    submitted_by    uuid,
    submitted_at    timestamptz,
    approved_by     uuid,
    approved_at     timestamptz,
    review_comment  text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (case_id, discipline_code),
    unique (organization_id, id),
    check (status <> 'approved' or (approved_by is not null and approved_at is not null)),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, owner_user_id) references users(organization_id, id),
    foreign key (organization_id, submitted_by) references users(organization_id, id),
    foreign key (organization_id, approved_by) references users(organization_id, id)
);

create table case_comments (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    case_id         uuid not null,
    discipline_code text check (discipline_code in ('D0','D1','D2','D3','D4','D5','D6','D7','D8')),
    body            text not null check (length(trim(body)) between 1 and 4000),
    author_user_id  uuid not null,
    created_at      timestamptz not null default now(),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, author_user_id) references users(organization_id, id)
);
create index idx_comments_case on case_comments(case_id, created_at);
