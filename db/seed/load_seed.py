"""Carga los CSV de esta carpeta en una base de 8D PRO que ya tiene las migraciones aplicadas (0001-0010).

Uso:
    pip install "psycopg[binary]"
    python load_seed.py "postgresql://usuario:contraseña@host:5432/base" --password "<contraseña de los usuarios demo>" [--replace]

- Todo ocurre en una transacción: si algo falla, la base queda como estaba.
- Las tablas del seed se vacían antes de cargar (incluidas las categorías e ideas de Ishikawa que crea la
  migración 0004, porque los CSV traen las suyas con otros identificadores). Si la base ya tiene una
  organización, hay que pasar --replace para confirmarlo.
- El seed público no trae hashes de contraseña: --password asigna esa contraseña a todos los usuarios activos.
- Los disparadores de inmutabilidad se desactivan solo durante la carga (requiere ser dueño de las tablas;
  el usuario de la base de Render lo es) y se vuelven a activar al final.
- Los archivos (fotos y PDF) van aparte: copia el contenido de files/ a la carpeta STORAGE_DIR del servidor.
"""
import argparse
import csv
import hashlib
import json
import secrets
from pathlib import Path

import psycopg
from psycopg import sql

HERE = Path(__file__).resolve().parent


def hash_password(password: str) -> str:
    """Mismo formato que app.security.hash_password (scrypt)."""
    n, r, p = 2**14, 8, 1
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Carga el seed de 8D PRO")
    ap.add_argument("database_url")
    ap.add_argument("--password", help="contraseña para los usuarios activos (obligatoria si el seed no trae contraseñas)")
    ap.add_argument("--replace", action="store_true", help="reemplaza los datos si la base ya tiene una organización")
    args = ap.parse_args()
    meta = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    manifest = meta["tables"]
    tables = [m["table"] for m in manifest]
    if not meta.get("passwords_included") and not args.password:
        print("Este seed no trae contraseñas: indica --password para los usuarios demo.")
        return 2
    if args.password and len(args.password) < 10:
        print("La contraseña debe tener al menos 10 caracteres.")
        return 2
    with psycopg.connect(args.database_url) as db:
        missing = [t for t in tables if not db.execute("select to_regclass(%s)", (f"public.{t}",)).fetchone()[0]]
        if missing:
            print(f"Faltan tablas {missing}: aplica primero las migraciones (db/migrations).")
            return 1
        if db.execute("select count(*) from organizations").fetchone()[0] and not args.replace:
            print("La base ya tiene datos. Vuelve a ejecutar con --replace para reemplazarlos.")
            return 1
        for t in tables:
            db.execute(sql.SQL("alter table {} disable trigger user").format(sql.Identifier(t)))
        db.execute(sql.SQL("truncate {} cascade").format(sql.SQL(", ").join(sql.Identifier(t) for t in tables)))
        for m in manifest:
            t, path, selfref = m["table"], HERE / "csv" / m["file"], m["self_ref"]
            with path.open(encoding="utf-8", newline="") as f:
                cols = next(csv.reader(f))
            tmp = sql.Identifier(f"seed_{t}")
            db.execute(sql.SQL("create temp table {} (like {}) on commit drop").format(tmp, sql.Identifier(t)))
            col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
            with db.cursor().copy(sql.SQL("copy {} ({}) from stdin with (format csv, header true, encoding 'UTF8')")
                                  .format(tmp, col_list)) as cp:
                cp.write(path.read_bytes())
            # Las referencias a la misma tabla (revisión que sustituye, subcausa) se ponen después.
            select = sql.SQL(", ").join(sql.SQL("null") if c in selfref else sql.Identifier(c) for c in cols)
            db.execute(sql.SQL("insert into {} ({}) overriding system value select {} from {}")
                       .format(sql.Identifier(t), col_list, select, tmp))
            for c in selfref:
                db.execute(sql.SQL("update {t} x set {c} = s.{c} from {tmp} s where s.id = x.id and s.{c} is not null")
                           .format(t=sql.Identifier(t), c=sql.Identifier(c), tmp=tmp))
            n = db.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(t))).fetchone()[0]
            if n != m["rows"]:
                raise SystemExit(f"{t}: se esperaban {m['rows']} filas y hay {n}")
            print(f"{m['order']:02d} {t:28s} {n}")
        if args.password:
            ids = [r[0] for r in db.execute("select id from users where is_active")]
            for uid in ids:
                db.execute("update users set password_hash = %s where id = %s", (hash_password(args.password), uid))
            print(f"Contraseña asignada a {len(ids)} usuarios activos.")
        db.execute("select setval(pg_get_serial_sequence('audit_events', 'id'), coalesce((select max(id) from audit_events), 1))")
        for t in tables:
            db.execute(sql.SQL("alter table {} enable trigger user").format(sql.Identifier(t)))
    print("Carga completa. Copia el contenido de files/ a STORAGE_DIR del servidor para que se vean fotos y PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
