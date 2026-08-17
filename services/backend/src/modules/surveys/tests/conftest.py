"""So'rovnoma testlariga xos fixture'lar.

Umumiy poydevor `src/conftest.py` da: `admin_client`, `anon_client`,
`sales_client`, `dataset`, `settings_guard`. Bu yerda faqat shu modulga
kerak bo'lgan ikkita narsa qo'shiladi.

NEGA `survey_factory` KERAK
  `dataset` fixture'i har bahoga BITTA so'rovnoma yaratadi va vaqtni
  «necha kun oldin» aniqligida beradi. So'rovnoma endpointidagi ikkita
  savol esa bundan nozikroq:

    • guruh oqimi — BITTA so'rovnoma, unga o'nlab javob. JOIN dublikat
      bermayaptimi degan savolga faqat shu shakl javob beradi.
    • sana chegarasi — «yuborilgan kuni» bilan «javob kelgan kuni» ATAYLAB
      boshqa kunga tushishi kerak, ya'ni soat-daqiqagacha aniq vaqt kerak.

  Yaratilgan so'rovnomalar test oxirida o'chiriladi; javoblar `ON DELETE
  CASCADE` bilan o'zi ketadi.

NEGA `login_as` KERAK
  `sales_client` har doim xodimga BOG'LANGAN savdo hisobini beradi.
  `agent_id` NULL bo'lgan holatni tekshirish uchun esa bog'lanmagan
  hisob kerak — uni shu fixture yaratadi va oxirida o'chiradi.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import delete

from src.conftest import MARK
from src.core.database import SessionFactory
from src.core.security import hash_password
from src.main import app
from src.modules.surveys.domain.entities import (
    SurveyChannel,
    SurveyStatus,
    new_survey_token,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel

TEST_PASSWORD = "pytest-secret-123"


@pytest_asyncio.fixture
async def survey_factory() -> AsyncIterator[Callable[..., Any]]:
    """Aniq vaqtli bitta so'rovnoma va uning javoblarini yozadi.

    Ishlatilishi::

        await survey_factory(
            agent_id=data.agent_id,
            sent_at=kun_x,                       # yuborilgan payt
            responses=[
                {"csat": 5, "responded_at": kun_x + timedelta(days=1)},
            ],
        )

    `sent_at` berilmasa — eng erta javobdan bir soat oldin. Bu «odatiy»
    holat: so'rovnoma yuborilgan kuni javob ham kelgan.
    """
    created: list[uuid.UUID] = []

    async def _make(
        *,
        agent_id: uuid.UUID,
        responses: list[dict[str, Any]],
        client_id: uuid.UUID | None = None,
        sent_at: datetime | None = None,
        status: SurveyStatus = SurveyStatus.COMPLETED,
    ) -> uuid.UUID:
        now = datetime.now(UTC)
        earliest = min((r["responded_at"] for r in responses), default=now)
        sent = sent_at if sent_at is not None else earliest - timedelta(hours=1)

        async with SessionFactory() as session:
            survey = SurveyModel(
                client_id=client_id,
                agent_id=agent_id,
                token=new_survey_token(),
                period_start=sent - timedelta(days=14),
                period_end=sent,
                channel=SurveyChannel.TELEGRAM_GROUP,
                status=status,
                sent_at=sent,
                expires_at=sent + timedelta(days=7),
                response_count=len(responses),
            )
            session.add(survey)
            await session.flush()

            for item in responses:
                session.add(
                    SurveyResponseModel(
                        survey_id=survey.id,
                        # Har javob boshqa odamdan: `uq_response_per_respondent`
                        # bitta so'rovnomaga bir xil hash'ni ikki marta qo'ymaydi.
                        respondent_hash=item.get("respondent_hash")
                        or uuid.uuid4().hex,
                        csat=item["csat"],
                        comment=item.get("comment"),
                        red_flags=item.get("red_flags", []),
                        responded_at=item["responded_at"],
                    )
                )

            await session.commit()
            created.append(survey.id)
            return survey.id

    yield _make

    async with SessionFactory() as session:
        if created:
            await session.execute(delete(SurveyModel).where(SurveyModel.id.in_(created)))
        await session.commit()


@pytest_asyncio.fixture
async def login_as() -> AsyncIterator[Callable[..., Any]]:
    """Berilgan rol va `agent_id` bilan vaqtinchalik hisob ochib, kirgan
    klient qaytaradi. Hisob ham, klient ham test oxirida yopiladi.
    """
    created_users: list[uuid.UUID] = []
    opened: list[httpx.AsyncClient] = []

    async def _make(
        *,
        role: Role = Role.SALES,
        agent_id: uuid.UUID | None = None,
    ) -> httpx.AsyncClient:
        # ⚠️ `.local` / `.test` kabi zaxiralangan domenlar `EmailStr`
        # validatoridan o'tmaydi — kirish 422 bilan yiqilardi. Haqiqiy
        # domen + noyob prefiks; yozuv test oxirida o'chiriladi.
        email = f"{MARK}-{uuid.uuid4().hex[:10]}@zvonki.uz"

        async with SessionFactory() as session:
            user = UserModel(
                email=email,
                password_hash=hash_password(TEST_PASSWORD),
                full_name=f"{MARK} {role.value}",
                role=role,
                agent_id=agent_id,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            created_users.append(user.id)

        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        opened.append(client)

        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        return client

    yield _make

    for client in opened:
        await client.aclose()

    async with SessionFactory() as session:
        if created_users:
            await session.execute(
                delete(UserModel).where(UserModel.id.in_(created_users))
            )
        await session.commit()
