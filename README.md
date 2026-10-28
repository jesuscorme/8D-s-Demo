# 8D PRO

Aplicación web para gestionar casos 8D de D0 a D8: flujo guiado con bloqueos en el servidor, contención con alerta de
calidad PDF, Ishikawa y validación de causas con evidencia, acciones correctivas/preventivas/sistémicas, verificación de
eficacia con criterio configurable, lecciones aprendidas, documentos PDF/Excel versionados con SHA-256, indicadores y bitácora.

Estado: **v1.0 — MVP completo para piloto controlado** ([docs/PROGRESS.md](docs/PROGRESS.md)). Guía de uso: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Requisitos
Windows + PowerShell 5.1, PostgreSQL 16 (servicio nativo), Python 3.12, Node 24.

## Instalación (una vez)
```powershell
copy .env.example .env      # completar POSTGRES_SUPERPASSWORD y DEMO_PASSWORD (ver tabla de variables)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-db.ps1   # rol d8_app (CREATEDB) + BD d8_demo; único paso con superusuario
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\migrate.ps1

cd apps\api
python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m app.seed            # organización, 2 plantas y 6 usuarios demo (@demo.local)
cd ..\web; npm install; npm run build
```

## Ejecución
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-api.ps1 -Port 8010   # terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-web.ps1              # terminal 2 → http://localhost:3010
```
Si usas otros puertos, ajusta `APP_BASE_URL` (destino del QR de las alertas). Desarrollo con recarga: `npm run dev` en `apps/web` (puerto 3000, `API_URL` apunta a la API).

Usuarios demo (`@demo.local`, contraseña = `DEMO_PASSWORD`): `admin` · `calidad` (gerente: aprueba, emite, publica) ·
`ingenieria`, `produccion`, `mantenimiento` (ingenieros) · `consulta` (solo lectura).

## Variables de entorno (`.env`, nunca se sube a Git)
| Variable | Uso |
|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor PostgreSQL |
| `POSTGRES_SUPERUSER`, `POSTGRES_SUPERPASSWORD` | Solo para `setup-db.ps1` |
| `APP_DB_NAME`, `APP_DB_USER`, `APP_DB_PASSWORD`, `DATABASE_URL` | Conexión de la aplicación y de las pruebas |
| `DEMO_PASSWORD` | Contraseña de los usuarios demo del seed (mín. 10) |
| `STORAGE_DIR` | Carpeta privada de archivos (por defecto `storage/`) |
| `APP_BASE_URL` | URL de la interfaz que se codifica en el QR |
| `COOKIE_SECURE` | `true` detrás de HTTPS |
| `API_URL` (proceso web) | URL de la API para el proxy de Next.js |

## Migraciones
SQL numerado en `db/migrations/NNNN_nombre.sql`, aplicado por `scripts/migrate.ps1` en orden y en una transacción por archivo.
La tabla `schema_migrations` guarda el SHA-256 de cada archivo: **una migración aplicada nunca se edita**; los cambios van en
una migración nueva. Para otra base: `scripts\migrate.ps1 -Database <nombre>`.

## Respaldo y restauración
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup.ps1                       # backups\<fecha>\ (BD + storage + SHA256SUMS)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restore.ps1 -From backups\<fecha> # detén la API antes
```
`restore.ps1` verifica el manifiesto, recrea la base (por defecto `d8_demo`; `-Database x` para probar en otra) y extrae
`storage/`. Respalda siempre BD y `storage/` juntos: los documentos de la BD apuntan a esos archivos.

## Pruebas
```powershell
cd apps\api; .venv\Scripts\python -m pytest -q      # unitarias + integración (BD temporal d8_demo_test)
cd apps\web; npm run typecheck; npm run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\e2e.ps1   # Edge + Playwright sobre BD temporal (tras el build)
```
