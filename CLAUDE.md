# 8D PRO — instrucciones para Claude Code

## Al empezar cada sesión
1. Lee `docs/PROGRESS.md` (estado, bloqueos, cómo retomar).
2. Lee de `PLAN_MAESTRO_8D_PRO.md` solo la fase que se va a trabajar.
3. Inspecciona el código antes de editar; conserva decisiones de `docs/DECISIONS.md`.

## Stack y entorno (Windows, PowerShell 5.1)
- `apps/api`: Python 3.12 + FastAPI + psycopg 3. Reglas puras en `app/workflow.py` y `app/causes_rules.py`.
- `apps/web`: Next.js 15 + TypeScript; proxy `/api/*` → API.
- PostgreSQL 16 nativo, BD `d8_demo`, rol `d8_app`. `psql`: `C:\Program Files\PostgreSQL\16\bin\psql.exe`.
- Credenciales solo en `.env` (no se sube). Scripts: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\<x>.ps1`.

## Comandos
| Comando | Qué hace |
|---|---|
| `scripts/setup-db.ps1` | Crea rol (CREATEDB) y BD (idempotente; usa superusuario) |
| `scripts/migrate.ps1 [-Database x]` | Aplica migraciones verificando SHA-256 |
| `.venv\Scripts\python -m app.seed` (apps/api) | Organización, plantas y usuarios demo |
| `scripts/start-api.ps1 -Port 8010` | API (3000/8000 los usa la demo SPC en este equipo) |
| `scripts/start-web.ps1` | Interfaz compilada en :3010 → API :8010 |
| `scripts/backup.ps1` / `restore.ps1 -From backups\<fecha>` | Respaldo BD + storage con SHA-256 / restauración |
| `.venv\Scripts\python -m pytest -q` (apps/api) | Pruebas (integración en BD temporal `d8_demo_test`) |
| `npm run dev` / `typecheck` / `build` (apps/web) | Interfaz |
| `scripts/e2e.ps1` | E2E en Edge (Playwright) sobre BD y storage temporales; requiere build |

## Reglas no negociables
- Permisos y reglas del flujo se aplican en el backend; la UI solo los refleja.
- Toda consulta filtra por `organization_id`; relaciones con claves compuestas.
- Nunca confirmar causa raíz solo con Sí/No (API + CHECK en BD).
- Documentos y revisiones emitidas son inmutables; una emisión nueva crea una revisión.
- No editar migraciones aplicadas: crear una nueva.
- No simular módulos futuros: se muestran como «no disponibles».
- No afirmar que una prueba pasó sin haberla ejecutado. Actualizar `docs/PROGRESS.md` al cerrar.
