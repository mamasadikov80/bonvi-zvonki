"""Foydalanuvchi hisoblari — faqat admin uchun."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from src.core.deps import DbSession, RequireAdmin
from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.security import hash_password
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel

router = APIRouter(prefix="/users", tags=["Users"])


class UserRow(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    agent_id: UUID | None
    agent_name: str | None = None
    created_at: datetime


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: Role
    agent_id: UUID | None = None


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    agent_id: UUID | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


@router.get("", response_model=list[UserRow], summary="Foydalanuvchilar ro'yxati")
async def list_users(session: DbSession, _: RequireAdmin):
    rows = (
        await session.execute(
            select(UserModel, AgentModel.full_name)
            .outerjoin(AgentModel, AgentModel.id == UserModel.agent_id)
            .order_by(UserModel.created_at.desc())
        )
    ).all()

    return [
        UserRow(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            agent_id=u.agent_id,
            agent_name=agent_name,
            created_at=u.created_at,
        )
        for u, agent_name in rows
    ]


@router.post("", response_model=UserRow, status_code=201, summary="Hisob yaratish")
async def create_user(payload: CreateUserRequest, session: DbSession, _: RequireAdmin):
    email = payload.email.lower()

    exists = (
        await session.execute(select(UserModel).where(UserModel.email == email))
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("Bu email allaqachon ro'yxatdan o'tgan")

    await _validate_agent_link(session, payload.role, payload.agent_id)

    user = UserModel(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        agent_id=payload.agent_id,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    return UserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        agent_id=user.agent_id,
        created_at=user.created_at,
    )


@router.patch("/{user_id}", response_model=UserRow, summary="Hisobni tahrirlash")
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    session: DbSession,
    admin: RequireAdmin,
):
    user = await session.get(UserModel, user_id)
    if user is None:
        raise NotFoundError("Foydalanuvchi topilmadi")

    data = payload.model_dump(exclude_unset=True)

    # Admin o'zini o'chirib qo'yolmasin
    if user.id == admin.id and data.get("is_active") is False:
        raise ValidationError("O'z hisobingizni o'chira olmaysiz")
    if user.id == admin.id and data.get("role") not in (None, Role.ADMIN):
        raise ValidationError("O'z rolingizni o'zgartira olmaysiz")

    role = data.get("role", user.role)
    agent_id = data.get("agent_id", user.agent_id)
    await _validate_agent_link(session, role, agent_id)

    if password := data.pop("password", None):
        user.password_hash = hash_password(password)

    for key, value in data.items():
        setattr(user, key, value)

    await session.flush()

    return UserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        agent_id=user.agent_id,
        created_at=user.created_at,
    )


async def _validate_agent_link(
    session: DbSession, role: Role, agent_id: UUID | None
) -> None:
    """SALES roli albatta savdo xodimiga bog'langan bo'lishi kerak."""
    if role is Role.SALES and agent_id is None:
        raise ValidationError(
            "Savdo xodimi roli uchun qaysi xodimga bog'lanishini tanlang"
        )
    if agent_id is not None:
        agent = await session.get(AgentModel, agent_id)
        if agent is None:
            raise NotFoundError("Savdo xodimi topilmadi")
