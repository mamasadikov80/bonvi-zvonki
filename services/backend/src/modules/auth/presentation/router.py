"""Autentifikatsiya endpointlari."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from src.core.config import settings
from src.core.deps import CurrentUser, DbSession
from src.core.exceptions import UnauthorizedError
from src.core.security import (
    REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from src.modules.settings.application.services import SettingsService
from src.modules.users.domain.entities import resolve_permissions
from src.modules.users.infrastructure.models import UserModel

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    agent_id: str | None
    permissions: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse, summary="Tizimga kirish")
async def login(payload: LoginRequest, session: DbSession, response: Response):
    row = (
        await session.execute(
            select(UserModel).where(UserModel.email == payload.email.lower())
        )
    ).scalar_one_or_none()

    if row is None or not verify_password(payload.password, row.password_hash):
        raise UnauthorizedError("Email yoki parol noto'g'ri")

    if not row.is_active:
        raise UnauthorizedError("Akkaunt faol emas")

    access = create_access_token(row.id)
    refresh = create_refresh_token(row.id)

    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse, summary="Tokenni yangilash")
async def refresh_token(payload: RefreshRequest, session: DbSession):
    user_id = decode_token(payload.refresh_token, expected_type=REFRESH)
    if user_id is None:
        raise UnauthorizedError("Refresh token yaroqsiz")

    row = await session.get(UserModel, user_id)
    if row is None or not row.is_active:
        raise UnauthorizedError("Foydalanuvchi topilmadi")

    return TokenResponse(
        access_token=create_access_token(row.id),
        refresh_token=create_refresh_token(row.id),
    )


@router.post("/logout", summary="Chiqish")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me", response_model=UserResponse, summary="Joriy foydalanuvchi")
async def me(user: CurrentUser, session: DbSession):
    """Ruxsatlar rolning bazaviy to'plami + sozlamalardan kelgan qo'shimchalar.

    Shuning uchun admin "Ruxsatlar" bo'limida biror narsani yoqsa,
    frontend keyingi so'rovda darhol yangi menyuni ko'radi.
    """
    access = await SettingsService(session).access_values()
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        agent_id=str(user.agent_id) if user.agent_id else None,
        permissions=sorted(resolve_permissions(user.role, access)),
    )
