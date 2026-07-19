"""
Auth routes (Part 8).

POST /auth/signup creates a new Organization plus its first User as
admin - this is the only way a brand new tenant enters the system.
POST /auth/login issues a JWT carrying user_id, organization_id, and
role so every other route can authorize without extra DB lookups.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Organization, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class SignupResponse(BaseModel):
    organization_id: str
    user_id: str
    email: str
    access_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    org = Organization(id=str(uuid.uuid4()), name=payload.organization_name)
    db.add(org)
    db.flush()  # so org.id is available for the FK below without a full commit yet

    user = User(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role="admin",  # the org creator is always admin
        is_active=True,
    )
    db.add(user)
    db.commit()

    token = create_access_token({"sub": user.id, "org": org.id, "role": user.role})
    return SignupResponse(organization_id=org.id, user_id=user.id, email=user.email, access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == form_data.username, User.is_active.is_(True)).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    token = create_access_token({"sub": user.id, "org": user.organization_id, "role": user.role})
    return TokenResponse(access_token=token)
