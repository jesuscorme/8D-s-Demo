-- D4: Ishikawa (6M), biblioteca de ideas de causa, causas del expediente y validación con evidencia.

create table ishikawa_categories (
    id            uuid primary key default gen_random_uuid(),
    code          text not null unique,
    name_es       text not null,
    name_en       text not null,
    display_order smallint not null unique
);

insert into ishikawa_categories (code, name_es, name_en, display_order) values
    ('METHOD', 'Método', 'Method', 1),
    ('MACHINE', 'Máquina', 'Machine', 2),
    ('MATERIAL', 'Material', 'Material', 3),
    ('MANPOWER', 'Mano de obra', 'Manpower', 4),
    ('MEASUREMENT', 'Medición', 'Measurement', 5),
    ('ENVIRONMENT', 'Medio ambiente', 'Mother Nature / Environment', 6);

-- Biblioteca de ideas. organization_id NULL = catálogo base compartido (solo lectura para las organizaciones).
create table cause_ideas (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id),
    category_id     uuid not null references ishikawa_categories(id),
    title_es        text not null check (length(trim(title_es)) > 0),
    title_en        text,
    description_es  text,
    description_en  text,
    process_tags    text[] not null default '{}',
    defect_tags     text[] not null default '{}',
    is_active       boolean not null default true,
    created_by      uuid,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    foreign key (organization_id, created_by) references users(organization_id, id)
);
create index idx_cause_ideas_category on cause_ideas(category_id) where is_active;

-- Causas potenciales del expediente. potential_cause es una copia del texto de la idea:
-- si el catálogo cambia después, la causa del caso no cambia.
create table ishikawa_causes (
    id                   uuid primary key default gen_random_uuid(),
    organization_id      uuid not null references organizations(id),
    case_id              uuid not null,
    category_id          uuid not null references ishikawa_categories(id),
    parent_cause_id      uuid,
    source_idea_id       uuid references cause_ideas(id),
    potential_cause      text not null check (length(trim(potential_cause)) between 1 and 500),
    notes                text,
    -- Estado vigente = decisión de la última validación (lo mantiene el disparador de cause_validations).
    investigation_status text not null default 'pending'
        check (investigation_status in ('pending', 'investigating', 'root_cause', 'not_root_cause', 'needs_more_investigation')),
    added_by             uuid not null,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    unique (organization_id, id),
    foreign key (organization_id, case_id) references cases_8d(organization_id, id) on delete cascade,
    foreign key (organization_id, parent_cause_id) references ishikawa_causes(organization_id, id),
    foreign key (organization_id, added_by) references users(organization_id, id)
);
create index idx_causes_case on ishikawa_causes(case_id);

-- Historial de validación: cada decisión es una fila nueva; nunca se edita ni se borra.
create table cause_validations (
    id                      uuid primary key default gen_random_uuid(),
    organization_id         uuid not null references organizations(id),
    cause_id                uuid not null,
    documented_answer       text not null default 'unknown' check (documented_answer in ('yes', 'no', 'unknown', 'not_applicable')),
    followed_process_answer text not null default 'unknown' check (followed_process_answer in ('yes', 'no', 'unknown', 'not_applicable')),
    verification_method     text,
    evidence_summary        text,
    rationale               text,
    decision                text not null
        check (decision in ('pending', 'investigating', 'root_cause', 'not_root_cause', 'needs_more_investigation')),
    responsible_user_id     uuid,
    due_date                date,
    validated_by            uuid not null,
    validated_at            timestamptz not null default now(),
    -- Una decisión de causa raíz (o descarte) nunca se basa solo en Sí/No:
    -- exige método de verificación, evidencia y justificación.
    check (decision not in ('root_cause', 'not_root_cause') or (
        length(trim(coalesce(verification_method, ''))) > 0
        and length(trim(coalesce(evidence_summary, ''))) > 0
        and length(trim(coalesce(rationale, ''))) > 0)),
    foreign key (organization_id, cause_id) references ishikawa_causes(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_user_id) references users(organization_id, id),
    foreign key (organization_id, validated_by) references users(organization_id, id)
);
create index idx_validations_cause on cause_validations(cause_id, validated_at desc);

create function cause_validations_immutable() returns trigger language plpgsql as $$
begin
    -- Permitido solo el borrado en cascada al eliminar la causa/caso.
    if tg_op = 'DELETE' and not exists (select 1 from ishikawa_causes where id = old.cause_id) then
        return old;
    end if;
    raise exception 'El historial de validación es de solo inserción (% no permitido)', tg_op;
end $$;
create trigger trg_cause_validations_immutable before update or delete on cause_validations
    for each row execute function cause_validations_immutable();

create function cause_validations_apply() returns trigger language plpgsql as $$
begin
    perform set_config('d8.validation_apply', 'on', true);
    update ishikawa_causes set investigation_status = new.decision, updated_at = now() where id = new.cause_id;
    perform set_config('d8.validation_apply', 'off', true);
    return new;
