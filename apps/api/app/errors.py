"""Errores de dominio con forma JSON estable: {code, message, details}."""
import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(entity: str = "Recurso") -> ApiError:
    # 404 también para recursos de otra organización: no se revela su existencia.
    return ApiError(404, "not_found", f"{entity} no encontrado.")


def forbidden(message: str = "No tienes permiso para esta acción.") -> ApiError:
    return ApiError(403, "forbidden", message)


def conflict(code: str, message: str, details=None) -> ApiError:
    return ApiError(409, code, message, details)


def invalid(message: str, details=None) -> ApiError:
    return ApiError(422, "invalid", message, details)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse({"code": exc.code, "message": exc.message, "details": exc.details}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"code": "invalid", "message": "Datos no válidos.", "details": details}, status_code=422)

    @app.exception_handler(psycopg.errors.CheckViolation)
    async def _check(_: Request, exc: psycopg.errors.CheckViolation):
        return JSONResponse({"code": "constraint", "message": "La base de datos rechazó los datos (restricción).",
                             "details": exc.diag.constraint_name}, status_code=422)

    @app.exception_handler(psycopg.errors.UniqueViolation)
    async def _unique(_: Request, exc: psycopg.errors.UniqueViolation):
        return JSONResponse({"code": "duplicate", "message": "Ya existe un registro con esos datos.",
                             "details": exc.diag.constraint_name}, status_code=409)

    @app.exception_handler(psycopg.errors.RaiseException)
    async def _raise(_: Request, exc: psycopg.errors.RaiseException):
        return JSONResponse({"code": "rule", "message": exc.diag.message_primary}, status_code=409)
