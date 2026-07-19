"""
Auth dependencies (Part 8 - Multi-Tenancy & RBAC).

Every protected route depends on get_current_user, which decodes the
JWT, loads the User row, and returns it. organization_id and role come
straight from the token so authorization checks never require an extra
DB round-trip. require_role() builds a dependency that enforces RBAC
(Admin / Analyst / Viewer) on top of authentication.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_HIERARCHY = {"viewer": 0, "analyst": 1, "admin": 2}


@dataclass
class CurrentUser:
    id: str
    organization_id: str
    email: str
    role: str


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> CurrentUser:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return CurrentUser(id=user.id, organization_id=user.organization_id, email=user.email, role=user.role)


def require_role(minimum_role: str):
    """
    Returns a FastAPI dependency that enforces the current user's role
    is at least `minimum_role` in the Admin > Analyst > Viewer hierarchy.
    Usage: Depends(require_role("analyst")) on a route that mutates data.
    """
    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if ROLE_HIERARCHY.get(current_user.role, -1) < ROLE_HIERARCHY.get(minimum_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires at least '{minimum_role}' role; you have '{current_user.role}'",
            )
        return current_user
    return _check
