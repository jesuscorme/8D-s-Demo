-- Corrección de 0008: permitir el borrado en cascada (caso, lección o adjunto ya eliminados).
create or replace function lesson_photos_draft_only() returns trigger language plpgsql as $$
declare
    lesson uuid := coalesce(new.lesson_id, old.lesson_id);
begin
    if tg_op = 'DELETE' and (not exists (select 1 from attachments where id = old.attachment_id)
                             or not exists (select 1 from lessons_learned where id = old.lesson_id)) then
        return old;
    end if;
    if exists (select 1 from lessons_learned where id = lesson and status <> 'draft') then
        raise exception 'Las fotos de una lección solo se modifican en borrador';
    end if;
    return coalesce(new, old);
end $$;
