"""Redesign spec §7.1. Prefix /api; every path below is relative to it."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app import settings_store
from app.auth.deps import bearer_token, current_user
from app.auth.passwords import burn_time, hash_password, verify_password
from app.auth.sessions import create_session, delete_session, delete_sessions_for_user
from app.db.connection import get_db, utcnow_iso
from app.routers.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OkResponse,
    UserOut,
)

router = APIRouter(prefix="/api", tags=["auth"])

# One message for every way a login can fail. Naming which half was wrong turns
# the login form into a username directory.
_BAD_LOGIN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
)


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> LoginResponse:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (payload.username,)).fetchone()

    if row is None or row["disabled"]:
        burn_time()
        raise _BAD_LOGIN
    if not verify_password(row["password_hash"], payload.password):
        raise _BAD_LOGIN

    return LoginResponse(token=create_session(conn, row["id"]), user=UserOut.from_row(row))


@router.post("/auth/change-password", response_model=OkResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    token: Annotated[str, Depends(bearer_token)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> OkResponse:
    if not verify_password(user["password_hash"], payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is wrong"
        )

    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (hash_password(payload.new_password), user["id"]),
    )
    # Everyone else holding a token for this account loses it. The tab that made
    # the change keeps working.
    delete_sessions_for_user(conn, user["id"], keep=token)
    return OkResponse()


@router.post("/auth/logout", response_model=OkResponse)
def logout(
    token: Annotated[str, Depends(bearer_token)],
    _: Annotated[sqlite3.Row, Depends(current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> OkResponse:
    delete_session(conn, token)
    return OkResponse()


@router.get("/me", response_model=MeResponse)
def me(
    user: Annotated[sqlite3.Row, Depends(current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> MeResponse:
    return MeResponse(
        user=UserOut.from_row(user),
        settings=settings_store.public_settings(conn),
        server_time=utcnow_iso(),
    )
