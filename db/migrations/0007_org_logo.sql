-- Logo de la organización para el encabezado de los documentos PDF.
alter table organizations add column logo_storage_key text;
alter table organizations add column logo_mime text check (logo_mime is null or logo_mime in ('image/png', 'image/jpeg'));
alter table organizations add column logo_sha256 char(64) check (logo_sha256 is null or logo_sha256 ~ '^[0-9a-f]{64}$');
alter table organizations add constraint organizations_logo_complete
    check ((logo_storage_key is null) = (logo_mime is null) and (logo_storage_key is null) = (logo_sha256 is null));
