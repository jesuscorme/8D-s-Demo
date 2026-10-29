"""Reglas puras del flujo D0-D8."""
import pytest

from app import workflow
from app.workflow import RuleError, Snapshot

OWNER, U2, U3 = "u-owner", "u-2", "u-3"


def full_case(**overrides) -> dict:
    case = {"title": "Rebaba en carcasa", "source_type": "customer_complaint", "severity": "high",
            "owner_user_id": OWNER, "problem_description": "Rebaba de 0.5 mm en el borde de la carcasa 123",
            "part_number": "123-A", "defect_date": "2026-10-01", "detected_quantity": 40, "customer_name": "Cliente A",
            "status": "open"}
    return {**case, **overrides}


def snap(status=None, **kw) -> Snapshot:
    base = dict(
        case=full_case(),
        team=[{"user_id": OWNER, "team_role": "leader"}, {"user_id": U2, "team_role": "member"},
              {"user_id": U3, "team_role": "member"}],
        content={"D0": {"emergency_response": "Bloqueo de inventario", "justification": "Reclamo de cliente"},
                 "D2": {"what": "Rebaba", "where": "Cliente", "when": "Recepción", "how_detected": "Inspección visual"},
                 "D4": {"occurrence_cause": "Desgaste", "escape_point": "Inspección final sin criterio"}},
        status=status or {},
        containment=[{"status": "verified", "evidence_notes": "Inventario 100% revisado"}],
        causes=[{"id": "c-root", "investigation_status": "root_cause"}, {"id": "c-no", "investigation_status": "not_root_cause"}],
        issued_alerts=1,
    )
    base.update(kw)
    return Snapshot(**base)


def item(s: Snapshot, code: str) -> dict:
    return next(d for d in workflow.evaluate(s) if d["code"] == code)


def test_d0_requirements_listed_and_submittable():
    s = snap()
    d0 = item(s, "D0")
    assert d0["pending_count"] == 0 and d0["can_submit"]
    workflow.check_submit("D0", s)


def test_d0_missing_emergency_response_blocks_submit():
    s = snap(content={"D0": {"justification": "x"}})
    with pytest.raises(RuleError) as exc:
        workflow.check_submit("D0", s)
    assert exc.value.code == "requirements_pending"
    assert any("emergencia" in b for b in exc.value.details)


def test_sequential_order_requires_previous_approved():
    s = snap(status={"D0": "pending_review"})
    with pytest.raises(RuleError) as exc:
        workflow.check_submit("D1", s)
    assert "Requiere D0 aprobada" in exc.value.details


def test_d1_requires_three_members_leader_and_owner():
    s = snap(status={"D0": "approved"}, team=[{"user_id": U2, "team_role": "member"}])
    labels = {r["key"]: r["met"] for r in item(s, "D1")["requirements"]}
    assert labels == {"owner": True, "leader": False, "team_size": False, "owner_in_team": False}


def test_d2_customer_required_only_for_external_8d():
    internal = snap(case=full_case(case_type="internal", customer_name=None))
    assert "customer_name" not in {r["key"] for r in item(internal, "D2")["requirements"]}
    complaint = snap(case=full_case(case_type="external", customer_name=" "))
    assert not next(r for r in item(complaint, "D2")["requirements"] if r["key"] == "customer_name")["met"]


def test_d3_needs_verified_actions_and_issued_alert():
    s = snap(containment=[{"status": "implemented", "evidence_notes": "x"}], issued_alerts=0)
    met = {r["key"]: r["met"] for r in item(s, "D3")["requirements"]}
    assert met == {"started": False, "lots": False, "ended": False, "has_actions": True, "all_verified": False,
                   "alert_issued": False}
    s = snap(containment_record={"started_at": "t", "ended_at": "t2", "result": "effective"}, containment_lots=2)
    assert all(r["met"] for r in item(s, "D3")["requirements"])
    open_record = snap(containment_record={"started_at": "t", "ended_at": None, "result": None}, containment_lots=1)
    assert not {r["key"]: r["met"] for r in item(open_record, "D3")["requirements"]}["ended"]


def test_milestones_from_report_date():
    from datetime import date
    ms = {m["key"]: m for m in workflow.milestones(date(2026, 10, 1), {"D3": date(2026, 10, 2), "D4": date(2026, 10, 5)},
                                                   date(2026, 10, 20))}
    assert ms["containment"]["status"] == "on_time" and str(ms["containment"]["due"]) == "2026-10-02"
    assert ms["root_cause"]["status"] == "late"          # meta 3-oct, cumplido 5-oct
    assert ms["actions"]["status"] == "overdue"          # meta 8-oct, sin cumplir al 20-oct
    assert workflow.milestones(date(2026, 10, 18), {}, date(2026, 10, 20))[3]["status"] == "pending"
    cancelled_only = snap(containment=[{"status": "cancelled", "evidence_notes": None}])
    assert not item(cancelled_only, "D3")["requirements"][0]["met"]


def test_d4_requires_decided_causes_and_root_cause():
    s = snap(causes=[{"id": "a", "investigation_status": "root_cause"}, {"id": "b", "investigation_status": "needs_more_investigation"}])
    met = {r["key"]: r["met"] for r in item(s, "D4")["requirements"]}
    assert met["root_cause"] and not met["all_decided"]
    none = snap(causes=[{"id": "a", "investigation_status": "not_root_cause"}])
    assert not {r["key"]: r["met"] for r in item(none, "D4")["requirements"]}["root_cause"]


