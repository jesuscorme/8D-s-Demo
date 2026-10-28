-- Antes y después visual de la lección aprendida (fotos tomadas de adjuntos del caso de origen).
create table lesson_photos (
    organization_id uuid not null references organizations(id),
    lesson_id       uuid not null,
    attachment_id   uuid not null,
    kind            text not null check (kind in ('before', 'after')),
    caption         text check (caption is null or length(caption) <= 300),
    sort_order      smallint not null default 0,
    primary key (lesson_id, attachment_id),
    foreign key (organization_id, lesson_id) references lessons_learned(organization_id, id) on delete cascade,
    foreign key (organization_id, attachment_id) references attachments(organization_id, id) on delete cascade
);

-- Las fotos solo cambian mientras la revisión es borrador (igual que el resto del contenido).
create function lesson_photos_draft_only() returns trigger language plpgsql as $$
declare
    lesson uuid := coalesce(new.lesson_id, old.lesson_id);
begin
    if exists (select 1 from lessons_learned where id = lesson and status <> 'draft') then
        raise exception 'Las fotos de una lección solo se modifican en borrador';
    end if;
    return coalesce(new, old);
end $$;
create trigger trg_lesson_photos_draft_only before insert or update or delete on lesson_photos
    for each row execute function lesson_photos_draft_only();
