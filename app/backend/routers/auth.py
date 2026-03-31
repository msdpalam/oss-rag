"""
Auth router — registration, login, and current-user endpoints.

POST /auth/register   Create a new account; returns JWT + user info
POST /auth/login      Authenticate with email + password; returns JWT + user info
GET  /auth/me         Return the currently logged-in user (requires valid JWT)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.database import get_db
from core.models import User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email or "",
        display_name=user.display_name,
        created_at=user.created_at.isoformat(),
    )


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(str(user.id), user.email or "")
    return TokenResponse(access_token=token, user=_user_response(user))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if len(body.password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be at least 8 characters")

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        display_name=body.display_name or body.email.split("@")[0],
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _token_response(user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)
