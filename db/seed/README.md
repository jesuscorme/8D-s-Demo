# Seed de demostración

Copia de la base de demostración local (29-oct-2026) para cargarla en otra instalación, por ejemplo producción.

| Carpeta / archivo | Contenido |
|---|---|
| `csv/` | Una tabla por archivo, numeradas en el orden de carga (01–30). UTF-8 con encabezado. |
| `files/` | Fotos, PDF y logo referenciados por `attachments`, `documents` y `organizations` (118 archivos). |
| `manifest.json` | Orden, filas esperadas por tabla y tablas excluidas. |
| `load_seed.py` | Cargador: una sola transacción y verificación del número de filas de cada tabla. |

Datos: 1 organización, 2 plantas, 8 usuarios (6 activos), 27 casos 8D, 40 revisiones de alerta, 20 lecciones y la bitácora.

No incluye: sesiones, intentos de inicio de sesión, bandeja de correos, `schema_migrations`, hashes de contraseña ni
correos reales (el destinatario de avisos es `avisos@demo.local`). La bitácora excluye los eventos de casos y
entidades eliminados y los de usuarios retirados.

## Carga

1. Aplica las migraciones `db/migrations/0001–0010` a la base de destino.
2. Carga los datos (la contraseña se asigna a los 6 usuarios activos, `*@demo.local`):

   ```
   pip install "psycopg[binary]"
   python db/seed/load_seed.py "<DATABASE_URL>" --password "<contraseña>"            # base vacía
   python db/seed/load_seed.py "<DATABASE_URL>" --password "<contraseña>" --replace  # reemplaza datos existentes
   ```

3. Copia el contenido de `files/` a la carpeta `STORAGE_DIR` del servicio de la API. En Render debe ser un disco
   persistente; sin disco, los archivos se pierden en cada despliegue.
4. Reinicia la API y entra con `calidad@demo.local` y la contraseña elegida.

Las tablas con disparadores de inmutabilidad se cargan con los disparadores desactivados (requiere ser dueño de las
tablas) y se reactivan al final. Si la base ya tiene una organización, el cargador se detiene salvo con `--replace`.