end $$;
create trigger trg_cause_validations_apply after insert on cause_validations
    for each row execute function cause_validations_apply();

-- El estado de investigación solo cambia registrando una validación.
create function ishikawa_causes_status_guard() returns trigger language plpgsql as $$
begin
    if new.investigation_status is distinct from old.investigation_status
       and coalesce(current_setting('d8.validation_apply', true), 'off') <> 'on' then
        raise exception 'El estado de una causa solo cambia registrando una validación';
    end if;
    return new;
end $$;
create trigger trg_ishikawa_causes_status_guard before update on ishikawa_causes
    for each row execute function ishikawa_causes_status_guard();

-- Evidencias de validación de causas.
alter table attachments add column cause_id uuid;
alter table attachments add foreign key (organization_id, cause_id) references ishikawa_causes(organization_id, id) on delete cascade;

-- Catálogo base inicial (hipótesis genéricas; no son conclusiones).
insert into cause_ideas (category_id, title_es, title_en, process_tags, defect_tags)
select c.id, v.title_es, v.title_en, v.process_tags, v.defect_tags
from (values
    ('METHOD', 'Instrucción de trabajo inexistente o desactualizada', 'Work instruction missing or outdated', '{}'::text[], '{}'::text[]),
    ('METHOD', 'Secuencia de operaciones no definida', 'Operation sequence not defined', '{ensamble}', '{faltante,ensamble_incorrecto}'),
    ('METHOD', 'Parámetros de proceso no especificados', 'Process parameters not specified', '{inyeccion,soldadura,maquinado}', '{dimensional,apariencia}'),
    ('METHOD', 'Plan de control sin la característica afectada', 'Control plan missing the affected characteristic', '{}', '{}'),
    ('MACHINE', 'Desgaste de herramental', 'Tooling wear', '{maquinado,estampado}', '{dimensional,rebaba}'),
    ('MACHINE', 'Mantenimiento preventivo vencido', 'Overdue preventive maintenance', '{}', '{}'),
    ('MACHINE', 'Ajuste incorrecto de molde o dispositivo', 'Incorrect mold or fixture setup', '{inyeccion,ensamble}', '{dimensional,rebaba,apariencia}'),
    ('MACHINE', 'Variación de temperatura o presión del equipo', 'Equipment temperature or pressure variation', '{inyeccion,soldadura}', '{apariencia,porosidad}'),
    ('MATERIAL', 'Material fuera de especificación del proveedor', 'Supplier material out of specification', '{}', '{}'),
    ('MATERIAL', 'Mezcla de lotes o números de parte', 'Mixed lots or part numbers', '{almacen,ensamble}', '{mezcla,ensamble_incorrecto}'),
    ('MATERIAL', 'Humedad o contaminación del material', 'Material moisture or contamination', '{inyeccion,pintura}', '{apariencia,porosidad}'),
    ('MATERIAL', 'Daño en empaque o manejo', 'Packaging or handling damage', '{almacen,embarque}', '{golpe,rayadura}'),
    ('MANPOWER', 'Operador sin entrenamiento o certificación vigente', 'Operator without current training or certification', '{}', '{}'),
    ('MANPOWER', 'Rotación o personal de apoyo sin inducción', 'Rotation or support staff without onboarding', '{}', '{}'),
    ('MANPOWER', 'Fatiga o carga de trabajo excesiva', 'Fatigue or excessive workload', '{}', '{}'),
    ('MANPOWER', 'Incumplimiento de un procedimiento existente', 'Non-compliance with an existing procedure', '{}', '{}'),
    ('MEASUREMENT', 'Instrumento sin calibración vigente', 'Gauge calibration expired', '{}', '{dimensional}'),
    ('MEASUREMENT', 'Sistema de medición no adecuado (MSA)', 'Inadequate measurement system (MSA)', '{}', '{dimensional}'),
    ('MEASUREMENT', 'Frecuencia de inspección insuficiente', 'Insufficient inspection frequency', '{}', '{}'),
    ('MEASUREMENT', 'Criterio de aceptación visual ambiguo', 'Ambiguous visual acceptance criteria', '{pintura,inyeccion}', '{apariencia,rayadura}'),
    ('ENVIRONMENT', 'Temperatura o humedad ambiental fuera de rango', 'Ambient temperature or humidity out of range', '{pintura,inyeccion}', '{apariencia,porosidad}'),
    ('ENVIRONMENT', 'Iluminación deficiente en la estación', 'Poor lighting at the station', '{inspeccion,ensamble}', '{apariencia,rayadura}'),
    ('ENVIRONMENT', 'Polvo o contaminación en el área', 'Dust or contamination in the area', '{pintura,ensamble}', '{apariencia,contaminacion}'),
    ('ENVIRONMENT', 'Orden y limpieza (5S) deficientes', 'Poor housekeeping (5S)', '{}', '{mezcla,contaminacion}')
) as v(category_code, title_es, title_en, process_tags, defect_tags)
join ishikawa_categories c on c.code = v.category_code;
