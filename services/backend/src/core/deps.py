"""FastAPI dependency'lari — autentifikatsiya va ruxsat tekshiruvi."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security import decode_token
from src.modules.users.domain.entities import Role, User, has_permission
from src.modules.users.infrastructure.models import UserModel

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    # Brauzer uchun cookie ham qo'llab-quvvatlanadi
    return request.cookies.get("access_token")


async def get_current_user(request: Request, session: DbSession) -> User:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Avtorizatsiya talab qilinadi")

    user_id = decode_token(token)
    if user_id is None:
        raise UnauthorizedError("Token yaroqsiz yoki muddati o'tgan")

    row = await session.get(UserModel, user_id)
    if row is None or not row.is_active:
        raise UnauthorizedError("Foydalanuvchi topilmadi yoki faol emas")

    return User(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        role=row.role,
        is_active=row.is_active,
        agent_id=row.agent_id,
        created_at=row.created_at,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str) -> Callable:
    """Ruxsat talab qiladigan dependency yaratadi.

    Ishlatish:
        @router.get("/", dependencies=[Depends(require_permission("agents:read"))])
    """

    async def checker(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise ForbiddenError(f"Ruxsat yetarli emas: {permission}")
        return user

    return checker


def require_roles(*roles: Role) -> Callable:
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise ForbiddenError(f"Faqat quyidagi rollar uchun: {allowed}")
        return user

    return checker


# Tez-tez ishlatiladigan qisqartmalar
RequireAdmin = Annotated[User, Depends(require_roles(Role.ADMIN))]
RequireManager = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]


async def get_user_or_none(request: Request, session: DbSession) -> User | None:
    """Ixtiyoriy avtorizatsiya — VIEWER (monitor) rejimi uchun."""
    try:
        return await get_current_user(request, session)
    except UnauthorizedError:
        return None
