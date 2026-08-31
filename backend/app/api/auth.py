"""PatchPilot session and GitHub App authorization."""

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.config import SESSION_COOKIE_NAME
from app.dependencies import (
    get_auth_service,
    get_optional_session,
    get_settings,
)
from app.errors import AuthorizationFailed, InvalidOAuthState, NotAuthenticated
from app.infrastructure.github_app_client import sanitize_oauth_authorize_url
from app.schemas import AuthInstallStart, AuthLoginStart, AuthMe, AuthUser

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])


def _set_session_cookie(response, session_id, settings):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
        path="/",
    )


def _clear_session_cookie(response, settings):
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@auth_router.get("/me", response_model=AuthMe)
def auth_me(session=Depends(get_optional_session), auth=Depends(get_auth_service)):
    if session is None:
        return AuthMe(authenticated=False, user=None)

    user = auth.store.get_user(session.user_id)
    if user is None:
        return AuthMe(authenticated=False, user=None)

    return AuthMe(authenticated=True, user=AuthUser(**user.public_dict()))


@auth_router.get("/github/login", response_model=AuthLoginStart)
def github_login(
    request: Request,
    return_to: str | None = Query(None),
    auth=Depends(get_auth_service),
    session=Depends(get_optional_session),
):
    """
    Start GitHub App authorization.

    Returns a URL. The browser navigates there; GitHub posts back to
    /api/auth/github/callback. Credentials never reach the client.
    """

    origin = return_to or request.headers.get("origin")
    started = auth.start_login(
        origin,
        user_id=session.user_id if session else None,
    )
    logger.info(
        "GitHub App user-authorization URL %s",
        sanitize_oauth_authorize_url(started["authorization_url"]),
    )
    return AuthLoginStart(
        authorization_url=started["authorization_url"],
        installation_url=started["installation_url"],
    )


@auth_router.get("/github/install", response_model=AuthInstallStart)
def github_install(
    request: Request,
    return_to: str | None = Query(None),
    auth=Depends(get_auth_service),
    session=Depends(get_optional_session),
):
    """Start GitHub App installation or repository-grant management."""

    if session is None:
        raise NotAuthenticated("Connect GitHub to choose repositories")

    origin = return_to or request.headers.get("origin")
    started = auth.start_install(origin, session.id)
    return AuthInstallStart(installation_url=started["installation_url"])


def _connected_destination(return_to, fallback):
    destination = (return_to or fallback).rstrip("/")
    if "?" in destination:
        return f"{destination}&connected=1"
    return f"{destination}/?connected=1"


def _session_destination(return_to, fallback, session_id):
    """
    Send the browser back to the UI with the session in the fragment.

    The API and Flutter web-server are different origins, so the
    httponly cookie is third-party on XHR and is dropped after a
    reload. The fragment is first-party, not sent to the web-server,
    and survives Flutter hot restart once copied to localStorage.
    """

    destination = _connected_destination(return_to, fallback)
    return f"{destination}#session={session_id}"


@auth_router.get("/github/callback")
def github_callback(
    code: str | None = None,
    state: str | None = None,
    installation_id: str | None = None,
    setup_action: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    auth=Depends(get_auth_service),
    settings=Depends(get_settings),
    session=Depends(get_optional_session),
):
    """GitHub redirects here. Sets the session cookie and returns to the UI."""

    fallback = settings.frontend_origin.rstrip("/")

    if error:
        detail = error_description or error
        return RedirectResponse(
            f"{fallback}/?auth_error={detail}",
            status_code=302,
        )

    install_return = bool(installation_id or setup_action) and not code

    try:
        if install_return:
            if session is None:
                raise NotAuthenticated(
                    "Connect GitHub before selecting repositories"
                )
            session, _user, return_to = auth.complete_installation_return(
                session_id=session.id,
                state=state,
            )
        else:
            session, _user, return_to = auth.complete_login(
                code=code or "",
                state=state or "",
                installation_id=installation_id,
            )
    except (InvalidOAuthState, AuthorizationFailed, NotAuthenticated) as exc:
        return RedirectResponse(
            f"{fallback}/?auth_error={exc}",
            status_code=302,
        )

    destination = _session_destination(return_to, fallback, session.id)
    response = RedirectResponse(destination, status_code=302)
    _set_session_cookie(response, session.id, settings)
    return response


@auth_router.post("/logout")
def logout(
    response: Response,
    session=Depends(get_optional_session),
    auth=Depends(get_auth_service),
    settings=Depends(get_settings),
):
    if session is not None:
        auth.logout(session.id)
    _clear_session_cookie(response, settings)
    return {"ok": True}
