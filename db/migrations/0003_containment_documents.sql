-- D3: contención, archivos adjuntos (evidencias/fotos), alertas de calidad versionadas y documentos emitidos.

create table containment_actions (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id),
    case_id             uuid not null,
    description         text not null check (length(trim(description)) > 0),
    location            text,
    responsible_user_id uuid,
    due_date            date,
    status              text not null default 'open'
        check (status in ('open', 'in_progress', 'implemented', 'verified', 'cancelled')),
    quantity_checked    integer check (quantity_checked is null or quantity_checked >= 0),
    quantity_rejected   integer check (quantity_rejected is null or quantity_rejected >= 0),
    evidence_notes      text,
    implemented_at      timestamptz,
    verified_at         timestamptz,
    verified_by         uuid,
    created_by          uuid not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (organization_id, id),
    -- Implementar o verificar exige evidencia descrita (los archivos son complementarios).
    check (status not in ('implemented', 'verified') or length(trim(coalesce(evidence_notes, ''))) > 0),
    check (status <> 'verified' or (verified_at is not null and verified_by is not null)),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, verified_by) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id)
);
create index idx_containment_case on containment_actions(case_id, created_at);

-- Archivos subidos (privados; fuera de la carpeta pública del frontend).
create table attachments (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    case_id         uuid not null,
    containment_id  uuid,
    purpose         text not null default 'evidence' check (purpose in ('evidence', 'photo', 'general')),
    storage_key     text not null,
    file_name       text not null check (length(file_name) between 1 and 255),
    mime_type       text not null check (mime_type in ('image/png', 'image/jpeg', 'application/pdf')),
    file_size_bytes bigint not null check (file_size_bytes > 0 and file_size_bytes <= 10485760),
    sha256_hex      char(64) not null check (sha256_hex ~ '^[0-9a-f]{64}$'),
    description     text,
    uploaded_by     uuid not null,
    uploaded_at     timestamptz not null default now(),
    unique (organization_id, id),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, containment_id) references containment_actions(organization_id, id),
    foreign key (organization_id, uploaded_by) references users(organization_id, id)
);
create index idx_attachments_case on attachments(case_id, uploaded_at desc);

create table quality_alerts (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id),
    case_id             uuid not null,
    alert_number        bigint not null check (alert_number > 0),
    revision            integer not null default 1 check (revision > 0),
    failure_type        text not null check (failure_type in ('internal', 'external')),
    title               text not null check (length(trim(title)) > 0),
    what_happened       text,
    when_happened       text,
    where_happened      text,
    who_is_affected     text,
    how_detected        text,
    affected_areas      text,
    affected_quantity   integer check (affected_quantity is null or affected_quantity >= 0),
    containment_summary text,
    responsible_user_id uuid,
    status              text not null default 'draft' check (status in ('draft', 'issued', 'superseded', 'retired')),
    revision_reason     text,
    created_by          uuid not null,
    issued_by           uuid,
    issued_at           timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (organization_id, alert_number, revision),
    unique (organization_id, id),
    check (status = 'draft' or (issued_by is not null and issued_at is not null)),
    check (revision = 1 or length(trim(coalesce(revision_reason, ''))) > 0),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, created_by) references users(organization_id, id),
    foreign key (organization_id, issued_by) references users(organization_id, id)
);
create index idx_alerts_case on quality_alerts(case_id);
-- Como máximo una revisión vigente (emitida) y un borrador por alerta.
create unique index uq_alert_one_issued on quality_alerts(organization_id, alert_number) where status = 'issued';
create unique index uq_alert_one_draft on quality_alerts(organization_id, alert_number) where status = 'draft';

-- Una revisión emitida/sustituida/retirada no cambia de contenido: solo su estado.
create function quality_alerts_issued_immutable() returns trigger language plpgsql as $$
begin
    if old.status <> 'draft'
       and (to_jsonb(new) - 'status' - 'updated_at') <> (to_jsonb(old) - 'status' - 'updated_at') then
        raise exception 'La alerta % rev % ya fue emitida: crea una nueva revisión', old.alert_number, old.revision;
    end if;
    return new;
end $$;
create trigger trg_quality_alerts_immutable before update on quality_alerts
    for each row execute function quality_alerts_issued_immutable();

-- Fotos NOK/OK de cada revisión de la alerta.
create table alert_photos (
    organization_id uuid not null references organizations(id),
    alert_id        uuid not null,
    attachment_id   uuid not null,
    kind            text not null check (kind in ('nok', 'ok')),
    sort_order      smallint not null default 0,
    primary key (alert_id, attachment_id),
    foreign key (organization_id, alert_id) references quality_alerts(organization_id, id) on delete cascade,
    foreign key (organization_id, attachment_id) references attachments(organization_id, id)
);

-- Documentos generados. Una emisión nunca sobrescribe otra: cada fila apunta a un archivo distinto.
create table documents (
    id               uuid primary key default gen_random_uuid(),
    organization_id  uuid not null references organizations(id),
    case_id          uuid not null,
    alert_id         uuid,
    document_type    text not null
        check (document_type in ('8d_full', '8d_progress', 'quality_alert', 'lesson_learned', 'audit_report', 'excel_export', 'other')),
    revision         integer not null default 1 check (revision > 0),
    storage_key      text not null,
    file_name        text not null,
    mime_type        text not null,
    file_size_bytes  bigint not null check (file_size_bytes >= 0),
    sha256_hex       char(64) not null check (sha256_hex ~ '^[0-9a-f]{64}$'),
    status           text not null default 'issued' check (status in ('draft', 'issued', 'superseded', 'retired')),
    template_version text not null,
    generated_by     uuid not null,
    generated_at     timestamptz not null default now(),
    superseded_by    uuid references documents(id),
    metadata         jsonb not null default '{}'::jsonb,
    unique (organization_id, id),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, alert_id) references quality_alerts(organization_id, id),
    foreign key (organization_id, generated_by) references users(organization_id, id)
);
create index idx_documents_case on documents(case_id, generated_at desc);

create function documents_immutable() returns trigger language plpgsql as $$
begin
    if (to_jsonb(new) - 'status' - 'superseded_by') <> (to_jsonb(old) - 'status' - 'superseded_by') then
        raise exception 'Los documentos emitidos son inmutables (%)', old.id;
    end if;
    return new;
end $$;
create trigger trg_documents_immutable before update on documents
    for each row execute function documents_immutable();
