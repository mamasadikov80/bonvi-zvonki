"""Hisoblar bilan ishlaydigan testlar uchun yordamchi fixture'lar.

Umumiy poydevor `src/conftest.py` da. Bu yerdagi ikkita fixture aynan
FOYDALANUVCHI HISOBIGA tegishli, shuning uchun `users` modulida turadi
va `auth` testlari ham shu yerdan oladi:

  `make_user`   — paroli bizga MA'LUM hisob yaratadi (bazaga to'g'ridan
                  to'g'ri). Mavjud dev hisoblarining paroli test ichida
                  qattiq yozilsa, kimdir uni almashtirgan kuni testlar
                  sababsiz qizarardi.
  `yangi_email` — API orqali yaratiladigan hisoblar uchun noyob email
                  beradi va test oxirida AYNAN o'shalarni o'chiradi.

Ikkalasi ham faqat o'zi yaratganini tozalaydi — mavjud yozuvlarga
tegilmaydi.

NEGA EMAIL `@zvonki.uz`
  `@test.local`, `@example.com` va shu kabi zaxiralangan domenlarni
  `EmailStr` (pydantic → email-validator) rad etadi — «special-use or
  reserved name». Shuning uchun haqiqiy domen olinadi, noyoblik esa
  mahalliy qismdagi tasodifiy prefiks bilan ta'minlanadi. Yozuv test
  oxirida baribir o'chiriladi, hech qanday xat yuborilmaydi.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import delete

from src.conftest import MARK
from src.core.database import SessionFactory
from src.core.security import hash_password
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel


@dataclass(slots=True)
class TempUser:
    """Test yaratgan hisob — paroli ochiq matnda ma'lum."""

    id: uuid.UUID
    email: str
    password: str
    role: Role
    is_active: bool


UserFactory = Callable[..., TempUser]


@pytest_asyncio.fixture
async def make_user() -> AsyncIterator[UserFactory]:
    """Vaqtinchalik hisob yaratadi va test oxirida o'chiradi.

    Ishlatilishi::

        user = await make_user(role=Role.MANAGER)
        user = await make_user(is_active=False)
    """
    created: list[uuid.UUID] = []

    async def _make(
        *,
        role: Role = Role.VIEWER,
        is_active: bool = True,
        password: str = "pytest-secret-123",
        agent_id: uuid.UUID | None = None,
    ) -> TempUser:
        email = f"{MARK}-{uuid.uuid4().hex[:10]}@zvonki.uz"
        async with SessionFactory() as session:
            row = UserModel(
                email=email,
                password_hash=hash_password(password),
                full_name=f"{MARK} {role.value}",
                role=role,
                agent_id=agent_id,
                is_active=is_active,
            )
            session.add(row)
            await session.commit()
            created.append(row.id)
            return TempUser(
                id=row.id,
                email=email,
                password=password,
                role=role,
                is_active=is_active,
            )

    yield _make

    async with SessionFactory() as session:
        if created:
            await session.execute(delete(UserModel).where(UserModel.id.in_(created)))
        await session.commit()


@pytest_asyncio.fixture
async def yangi_email() -> AsyncIterator[Callable[..., str]]:
    """Noyob email beradi va uni tozalash ro'yxatiga qo'shadi.

    API orqali yaratilgan hisob uchun: `POST /users` javobidagi id ni
    kuzatib yurishdan ko'ra emailni oldindan bilib turgan qulay —
    so'rov 4xx bilan tugasa ham ro'yxat to'g'ri qoladi.
    """
    berilgan: list[str] = []

    def _make(prefiks: str = "user") -> str:
        email = f"{MARK}-{prefiks}-{uuid.uuid4().hex[:10]}@zvonki.uz"
        berilgan.append(email)
        return email

    yield _make

    async with SessionFactory() as session:
        if berilgan:
            # Katta harf bilan yuborilgan bo'lsa ham baza kichik harfda saqlaydi
            hammasi = berilgan + [e.lower() for e in berilgan]
            await session.execute(delete(UserModel).where(UserModel.email.in_(hammasi)))
        await session.commit()
