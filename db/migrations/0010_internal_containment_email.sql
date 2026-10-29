-- 8D internos/externos, datos del concentrado, incidencias en el Ishikawa,
-- registro de contención (inicio/fin, lotes, resultado) y notificaciones por correo.

-- ---- Caso: tipo interno/externo y campos del concentrado ----
alter table cases_8d add column case_type text;
update cases_8d set case_type = case when source_type = 'customer_complaint' then 'external' else 'internal' end;
alter table cases_8d alter column case_type set not null;
alter table cases_8d alter column case_type set default 'internal';
alter table cases_8d add constraint cases_8d_case_type_check check (case_type in ('internal', 'external'));
alter table cases_8d add column market_segment text check (market_segment in ('OEM', 'OES', 'AM'));
alter table cases_8d add column main_defect text check (main_defect is null or length(main_defect) <= 200);
alter table cases_8d add column report_date date;
update cases_8d set report_date = created_at::date;
alter table cases_8d alter column report_date set not null;
alter table cases_8d alter column report_date set default current_date;

-- ---- Ishikawa: incidencias observadas de cada causa potencial ----
alter table ishikawa_causes add column incidence_count integer check (incidence_count is null or incidence_count between 0 and 1000000);

-- ---- D3: registro de contención ----
create table case_containment (
    case_id         uuid primary key,
    organization_id uuid not null references organizations(id),
    started_at      timestamptz not null,
    started_by      uuid not null,
    ended_at        timestamptz,
    ended_by        uuid,
    result          text check (result in ('effective', 'not_effective')),
    result_notes    text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    check (ended_at is null or ended_at >= started_at),
    check ((ended_at is null) = (result is null)),
    check (result is null or length(trim(coalesce(result_notes, ''))) > 0),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, started_by) references users(organization_id, id),
    foreign key (organization_id, ended_by) references users(organization_id, id)
);

create table containment_lots (
    id                 uuid primary key default gen_random_uuid(),
    organization_id    uuid not null references organizations(id),
    case_id            uuid not null,
    lot_number         text not null check (length(trim(lot_number)) between 1 and 100),
    location           text check (location is null or length(location) <= 200),
    quantity_inspected integer not null check (quantity_inspected >= 0),
    quantity_rejected  integer not null default 0 check (quantity_rejected >= 0),
    disposition        text check (disposition in ('released', 'rework', 'scrap', 'returned', 'on_hold')),
    notes              text,
    created_by         uuid not null,
    created_at         timestamptz not null default now(),
    unique (case_id, lot_number),
    check (quantity_rejected <= quantity_inspected),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, created_by) references users(organization_id, id)
);

-- ---- Notificaciones por correo ----
create table notification_recipients (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    plant_id        uuid,
    event           text not null check (event in ('containment_started', 'alert_issued')),
    email           text not null check (email = lower(email) and email like '%_@_%.__%'),
    name            text,
    created_at      timestamptz not null default now(),
    unique nulls not distinct (organization_id, plant_id, event, email),
    foreign key (organization_id, plant_id) references plants(organization_id, id) on delete cascade
);

-- Bandeja de salida: cada correo queda registrado (enviado o con su error); el envío ocurre tras el commit.
create table email_outbox (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    case_id         uuid,
    event           text not null,
    to_addresses    text[] not null check (cardinality(to_addresses) between 1 and 100),
    subject         text not null,
    body_text       text not null,
    body_html       text,
    attachments     jsonb not null default '[]'::jsonb,
    status          text not null default 'queued' check (status in ('queued', 'sent', 'failed')),
    attempts        integer not null default 0,
    last_error      text,
    transport       text,
    created_by      uuid,
    created_at      timestamptz not null default now(),
    sent_at         timestamptz,
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete set null (case_id)
);
create index idx_outbox_status on email_outbox(status, created_at);
create index idx_outbox_case on email_outbox(case_id, created_at desc);
