"""Butun backend uchun umumiy test poydevori.

NEGA ALOHIDA MA'LUMOT TO'PLAMI KERAK
  Statistika testlari «o'rtacha ball 82.4 bo'lsin» deb yozilsa, ular
  bazadagi mavjud ma'lumotga bog'lanib qoladi: kimdir bitta qo'ng'iroq
  qo'shsa yoki demo tozalansa — testlar sababsiz qizarib ketadi.

  Shuning uchun har test O'ZIGA XOS xodim yaratadi, unga aniq ma'lum
  qiymatli qo'ng'iroq va baholarni yozadi, so'ng barcha tekshiruvni
  AYNAN O'SHA xodim bo'yicha filtrlab bajaradi. Kutilayotgan raqam
  test ichida qo'lda hisoblanadi, bazadagi boshqa ma'lumot esa
  natijaga umuman ta'sir qilmaydi.

  Test tugagach yaratilgan hamma narsa o'chiriladi (`ON DELETE CASCADE`
  qo'ng'iroq, baho va javoblarni o'zi olib ketadi).

IZOLYATSIYA CHEGARASI
  Bu testlar HAQIQIY dev bazasida ishlaydi — loyihada alohida test
  bazasi yo'q. Shuning uchun testlar hech qachon mavjud yozuvlarni
  o'zgartirmaydi yoki o'chirmaydi: faqat o'zi yaratganini tozalaydi.
  Sozlamaga tegadigan test uni oldin saqlab, keyin qaytaradi
  (`settings_guard`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import delete, select

from src.core import models as _models  # noqa: F401 — metadata to'liq bo'lsin
from src.core.database import SessionFactory, engine
from src.main import app
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.settings.infrastructure.models import SettingModel
from src.modules.surveys.domain.entities import (
    SurveyChannel,
    SurveyStatus,
    new_survey_token,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel

API = "http://test/api/v1"

ADMIN = ("admin@zvonki.uz", "admin12345")

#: Test yozuvlarini tanib olish uchun. Nomga qo'shiladi, tozalash ham
#: shu bo'yicha ketadi — qoldiq yozuv qolsa keyingi yurishda topiladi.
MARK = "pytest-fixture"


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Yurish oxirida qolib ketgan test yozuvlarini supurib tashlaydi.

    NEGA KERAK: fixture'lar o'zidan keyin tozalaydi, LEKIN test o'rtasida
    yiqilsa (masalan login 422 qaytarsa) tozalash kodigacha yetib
    bormaydi. O'shanda dev bazasida «pytest-fixture-…» nomli xodim va
    hisoblar qolib ketadi — ular admin panelida ko'rinadi va statistikaga
    qo'shiladi.

    Bu to'r FAQAT `MARK` prefiksli yozuvlarni o'chiradi. Haqiqiy
    ma'lumotga hech qanday sharoitda tegmaydi.
    """
    import asyncio

    async def _sweep() -> None:
        await engine.dispose()
        try:
            async with SessionFactory() as db:
                await db.execute(
                    delete(UserModel).where(UserModel.email.like(f"{MARK}%"))
                )
                await db.execute(
                    delete(TelegramGroupModel).where(
                        TelegramGroupModel.title.like(f"{MARK}%")
                    )
                )
                await db.execute(
                    delete(ClientModel).where(ClientModel.name.like(f"{MARK}%"))
                )
                # Xodim oxirida: qo'ng'iroq va so'rovnomalar kaskad bilan ketadi
                await db.execute(
                    delete(AgentModel).where(AgentModel.full_name.like(f"{MARK}%"))
                )
                await db.commit()
        finally:
            await engine.dispose()

    try:
        asyncio.run(_sweep())
    except Exception as exc:  # noqa: BLE001 — tozalash testni yiqitmasin
        print(f"\n⚠️  Test qoldiqlarini tozalab bo'lmadi: {exc}")


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool() -> AsyncIterator[None]:
    """`pytest-asyncio` har testga yangi loop beradi, pool esa eskisiga
    bog'langan ulanishlarni saqlab qoladi — shuning uchun bo'shatiladi."""
    await engine.dispose()
    yield
    await engine.dispose()


# ══════════════════════════════════════════════════════════════
#  HTTP klientlar
# ══════════════════════════════════════════════════════════════


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


@pytest_asyncio.fixture
async def admin_client() -> AsyncIterator[httpx.AsyncClient]:
    """Admin sifatida kirgan klient — haqiqiy ilova, haqiqiy JWT."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, *ADMIN)
        yield client


@pytest_asyncio.fixture
async def anon_client() -> AsyncIterator[httpx.AsyncClient]:
    """Tokensiz klient — himoya tekshiruvlari uchun."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ══════════════════════════════════════════════════════════════
#  Ma'lumot to'plami
# ══════════════════════════════════════════════════════════════


@dataclass(slots=True)
class SeededCall:
    """Yaratilgan bitta qo'ng'iroq — kutilayotgan qiymat test ichida ma'lum."""

    call_id: uuid.UUID
    started_at: datetime
    score: int
    duration_sec: int
    red_flags: int