def action(id_, type_="corrective", status="open", cause="c-root", **kw):
    return {"id": id_, "action_type": type_, "status": status, "cause_id": cause, "responsible_user_id": OWNER,
            "due_date": "2026-11-30", **kw}


def met(s, code):
    return {r["key"]: r["met"] for r in item(s, code)["requirements"]}


def test_d5_every_root_cause_needs_assigned_corrective_action_and_criterion():
    s = snap(content={"D5": {"verification_plan": "Prueba piloto"}})
    assert met(s, "D5") == {"has_corrective": False, "roots_covered": False, "assigned": False, "criteria": False,
                            "verification_plan": True}
    s = snap(content={"D5": {"verification_plan": "x"}}, approved_criteria=1,
             actions=[action("a1"), action("a2", responsible_user_id=None)])
    assert met(s, "D5")["roots_covered"] and not met(s, "D5")["assigned"]
    # Una acción cancelada no cubre la causa.
    s = snap(approved_criteria=1, actions=[action("a1", status="cancelled", cancel_reason="x")])
    assert not met(s, "D5")["roots_covered"]


def test_d6_requires_approval_and_effective_check():
    s = snap(content={"D6": {"validation_summary": "ok"}}, actions=[action("a1", status="approved")])
    assert met(s, "D6") == {"implemented": True, "effective": False, "no_ineffective": True, "validation_summary": True}
    s.latest_checks = {"a1": "effective"}
    assert all(met(s, "D6").values())
    s = snap(actions=[action("a1", status="ineffective")], latest_checks={"a1": "ineffective"})
    assert not met(s, "D6")["no_ineffective"]
    # Datos insuficientes no cuentan como eficaz.
    s = snap(actions=[action("a1", status="approved")], latest_checks={"a1": "insufficient_data"})
    assert not met(s, "D6")["effective"]


def test_d7_accepts_justification_but_not_pending_updates():
    s = snap(content={"D7": {"horizontal_deployment": "Línea 2", "no_update_justification": "No cambia el AMEF",
                             "no_preventive_justification": "Cubierto por la correctiva"}})
    assert all(met(s, "D7").values())
    s.system_updates = [{"status": "planned"}]
    assert not met(s, "D7")["updates_done"]
    s = snap(content={"D7": {"horizontal_deployment": "x"}}, system_updates=[{"status": "completed"}],
             actions=[action("p1", "preventive", "pending_approval", cause=None)])
    assert met(s, "D7")["updates"] and not met(s, "D7")["preventive"] and not met(s, "D7")["preventive_done"]


def test_d8_requires_approved_lesson_and_closes_case():
    s = snap(content={"D8": {"closure_summary": "x", "team_recognition": "y"}}, lessons=["draft"],
             actions=[action("a1", status="verified")])
    assert met(s, "D8") == {"lesson": False, "actions_closed": True, "closure_summary": True, "team_recognition": True}
    s.lessons = ["published"]
    assert all(met(s, "D8").values())
    closed = snap(status={c: "approved" for c in workflow.CODES})
    assert workflow.case_status_after(closed) == "closed"


def test_closed_case_only_reopens_through_d8():
    s = snap(case=full_case(status="closed"), status={c: "approved" for c in workflow.CODES})
    workflow.check_reopen("D8", s)
    with pytest.raises(RuleError) as exc:
        workflow.check_reopen("D7", s)
    assert exc.value.code == "case_closed"
    with pytest.raises(RuleError):
        workflow.check_edit("D8", s)


def test_all_disciplines_available():
    assert all(d["available"] for d in workflow.evaluate(snap()))


def test_edit_blocked_while_pending_or_approved():
    for status in ("pending_review", "approved"):
        with pytest.raises(RuleError):
            workflow.check_edit("D2", snap(status={"D2": status}))
    workflow.check_edit("D2", snap(status={"D2": "in_progress"}))


def test_approve_rechecks_requirements():
    s = snap(status={"D0": "approved", "D1": "approved", "D2": "approved", "D3": "pending_review"},
             containment=[{"status": "cancelled", "evidence_notes": None}])
    with pytest.raises(RuleError) as exc:
        workflow.check_approve("D3", s)
    assert exc.value.code == "requirements_pending"


def test_reopen_only_last_locked_discipline():
    s = snap(status={"D0": "approved", "D1": "approved", "D2": "pending_review"})
    with pytest.raises(RuleError) as exc:
        workflow.check_reopen("D1", s)
    assert exc.value.code == "later_disciplines"
    workflow.check_reopen("D1", snap(status={"D0": "approved", "D1": "approved"}))


def test_locked_fields_follow_discipline_status():
    assert workflow.locked_fields(snap()) == set()
    assert "part_number" in workflow.locked_fields(snap(status={"D2": "pending_review"}))
    assert "severity" in workflow.locked_fields(snap(status={"D0": "approved"}))


def test_cancelled_case_rejects_everything():
    s = snap(case=full_case(status="cancelled"))
    for check in (workflow.check_edit, workflow.check_submit, workflow.check_review):
        with pytest.raises(RuleError) as exc:
            check("D0", s)
        assert exc.value.code == "case_closed"


@pytest.mark.parametrize("status,expected", [
    ({}, "draft"),
    ({"D0": "in_progress"}, "open"),
    ({"D0": "pending_review"}, "pending_review"),
    ({"D0": "approved"}, "in_progress"),
    ({"D0": "approved", "D1": "pending_review"}, "pending_review"),
])
def test_case_status_derivation(status, expected):
    assert workflow.case_status_after(snap(status=status, case=full_case(status="draft"))) == expected
