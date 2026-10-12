"""Mot de passe unique, obligatoire dès que Jideo écoute hors de localhost."""
from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

COOKIE = "jideo_session"
MAX_AGE = 30 * 24 * 3600
LOGIN_FAILURE_DELAY = 1.0  # ralentit les essais de mot de passe
PUBLIC_PATHS = {"/api/health", "/api/login", "/api/logout"}

router = APIRouter()


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt="jideo-session")


def is_authenticated(request: Request) -> bool:
    settings = request.app.state.settings
    if not settings.auth_required:
        return True
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        _serializer(settings.secret).loads(token, max_age=MAX_AGE)
    except BadSignature:
        return False
    return True


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS and not is_authenticated(request):
        return JSONResponse({"detail": "Authentification requise"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    password: str


@router.post("/api/login", status_code=204)
def login(body: Login, request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.auth_required:
        return Response(status_code=204)
    if not hmac.compare_digest(body.password.encode(), settings.password.encode()):
        time.sleep(LOGIN_FAILURE_DELAY)
        return JSONResponse({"detail": "Mot de passe incorrect"}, status_code=401)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE, _serializer(settings.secret).dumps("ok"), max_age=MAX_AGE, httponly=True, samesite="lax"
    )
    return response


@router.post("/api/logout", status_code=204)
def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE)
    return response
