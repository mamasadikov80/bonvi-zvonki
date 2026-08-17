"""`calls` moduli testlariga xos qo'shimcha poydevor.

Umumiy fixture'lar `src/conftest.py` da yashaydi: `admin_client`,
`anon_client`, `sales_client`, `dataset`, `settings_guard`. Bu yerda
faqat qo'ng'iroqlar ro'yxatini tekshirish uchun kerak bo'lgani bor.

NEGA `db` KERAK
  `dataset` fixture'i barcha qo'ng'iroqni BITTA client va BITTA holat
  bilan yaratadi. Saralashni tekshirish uchun esa ustunda har xil
  qiymat bo'lishi shart: hamma qatorda bir xil nom tursa, `sort=client`
  har qanday tartibda «to'g'ri» ko'rinadi va test hech narsani
  isbotlamaydi. `db` ana shu farqni FAQAT o'zimiz yaratgan yozuvlarga
  qo'shadi.

TOZALASH
  `db` o'zi qo'shgan clientlarni test oxirida o'chiradi; mavjud
  qatorlarni esa umuman qo'zg'atmaydi — u faqat `dataset` bergan
  identifikatorlar bo'yicha ishlaydi.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import delete, update

from src.core.database import SessionFactory
from src.main import app
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.scoring.infrastructure.models import CallScoreModel

API = "http://test/api/v1"

#: Seed'dan keladigan hisoblar (`src/seed.py:280-285`).
#: VIEWER ruxsatlari faqat `analytics:read` va `regions:read` —
#: `calls:read` unda YO'Q.
VIEWER = ("viewer@zvonki.uz", "viewer12345")
MANAGER = ("manager@zvonki.uz", "manager12345")


async def _rol_klienti(email: str, password: str) -> AsyncIterator[httpx.AsyncClient]:
    """Berilgan hisob ostida kirgan klient — haqiqiy ilova, haqiqiy JWT."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"{API}/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


@pytest_asyncio.fixture
async def viewer_client() -> AsyncIterator[httpx.AsyncClient]:
    """VIEWER roli — savdo xonasidagi monitor uchun cheklangan ko'rinish."""
    async for client in _rol_klienti(*VIEWER):
        yield client


@pytest_asyncio.fixture
async def manager_client() -> AsyncIterator[httpx.AsyncClient]:
    """MANAGER roli — `calls:read` ruxsati BOR, nazorat testi uchun."""
    async for client in _rol_klienti(*MANAGER):
        yield client


class DbTweak:
    """Test O'ZI yaratgan yozuvlarni bazada nozik o'zgartiradi.

    Har bir metod aniq identifikator talab qiladi — ommaviy `UPDATE`
    yo'q, shuning uchun begona yozuvga tegib ketish imkoni yo'q.
    """

    def __init__(self) -> None:
        self.created_clients: list[uuid.UUID] = []

    @staticmethod
    async def _apply(model: Any, column: Any, key: Any, values: dict[str, Any]) -> None:
        async with SessionFactory() as session:
            await session.execute(update(model).where(column == key).values(**values))
            await session.commit()

    async def call(self, call_id: uuid.UUID, **values: Any) -> None:
        await self._apply(CallModel, CallModel.id, call_id, values)

    async def score(self, call_id: uuid.UUID, **values: Any) -> None:
        """Baho qatori `call_id` bo'yicha topiladi (u UNIQUE)."""
        await self._apply(CallScoreModel, CallScoreModel.call_id, call_id, values)

    async def agent(self, agent_id: uuid.UUID, **values: Any) -> None:
        await self._apply(AgentModel, AgentModel.id, agent_id, values)

    async def client(self, client_id: uuid.UUID, **values: Any) -> None:
        await self._apply(ClientModel, ClientModel.id, client_id, values)

    async def new_client(
        self,
        name: str,
        *,
        region: str = "Toshkent",
        agent_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Qo'shimcha client yaratadi — masalan `sort=client` uchun."""
        async with SessionFactory() as session:
            row = ClientModel(
                name=name, region=region, agent_id=agent_id, is_active=True
            )
            session.add(row)
            await session.commit()
            self.created_clients.append(row.id)
            return row.id


@pytest_asyncio.fixture
async def db() -> AsyncIterator[DbTweak]:
    tweak = DbTweak()
    yield tweak

    if tweak.created_clients:
        async with SessionFactory() as session:
            await session.execute(
                delete(ClientModel).where(ClientModel.id.in_(tweak.created_clients))
            )
            await session.commit()
