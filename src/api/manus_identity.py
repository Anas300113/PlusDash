"""Verified Manus session identity for account-backed learner endpoints.

The browser never supplies an authoritative student id. Next.js forwards the
already-validated webdev_app_session JWT as a server-to-server Bearer token.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class LearnerIdentity:
    student_id: str
    display_name: str


def derive_student_id(open_id: str, secret: str) -> str:
    """Return a non-reversible stable ID; never persist the provider openId."""
    payload = b"plus11-learner-id-v1:" + open_id.encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return "p11_" + digest


def get_current_learner(
    authorization: str | None = Header(default=None),
) -> LearnerIdentity:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            401, "Please sign in to access your learning.",
            headers={"WWW-Authenticate": "Bearer"})

    secret = os.environ.get("MANUS_JWT_SECRET", "")
    project_id = os.environ.get("MANUS_PROJECT_ID", "")
    if not secret or not project_id:
        raise HTTPException(503, "Account-backed learning is not configured.")

    token = authorization[7:].strip()
    if not token or len(token) > 8192:
        raise HTTPException(401, "The sign-in session is invalid.")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat"], "verify_aud": False},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Your sign-in session has expired. Please sign in again.") from None

    open_id = claims.get("openId")
    if claims.get("appId") != project_id or not isinstance(open_id, str) or not open_id.strip() or len(open_id) > 1024:
        raise HTTPException(401, "The sign-in session is not valid for this Plus11 app.")

    raw_name = claims.get("name")
    name = " ".join(raw_name.split())[:80] if isinstance(raw_name, str) else ""
    return LearnerIdentity(
        student_id=derive_student_id(open_id, secret),
        display_name=name or "Learner",
    )
