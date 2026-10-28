"""Matriz de permisos por rol. La autorización se aplica siempre en el backend."""

ROLE_NAMES = {
    "admin": "Administrador",
    "quality_manager": "Gerente de calidad",
    "engineer": "Ingeniero de calidad",
    "viewer": "Consulta",
}

_VIEWER = {"case.read", "lesson.read"}
_ENGINEER = _VIEWER | {
    "case.create", "case.edit", "containment.edit", "alert.edit",
    "cause.edit", "cause.validate", "attachment.upload", "comment.create",
    "action.edit", "effectiveness.edit", "lesson.edit", "lesson.apply", "document.generate", "report.export",
}
_MANAGER = _ENGINEER | {
    "discipline.approve", "alert.issue", "case.cancel", "catalog.manage",
    "action.approve", "criteria.approve", "lesson.review", "lesson.publish", "lesson.retire", "audit.read",
}

PERMISSIONS: dict[str, set[str]] = {
    "viewer": _VIEWER,
    "engineer": _ENGINEER,
    "quality_manager": _MANAGER,
    "admin": _MANAGER | {"admin.users"},
}


def permissions_for(roles: set[str]) -> set[str]:
    result: set[str] = set()
    for role in roles:
        result |= PERMISSIONS.get(role, set())
    return result
