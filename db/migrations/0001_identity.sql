-- Identidad, organizaciones, plantas, roles, sesiones, numeración y auditoría.
-- Basado en el DDL de referencia de PLAN_MAESTRO_8D_PRO.md con correcciones (ver docs/DATA_MODEL.md).
-- gen_random_uuid() es nativo desde PostgreSQL 13: no requiere pgcrypto.

create table organizations (
    id         uuid primary key default gen_random_uuid(),
    name       text not null check (length(trim(name)) > 0),
    code       text not null unique check (code ~ '^[A-Z0-9_-]{2,20}$'),
    is_active  boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table plants (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    code            text not null check (code ~ '^[A-Z0-9_-]{2,20}$'),
    name            text not null check (length(trim(name)) > 0),
    timezone        text not null default 'America/Mexico_City',
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    unique (organization_id, code),
    unique (organization_id, id)
);

create table users (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    email           text not null check (email = lower(email) and email like '%_@_%'),
    display_name    text not null check (length(trim(display_name)) > 0),
    -- scrypt$n$r$p$salt_hex$hash_hex (ver apps/api/app/security.py). NULL = sin acceso local.
    password_hash   text,
    auth_provider   text,
    auth_subject    text,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    -- El correo es único globalmente: el inicio de sesión no pide organización.
    unique (email),
    unique (auth_provider, auth_subject),
    unique (organization_id, id)
);

-- Roles fijos por organización; los permisos de cada código viven en apps/api/app/permissions.py.
create table roles (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    code            text not null check (code in ('admin', 'quality_manager', 'engineer', 'viewer')),
    name            text not null,
    unique (organization_id, code),
    unique (organization_id, id)
);

-- La PK del DDL de referencia incluía plant_id nullable (no válido en una PK).
-- plant_id NULL = el rol aplica a todas las plantas de la organización.
create table user_roles (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    user_id         uuid not null,
    role_id         uuid not null,
    plant_id        uuid,
    created_at      timestamptz not null default now(),
    unique nulls not distinct (user_id, role_id, plant_id),
    foreign key (organization_id, user_id) references users(organization_id, id),
    foreign key (organization_id, role_id) references roles(organization_id, id),
    foreign key (organization_id, plant_id) references plants(organization_id, id)
);

-- Sesiones de servidor: solo se guarda el SHA-256 del token, nunca el token.
create table sessions (
    token_sha256    char(64) primary key check (token_sha256 ~ '^[0-9a-f]{64}$'),
    organization_id uuid not null,
    user_id         uuid not null,
    created_at      timestamptz not null default now(),
    expires_at      timestamptz not null,
    revoked_at      timestamptz,
    foreign key (organization_id, user_id) references users(organization_id, id)
);
create index idx_sessions_user on sessions(user_id);

-- Numeración transaccional (folios de casos y alertas). Se incrementa con
-- INSERT ... ON CONFLICT DO UPDATE ... RETURNING; nunca con MAX()+1.
create table counters (
    organization_id uuid not null references organizations(id),
    scope           text not null,
    last_value      bigint not null default 0 check (last_value >= 0),
    primary key (organization_id, scope)
);

-- Bitácora: solo inserción. La escritura se centraliza en apps/api/app/audit.py.
create table audit_events (
    id              bigint generated always as identity primary key,
    organization_id uuid not null references organizations(id),
    actor_user_id   uuid,
    event_type      text not null,
    entity_type     text not null,
    entity_id       uuid,
    case_id         uuid,
    occurred_at     timestamptz not null default now(),
    request_id      text,
    ip_address      inet,
    user_agent      text,
    old_values      jsonb,
    new_values      jsonb,
    metadata        jsonb not null default '{}'::jsonb,
    foreign key (organization_id, actor_user_id) references users(organization_id, id)
);
create index idx_audit_org_time on audit_events(organization_id, occurred_at desc);
create index idx_audit_entity on audit_events(entity_type, entity_id);
create index idx_audit_case on audit_events(case_id, occurred_at desc);

create function audit_events_immutable() returns trigger language plpgsql as $$
begin
    raise exception 'audit_events es de solo inserción (% no permitido)', tg_op;
end $$;

create trigger trg_audit_events_immutable
    before update or delete on audit_events
    for each row execute function audit_events_immutable();

create trigger trg_audit_events_no_truncate
    before truncate on audit_events
    for each statement execute function audit_events_immutable();
