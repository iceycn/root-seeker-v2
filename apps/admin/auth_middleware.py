from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from apps.admin.session_store import SESSION_COOKIE_NAME, SessionStore
from apps.admin.user_store import UserStore

PUBLIC_EXACT = {
    ("GET", "/healthz"),
    ("GET", "/login"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/bootstrap"),
    ("POST", "/api/auth/logout"),
}


def is_public(method: str, path: str) -> bool:
    if path.startswith("/assets/"):
        return True
    return (method.upper(), path) in PUBLIC_EXACT


def AdminAuthMiddleware(session_store: SessionStore, user_store: UserStore):  # noqa: N802
    async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        method = request.method.upper()
        path = request.url.path
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        record = session_store.get(session_id) if session_id else None
        if record is not None and user_store.get_by_id(record.user_id) is None:
            session_store.delete(session_id or "")
            record = None
        request.state.admin_user = record
        if is_public(method, path) or record is not None:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    return middleware