@dataclass(slots=True)
class Dataset:
    """Bitta test uchun ajratilgan izolyatsiyalangan ma'lumot.

    Barcha tekshiruvlar `agent_id` bo'yicha filtrlanadi — bazadagi
    boshqa yozuvlar natijaga qo'shilmaydi.
    """

    agent_id: uuid.UUID
    agent_name: str
    region: str
    client_id: uuid.UUID | None = None
    calls: list[SeededCall] = field(default_factory=list)
    ratings: list[int] = field(default_factory=list)

    # ── Kutilayotgan qiymatlar (test ichida qo'lda hisoblanadi) ──

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def avg_score(self) -> float | None:
        if not self.calls:
            return None
        return sum(c.score for c in self.calls) / len(self.calls)

    @property
    def avg_duration(self) -> float | None:
        if not self.calls:
            return None
        return sum(c.duration_sec for c in self.calls) / len(self.calls)

    @property
    def calls_with_red_flags(self) -> int:
        return sum(1 for c in self.calls if c.red_flags > 0)

    @property
    def total_red_flags(self) -> int:
        return sum(c.red_flags for c in self.calls)

    @property
    def avg_rating(self) -> float | None:
        if not self.ratings:
            return None
        return sum(self.ratings) / len(self.ratings)


DatasetFactory = Callable[..., Any]


@pytest_asyncio.fixture
async def dataset() -> AsyncIterator[DatasetFactory]:
    """Izolyatsiyalangan ma'lumot yaratuvchi.

    Ishlatilishi::

        data = await dataset(
            scores=[90, 70, 50],          # har biri bitta qo'ng'iroq
            days_ago=[1, 2, 3],           # qachon bo'lgani
            ratings=[5, 4],               # client javoblari (1..5)
        )
        # keyin: /analytics/overview?agent_ids=<data.agent_id>

    Test tugagach xodim o'chiriladi, qolgani kaskad bilan ketadi.
    """
    created: list[uuid.UUID] = []
    created_clients: list[uuid.UUID] = []

    async def _make(
        *,
        scores: list[int] | None = None,
        days_ago: list[int] | None = None,
        durations: list[int] | None = None,
        red_flags: list[int] | None = None,
        ratings: list[int] | None = None,
        rating_days_ago: list[int] | None = None,
        region: str = "Toshkent",
        unscored_calls: int = 0,
    ) -> Dataset:
        scores = scores if scores is not None else []
        now = datetime.now(UTC)

        async with SessionFactory() as session:
            agent = AgentModel(
                full_name=f"{MARK}-{uuid.uuid4().hex[:8]}",
                region=region,
                is_active=True,
            )
            session.add(agent)
            await session.flush()
            created.append(agent.id)

            client = ClientModel(
                name=f"{MARK}-client",
                region=region,
                agent_id=agent.id,
                is_active=True,
            )
            session.add(client)
            await session.flush()
            created_clients.append(client.id)

            data = Dataset(
                agent_id=agent.id,
                agent_name=agent.full_name,
                region=region,
                client_id=client.id,
            )

            for index, score in enumerate(scores):
                offset = days_ago[index] if days_ago else index + 1
                duration = durations[index] if durations else 300
                flags = red_flags[index] if red_flags else 0
                started = now - timedelta(days=offset)

                call = CallModel(
                    external_id=f"{MARK}-{uuid.uuid4().hex}",
                    agent_id=agent.id,
                    client_id=client.id,
                    direction=CallDirection.OUTBOUND,
                    status=CallStatus.COMPLETED,
                    started_at=started,
                    duration_sec=duration,
                )
                session.add(call)
                await session.flush()

                session.add(
                    CallScoreModel(
                        call_id=call.id,
                        model="test-model",
                        rubric_version="v1",
                        overall_score=score,
                        blocks={"script": 25, "communication": 25},
                        red_flags=[
                            {"type": "shouting", "severity": "high"}
                            for _ in range(flags)
                        ],
                        confidence=0.9,
                        needs_review=False,
                        scored_at=started + timedelta(hours=1),
                    )
                )
                data.calls.append(
                    SeededCall(
                        call_id=call.id,
                        started_at=started,
                        score=score,
                        duration_sec=duration,
                        red_flags=flags,
                    )
                )

            # Bahosi YO'Q qo'ng'iroqlar — «baholangan» va «jami» farqini
            # tekshirish uchun. Ular `data.calls` ga KIRMAYDI.
            for _ in range(unscored_calls):
                session.add(
                    CallModel(
                        external_id=f"{MARK}-{uuid.uuid4().hex}",
                        agent_id=agent.id,
                        client_id=client.id,
                        direction=CallDirection.OUTBOUND,
                        status=CallStatus.COMPLETED,
                        started_at=now - timedelta(days=1),
                        duration_sec=100,
                    )
                )

            # ── Client javoblari ──────────────────────────────
            for index, csat in enumerate(ratings or []):
                offset = (
                    rating_days_ago[index] if rating_days_ago else index + 1
                )
                responded = now - timedelta(days=offset)
                survey = SurveyModel(
                    client_id=client.id,
                    agent_id=agent.id,
                    token=new_survey_token(),
                    period_start=responded - timedelta(days=14),
                    period_end=responded,
                    channel=SurveyChannel.TELEGRAM_GROUP,
                    status=SurveyStatus.COMPLETED,
                    sent_at=responded - timedelta(hours=1),
                    expires_at=responded + timedelta(days=7),
                    response_count=1,
                )
                session.add(survey)
                await session.flush()
                session.add(
                    SurveyResponseModel(
                        survey_id=survey.id,
                        respondent_hash=uuid.uuid4().hex,
                        csat=csat,
                        responded_at=responded,
                    )
                )
                data.ratings.append(csat)

            await session.commit()
            return data

    yield _make

    # ── Tozalash ──────────────────────────────────────────────
    async with SessionFactory() as session:
        if created:
            # Xodim o'chsa qo'ng'iroq, baho, so'rovnoma va javob kaskad
            # bilan ketadi; client `SET NULL` bo'lgani uchun alohida.
            await session.execute(delete(AgentModel).where(AgentModel.id.in_(created)))
        if created_clients:
            await session.execute(
                delete(ClientModel).where(ClientModel.id.in_(created_clients))
            )
        await session.commit()


