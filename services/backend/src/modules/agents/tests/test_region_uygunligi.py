"""Xodim profilidagi hudud = Telegram guruhlari bo'limidagi hudud.

MUAMMO TARIXI: tizimda hudud ikki xil ma'noda saqlanadi —
`agents.region` (xodim YASHAYDIGAN joy) va `telegram_groups.region`
(u XIZMAT KO'RSATADIGAN hudud). Profil sahifasi birinchisini,
guruhlar daraxti ikkinchisini ko'rsatardi. Natijada bitta xodim
ikki ekranda ikki xil hududda «yashardi»: profilda «Farg'ona
vodiysi», guruhlar bo'limida «Samarqand».

Endi ikkalasi ham `groups/application/agent_regions.py` dagi
YAGONA qoidadan oziqlanadi. Bu testlar o'sha bog'lanishni qotiradi:
kimdir bir tomonini o'zgartirsa, ikkinchisi bilan farqi darhol
ko'rinadi.
"""

import pytest

from src.core.database import SessionFactory
from src.modules.agents.application.services import AgentService
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.groups.application.services import GroupService
from src.modules.groups.infrastructure.models import TelegramGroupModel


async def _ikkala_taraf(agent_id) -> tuple[list[str], list[str]]:
    """`(profil hududlari, daraxt hududlari)` — bir xil bo'lishi shart."""
    async with SessionFactory() as session:
        agent = await session.get(AgentModel, agent_id)
        profil = (await AgentService(session).serialize(agent))["regions"]

        tree = await GroupService(session).tree()
        node = next(
            (a for a in tree["agents"] if a["agent_id"] == agent_id), None
        )
        daraxt = sorted(
            r["region"]
            for r in (node["regions"] if node else [])
            if r["region"] is not None
        )
        return profil, daraxt


@pytest.mark.asyncio
async def test_bitta_hududda_ikkala_taraf_mos(dataset, group_factory) -> None:
    data = await dataset(scores=[80])
    await group_factory(data.agent_id, regions=["Toshkent"])

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == ["Toshkent"]


@pytest.mark.asyncio
async def test_bir_nechta_hududda_hammasi_ikkala_tarafda(
    dataset, group_factory
) -> None:
    """Foydalanuvchi so'ragan asosiy holat: Toshkent + Buxoro."""
    data = await dataset(scores=[80])
    await group_factory(data.agent_id, regions=["Toshkent", "Buxoro"])

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == ["Buxoro", "Toshkent"]


@pytest.mark.asyncio
async def test_yashash_joyi_xizmat_hududiga_qoshilmaydi(
    dataset, group_factory
) -> None:
    """`agents.region` — boshqa narsa, ro'yxatga TUSHMASLIGI kerak.

    Toshkentda yashab Samarqandga xizmat ko'rsatuvchi xodim ikkala
    ekranda ham faqat «Samarqand» bo'lib ko'rinishi kerak.
    """
    data = await dataset(scores=[80], region="Toshkent")
    await group_factory(data.agent_id, regions=["Samarqand"])

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == ["Samarqand"]
    assert "Toshkent" not in profil


@pytest.mark.asyncio
async def test_faolsiz_guruh_ikkala_tarafdan_ham_tushadi(
    dataset, group_factory
) -> None:
    """O'chirilgan guruhga xizmat ko'rsatilmaydi — hudud ham hisoblanmaydi."""
    data = await dataset(scores=[80])
    groups = await group_factory(data.agent_id, regions=["Toshkent", "Buxoro"])

    async with SessionFactory() as session:
        group = await session.get(TelegramGroupModel, groups[1])
        group.is_active = False
        await session.commit()

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == ["Toshkent"]


@pytest.mark.asyncio
async def test_hududsiz_guruh_ikkala_tarafda_ham_hisoblanmaydi(
    dataset, group_factory
) -> None:
    """Hududi yo'q guruh — «hali saralanmagan», hudud emas."""
    data = await dataset(scores=[80])
    await group_factory(data.agent_id, regions=[None])

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == []


@pytest.mark.asyncio
async def test_guruhsiz_xodimda_ikkala_taraf_ham_bosh(dataset) -> None:
    """Guruhi yo'q xodim — profil ham bo'sh ko'rsatishi kerak.

    Ilgari bu yerda `agents.region` chiqib turardi va admin xodimni
    biror hududga biriktirilgan deb o'ylardi.
    """
    data = await dataset(scores=[80], region="Xorazm")

    profil, daraxt = await _ikkala_taraf(data.agent_id)

    assert profil == daraxt == []


@pytest.mark.asyncio
async def test_api_javobida_ikkala_maydon_ham_bor(
    admin_client, dataset, group_factory
) -> None:
    """`GET /agents` — `region` (yashash) va `regions` (xizmat) alohida."""
    data = await dataset(scores=[80], region="Xorazm")
    await group_factory(data.agent_id, regions=["Buxoro"])

    response = await admin_client.get("/api/v1/agents")
    assert response.status_code == 200, response.text

    row = next(a for a in response.json() if a["id"] == str(data.agent_id))
    assert row["region"] == "Xorazm"
    assert row["regions"] == ["Buxoro"]


@pytest.mark.asyncio
async def test_royxat_va_bitta_xodim_bir_xil_javob_beradi(
    admin_client, dataset, group_factory
) -> None:
    """Ro'yxat `GROUP BY` bilan, bitta xodim alohida so'rov bilan
    hisoblaydi — ikkala yo'l bir xil natija berishi shart."""
    data = await dataset(scores=[80])
    await group_factory(data.agent_id, regions=["Toshkent", "Buxoro"])

    royxat = (await admin_client.get("/api/v1/agents")).json()
    bitta = (await admin_client.get(f"/api/v1/agents/{data.agent_id}")).json()

    row = next(a for a in royxat if a["id"] == str(data.agent_id))
    assert row["regions"] == bitta["regions"] == ["Buxoro", "Toshkent"]
