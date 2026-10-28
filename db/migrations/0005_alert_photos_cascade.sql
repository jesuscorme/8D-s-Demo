-- Corrección: al eliminar un caso (cascada) las fotos de alerta bloqueaban el borrado de sus adjuntos.
alter table alert_photos drop constraint alert_photos_organization_id_attachment_id_fkey;
alter table alert_photos add constraint alert_photos_organization_id_attachment_id_fkey
    foreign key (organization_id, attachment_id) references attachments(organization_id, id) on delete cascade;
