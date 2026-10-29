"""API de 8D PRO (FastAPI)."""
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import errors
from app.db import Database, database_url
from app.routers import (actions, alerts, auth_routes, cases_routes, containment, core, ishikawa, lessons,
                         notifications, reports)

CLIENT_HEADER = "x-d8-client"


def create_app(url: str | None = None) -> FastAPI:
    db = Database(url or database_url())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.open()
        app.state.db = db
        yield
        db.close()

    app = FastAPI(title="8D PRO API", version="0.5.0", lifespan=lifespan)
    errors.install(app)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Defensa CSRF adicional a SameSite=Lax: las peticiones que modifican datos deben venir de
        # nuestro cliente (cabecera personalizada; un formulario de otro sitio no puede añadirla).
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CLIENT_HEADER) != "web":
            return JSONResponse({"code": "csrf", "message": "Petición rechazada (falta cabecera de cliente)."},
                                status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        # Identificador de la solicitud: se guarda en la bitácora y se devuelve al cliente para soporte.
        incoming = request.headers.get("x-request-id", "")
        request.state.request_id = incoming if re.fullmatch(r"[A-Za-z0-9-]{8,64}", incoming) else uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/health")
    def health():
        with app.state.db.transaction() as conn:
            conn.execute("select 1")
        return {"status": "ok"}

    for module in (auth_routes, core, cases_routes, containment, alerts, ishikawa, actions, lessons, reports,
                   notifications):
        app.include_router(module.router)
    return app
