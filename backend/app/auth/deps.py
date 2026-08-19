"""Three dependencies, in increasing order of what they demand.

    current_user   a live token
    active_user    ... and the forced password change is done
    require_admin  ... and role = 'admin'

Everything under /api uses active_user or require_admin. The only three routes
allowed to use current_user are /api/me, /api/auth/change-password and
/api/auth/logout — a user who must change their password has to be able to see
who they are, change it, and give up.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.auth.sessions import resolve_session
from app.db.connection import get_db

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise _UNAUTHENTICATED
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _UNAUTHENTICATED
    return token


def current_user(
    token: Annotated[str, Depends(bearer_token)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> sqlite3.Row:
    user = resolve_session(conn, token)
    if user is None:
        raise _UNAUTHENTICATED
    return user


def active_user(user: Annotated[sqlite3.Row, Depends(current_user)]) -> sqlite3.Row:
    if user["must_change_password"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Password change required"
        )
    return user


def require_admin(user: Annotated[sqlite3.Row, Depends(active_user)]) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
