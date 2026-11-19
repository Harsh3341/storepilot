"""Owner login/session/logout endpoints; business protection lives in app setup."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from storepilot.auth import Auth, AuthError, SESSION_SECONDS


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    password: Annotated[StrictStr, Field(min_length=1, max_length=1024)]


def make_auth_router(auth: Auth, settings) -> APIRouter:
    router = APIRouter(prefix="/api/auth")

    def status(session=None):
        return {"enabled": auth.has_owner(), "authenticated": session is not None,
                "username": session["username"] if session else None,
                "csrf_token": session["csrf_token"] if session else None}

    @router.get("/session")
    def session(request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return status(auth.session(request.cookies.get(settings.session_cookie)))

    @router.post("/login")
    def login(body: LoginRequest, request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        if not settings.accepts_origin(request):
            raise HTTPException(status_code=403, detail="Login origin is not allowed.", headers={"Cache-Control": "no-store"})
        try:
            result = auth.login(body.username, body.password, request.client.host if request.client else "unknown")
        except AuthError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error), headers={"Cache-Control": "no-store"}) from error
        response.set_cookie(settings.session_cookie, result["token"], max_age=SESSION_SECONDS,
                            path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
        return status(result)

    @router.post("/logout")
    def logout(request: Request, response: Response):
        auth.logout(request.cookies.get(settings.session_cookie))
        response.delete_cookie(settings.session_cookie, path="/", secure=settings.secure_cookies,
                               httponly=True, samesite="lax")
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True}

    return router
