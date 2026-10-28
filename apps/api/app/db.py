"""Configuración y conexiones a PostgreSQL (psycopg 3 con pool)."""
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import set_json_dumps
from psycopg_pool import ConnectionPool

REPO_ROOT = Path(__file__).resolve().parents[3]


def read_dotenv() -> dict[str, str]:
    """Lee el .env de la raíz del repositorio (no se sube a Git)."""
    values: dict[str, str] = {}
    path = REPO_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def setting(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or read_dotenv().get(name) or default


def database_url() -> str:
    url = setting("DATABASE_URL")
    if not url:
        raise RuntimeError("Falta DATABASE_URL (variable de entorno o .env).")
    return url


def _json_default(value):
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    raise TypeError(f"No serializable: {type(value).__name__}")


set_json_dumps(lambda obj: json.dumps(obj, default=_json_default, ensure_ascii=False))


class Database:
    def __init__(self, url: str):
        self.pool = ConnectionPool(url, min_size=1, max_size=8, open=False, kwargs={"row_factory": dict_row})

    def open(self) -> None:
        self.pool.open(wait=True, timeout=10)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection]:
        """Una transacción por petición: commit al salir, rollback si hay excepción."""
        with self.pool.connection() as conn:
            yield conn
