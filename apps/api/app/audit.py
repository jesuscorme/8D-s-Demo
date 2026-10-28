"""Escritura centralizada de la bitácora (audit_events es de solo inserción)."""
import ipaddress
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.auth import Principal


def _ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",")[0].strip()
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return None


def security_event(db, organization_id: UUID, actor_user_id: UUID | None, event_type: str, ip: str | None,
                   user_agent: str | None, metadata: dict, request_id: str | None = None) -> None:
    """Evento de seguridad en una conexión propia: se conserva aunque la petición termine en error (rollback)."""
    with db.pool.connection() as conn:
        conn.execute(
            """insert into audit_events (organization_id, actor_user_id, event_type, entity_type, request_id,
                                         ip_address, user_agent, metadata)
               values (%s, %s, %s, 'security', %s, %s, %s, %s)""",
            (organization_id, actor_user_id, event_type, request_id, _ip(ip), (user_agent or "")[:300], Jsonb(metadata)))


def diff(old: dict, new: dict) -> tuple[dict, dict]:
    """Solo los campos que cambiaron, para no inflar la bitácora."""
    keys = [k for k in new if old.get(k) != new.get(k)]
    return {k: old.get(k) for k in keys}, {k: new.get(k) for k in keys}


def record(conn: psycopg.Connection, who: Principal, event_type: str, entity_type: str, entity_id: UUID | None,
           case_id: UUID | None = None, old: dict | None = None, new: dict | None = None,
           metadata: dict | None = None) -> None:
    conn.execute(
        """insert into audit_events (organization_id, actor_user_id, event_type, entity_type, entity_id, case_id,
                                     request_id, ip_address, user_agent, old_values, new_values, metadata)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s || jsonb_build_object('txid', pg_current_xact_id()::text))""",
        (who.organization_id, who.user_id, event_type, entity_type, entity_id, case_id, who.request_id,
         _ip(who.ip), who.user_agent, Jsonb(old) if old is not None else None,
         Jsonb(new) if new is not None else None, Jsonb(metadata or {})))