@pytest_asyncio.fixture
async def group_factory() -> AsyncIterator[Callable[..., Any]]:
    """Xodimga Telegram guruhlarini biriktiradi.

    `regions` ro'yxatidagi har bir element uchun bitta guruh yaratiladi;
    `None` — hududi biriktirilmagan guruh (bu XATO emas, «hali
    saralanmagan» degan holat).

    `chat_id` manfiy va noyob — haqiqiy supergroup identifikatorlari
    bilan to'qnashmasligi uchun.
    """
    created: list[uuid.UUID] = []

    async def _make(agent_id: uuid.UUID, *, regions: list[str | None]):
        async with SessionFactory() as session:
            ids: list[uuid.UUID] = []
            for index, region in enumerate(regions):
                group = TelegramGroupModel(
                    # `uuid4().int` dan olingan katta manfiy son —
                    # takrorlanish ehtimoli amalda nolga teng
                    chat_id=-(10**12) - (uuid.uuid4().int % 10**9) - index,
                    title=f"{MARK}-group-{index}",
                    agent_id=agent_id,
                    region=region,
                    is_active=True,
                )
                session.add(group)
                await session.flush()
                ids.append(group.id)
                created.append(group.id)
            await session.commit()
            return ids

    yield _make

    async with SessionFactory() as session:
        if created:
            await session.execute(
                delete(TelegramGroupModel).where(TelegramGroupModel.id.in_(created))
            )
        await session.commit()


@pytest_asyncio.fixture
async def sales_client(dataset: DatasetFactory) -> AsyncIterator[tuple]:
    """Savdo xodimi hisobi + o'ziga tegishli ma'lumot.

    Rol doirasini tekshirish uchun: bu hisob FAQAT o'z xodimining
    ma'lumotini ko'rishi kerak.
    """
    data = await dataset(scores=[80, 60], ratings=[5, 3])
    # ⚠️ `.local` / `.test` kabi zaxiralangan domenlar `EmailStr`
    # validatoridan o'tmaydi. Haqiqiy domen + noyob prefiks ishlatiladi;
    # yozuv test oxirida o'chiriladi.
    email = f"{MARK}-{uuid.uuid4().hex[:8]}@zvonki.uz"
    password = "pytest-secret-123"

    from src.core.security import hash_password

    async with SessionFactory() as session:
        user = UserModel(
            email=email,
            password_hash=hash_password(password),
            full_name=f"{MARK} sales",
            role=Role.SALES,
            agent_id=data.agent_id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, email, password)
        yield client, data

    async with SessionFactory() as session:
        await session.execute(delete(UserModel).where(UserModel.id == user_id))
        await session.commit()


@pytest_asyncio.fixture
async def settings_guard() -> AsyncIterator[Callable[[str, Any], Any]]:
    """Sozlamani vaqtincha o'zgartiradi va test oxirida QAYTARADI.

    Sozlamalar dev bazasida umumiy — test ularni o'zgartirib qoldirsa,
    keyingi testlar ham, ishlatuvchi ham buzilgan holatga tushadi.
    """
    touched: dict[str, Any] = {}

    async def _set(key: str, value: Any) -> None:
        async with SessionFactory() as session:
            row = (
                await session.execute(
                    select(SettingModel).where(SettingModel.key == key)
                )
            ).scalar_one_or_none()

            if key not in touched:
                touched[key] = dict(row.value) if row is not None else None

            if row is None:
                session.add(
                    SettingModel(key=key, category=key.split(".")[0], value={"v": value})
                )
            else:
                row.value = {"v": value}
            await session.commit()

    yield _set

    async with SessionFactory() as session:
        for key, previous in touched.items():
            row = (
                await session.execute(
                    select(SettingModel).where(SettingModel.key == key)
                )
            ).scalar_one_or_none()
            if previous is None:
                if row is not None:
                    await session.delete(row)
            elif row is None:
                session.add(
                    SettingModel(key=key, category=key.split(".")[0], value=previous)
                )
            else:
                row.value = previous
        await session.commit()
