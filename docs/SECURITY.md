# Seguridad

## Implementado y probado
| Control | Detalle | Prueba |
|---|---|---|
| Autenticación | Correo + contraseña (scrypt con sal); error único; hash ficticio si el usuario no existe | `test_login_me_logout` |
| Bloqueo temporal | 5 intentos fallidos en 15 min por correo → 429; se registra `auth.login_failed` y `auth.locked` (conexión propia: no se pierden con el rollback) | `test_login_lockout_and_security_events` |
| Contraseñas | Cambio propio con contraseña actual; restablecimiento por admin; ambos revocan sesiones y quedan en bitácora | `test_change_own_password…`, `test_admin_reset_password…` |
| Concurrencia | Transiciones serializadas con `select … for update` del caso; folios con contador transaccional | `test_parallel_case_creation…`, `test_double_submit…` |
| Sesión | Token de 256 bits en cookie httpOnly/SameSite=Lax (`Secure` con `COOKIE_SECURE=true`), 12 h; en BD solo SHA-256; logout y desactivación revocan | `test_login_me_logout`, `test_admin_creates_user…` |
| CSRF | SameSite=Lax + cabecera `x-d8-client: web` obligatoria en métodos que modifican | `test_csrf_header_required_for_mutations` |
| Autorización | Permiso por endpoint en backend (`app/permissions.py`); los denegados se registran como `security.forbidden` | `test_role_permissions…`, `test_complete_8d_cycle` (403 en aprobar, publicar, emitir, exportar) |
| Segregación | Quien envía una acción no la aprueba; el autor/remitente de una lección no la revisa | `test_complete_8d_cycle` |
| Aislamiento | Filtro por organización y plantas en cada consulta; recurso ajeno = 404; claves foráneas compuestas | `test_organization_isolation`, `test_actions_respect_organization_isolation` |
| Archivos | Tipo por firma real (PNG/JPEG/PDF), 10 MB, nombre saneado, carpeta privada, sin sobrescritura, descarga con permisos, `nosniff`, `no-store` | `test_uploads_are_validated_and_private` |
| Descargas | Documentos de caso: permiso sobre el caso; exportaciones de organización: solo su autor o auditor con todas las plantas; lecciones no publicadas: solo editores | `test_complete_8d_cycle` |
| Excel | Celdas que empiezan con `= + - @` se escapan (inyección de fórmulas) | `test_excel_escapes_formulas…` |
| Integridad | SHA-256 de adjuntos y documentos; `GET /documents/{id}/verify` y `/attachments/{id}/verify` recalculan | `test_complete_8d_cycle` (detecta archivo alterado) |
| Bitácora | `audit_events` sin UPDATE/DELETE/TRUNCATE (disparador); usuario, fecha, evento, entidad, antes/después, `request_id`, `txid`, IP | `test_audit_trail_is_append_only` |
| Inmutabilidad | Alertas emitidas, documentos, criterios aprobados, verificaciones decididas, lecciones no borrador, aplicaciones de lección | pruebas con `sql("update …")` → excepción |
| Secretos | Solo en `.env` (ignorado); la contraseña demo sale de `DEMO_PASSWORD` | — |

## Firma electrónica
El SHA-256 **no** es una firma electrónica legal: prueba que el archivo no cambió, no quién lo aprobó con valor legal.
Para firma avanzada/cualificada faltaría: identidad verificada del firmante (SSO corporativo o certificado), firma
criptográfica del documento (PAdES con certificado), sellado de tiempo de una autoridad, política de firma y validación
por el área legal del cliente. Hoy las aprobaciones son registros de auditoría (usuario autenticado + fecha).

## Requiere infraestructura (no verificable en local)
| Medida | Configuración | Cómo verificar |
|---|---|---|
| HTTPS | Proxy inverso (IIS/nginx) con TLS delante de la web; `COOKIE_SECURE=true` | La cookie aparece con `Secure`; HTTP redirige a HTTPS |
| Cabeceras | `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options` en el proxy inverso | Inspeccionar cabeceras de respuesta |
| API no expuesta | La API escucha en `127.0.0.1`; solo la web debe ser pública | Puerto 8010 inaccesible desde otra máquina |
| Respaldo | `scripts/backup.ps1` programado y copiado fuera del equipo | `restore.ps1 -Database d8_restore_check` periódico |
| Antivirus de archivos | Escaneo de `storage/` si el cliente lo exige | — |

## Riesgos conocidos
- Archivo huérfano en `storage/` si la transacción falla después de guardarlo (no afecta integridad; limpieza pendiente).
- Sin recuperación de contraseña por correo: el usuario la cambia (cierra sus otras sesiones) o el administrador la restablece (cierra todas).
- El bloqueo de login es por correo; un atacante puede bloquear temporalmente una cuenta conocida (riesgo aceptado para el piloto).
