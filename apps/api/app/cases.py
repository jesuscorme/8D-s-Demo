"""Acceso a expedientes con aislamiento por organización/planta y carga de la instantánea del flujo."""
from uuid import UUID

import psycopg

from app import workflow
from app.auth import Principal
from app.errors import ApiError, not_found


def load_case(conn: psycopg.Connection, who: Principal, case_id: UUID, for_update: bool = False) -> dict:
    row = conn.execute(
        "select * from cases_8d where id = %s and organization_id = %s" + (" for update" if for_update else ""),
        (case_id, who.organization_id)).fetchone()
    if not row or not who.sees_plant(row["plant_id"]):
        raise not_found("Caso")
    return row


def snapshot(conn: psycopg.Connection, case: dict) -> workflow.Snapshot:
    cid = case["id"]
    disciplines = conn.execute("select discipline_code, status, content from case_disciplines where case_id = %s",
                               (cid,)).fetchall()
    return workflow.Snapshot(
        case=case,
        team=conn.execute("select user_id, team_role from case_team where case_id = %s", (cid,)).fetchall(),
        content={d["discipline_code"]: d["content"] for d in disciplines},
        status={d["discipline_code"]: d["status"] for d in disciplines},
        containment=conn.execute("select status, evidence_notes from containment_actions where case_id = %s",
                                 (cid,)).fetchall(),
        causes=conn.execute("select id, investigation_status from ishikawa_causes where case_id = %s", (cid,)).fetchall(),
        issued_alerts=conn.execute("select count(*) as n from quality_alerts where case_id = %s and status = 'issued'",
                                   (cid,)).fetchone()["n"],
        actions=conn.execute("""select id, action_type, status, cause_id, responsible_user_id, due_date
                                from corrective_actions where case_id = %s""", (cid,)).fetchall(),
        latest_checks={r["action_id"]: r["result"] for r in conn.execute(
            """select distinct on (action_id) action_id, result from effectiveness_checks
               where case_id = %s and result <> 'pending' order by action_id, decided_at desc""", (cid,)).fetchall()},
        approved_criteria=conn.execute("""select count(*) as n from effectiveness_criteria
                                          where case_id = %s and status = 'approved'""", (cid,)).fetchone()["n"],
        system_updates=conn.execute("select status from system_updates where case_id = %s", (cid,)).fetchall(),
        lessons=[r["status"] for r in conn.execute("select status from lessons_learned where source_case_id = %s",
                                                    (cid,)).fetchall()],
    )


def rule(fn, *args) -> None:
    """Traduce RuleError del módulo puro a una respuesta HTTP 409."""
    try:
        fn(*args)
    except workflow.RuleError as exc:
        raise ApiError(409, exc.code, exc.message, exc.details) from None


def ensure_section_editable(conn: psycopg.Connection, case: dict, code: str, label: str) -> None:
    s = snapshot(conn, case)
    rule(workflow.check_case_open, s)
    if workflow.section_locked(code, s):
        raise ApiError(409, "discipline_locked", f"{label} está congelado porque {code} fue enviada o aprobada. "
                       f"Reabre {code} para modificarlo.")


def refresh_case_status(conn: psycopg.Connection, case_id: UUID) -> str:
    case = conn.execute("select * from cases_8d where id = %s", (case_id,)).fetchone()
    status = workflow.case_status_after(snapshot(conn, case))
    if status != case["status"]:
        conn.execute("""update cases_8d set status = %s, updated_at = now(), version = version + 1,
                        closed_at = case when %s = 'closed' then now() else null end where id = %s""",
                     (status, status, case_id))
    return status


def touch(conn: psycopg.Connection, case_id: UUID) -> None:
    conn.execute("update cases_8d set updated_at = now() where id = %s", (case_id,))


def same_org_user(conn: psycopg.Connection, who: Principal, user_id: UUID | None) -> None:
    if user_id is None:
        return
    ok = conn.execute("select 1 from users where id = %s and organization_id = %s and is_active",
                      (user_id, who.organization_id)).fetchone()
    if not ok:
        raise ApiError(422, "invalid_user", "El usuario no existe o no pertenece a tu organización.")
