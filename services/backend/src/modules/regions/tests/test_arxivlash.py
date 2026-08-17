"""Hududni arxivlash — tarix saqlanadi, kelajak uziladi.

MUAMMO TARIXI. Hisobot hududni TIRIK `telegram_groups.region` dan
o'qirdi. Shuning uchun hududni guruhdan uzish o'tgan oylarning
bahosini hisobotdan JIMGINA o'chirib yuborardi: o'lchov o'zgargani
uchun tarix ham o'zgarardi. O'lchangan edi — 8 ta bahodan 5 tasi
yo'qolardi.

Endi har so'rovnoma yaratilgan lahzadagi hudud NUSXASINI saqlaydi
(`surveys.region`), shuning uchun uzish faqat KELAJAKKA ta'sir qiladi.

Bu testlar aynan shu kafolatni qo'riqlaydi.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.database import SessionFactory
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.infrastructure.models import RegionModel
from src.modules.surveys.domain.entities import (
    SurveyChannel,
    SurveyStatus,
    new_survey_token,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel

API = "/api/v1/regions"
MARK = "pytest-fixture"


@pytest.fixture
def region_name() -> str:
    return f"{MARK}-hudud-{uuid.uuid4().hex[:6]}"


async def _create_region(client, name: str) -> str:
    response = await client.post(API, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _survey_with_response(agent_id, group_id, region: str, csat: int) -> None:
    """Hudud nusxasi bilan so'rovnoma + javob yozadi."""
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        survey = SurveyModel(
            agent_id=agent_id,
            group_id=group_id,
            region=region,
            token=new_survey_token(),
            period_start=now - timedelta(days=14),
            period_end=now,
            channel=SurveyChannel.TELEGRAM_GROUP,
            status=SurveyStatus.COMPLETED,
            sent_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=7),
        )
        session.add(survey)
        await session.flush()
        session.add(
            SurveyResponseModel(
                survey_id=survey.id,
                respondent_hash=uuid.uuid4().hex,
                csat=csat,
                responded_at=now - timedelta(hours=1),
            )
        )
        await session.commit()


async def _cleanup_region(name: str) -> None:
    async with SessionFactory() as session:
        row = (
            await session.execute(select(RegionModel).where(RegionModel.name == name))
        ).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
            await session.commit()


@pytest.mark.asyncio
async def test_arxivlash_tarixni_yoqotmaydi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """ENG MUHIM TEST: uzilgandan keyin ham o'tgan baholar hisobotda."""
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name])
        await _survey_with_response(data.agent_id, groups[0], region_name, 5)

        oldin = (
            await admin_client.get(
                "/api/v1/surveys", params={"days": 30, "region": region_name}
            )
        ).json()
        assert oldin["count"] == 1

        response = await admin_client.patch(
            f"{API}/{region_id}",
            json={"is_active": False, "detach_groups": True},
        )
        assert response.status_code == 200, response.text
        assert response.json()["detached_groups"] == 1

        keyin = (
            await admin_client.get(
                "/api/v1/surveys", params={"days": 30, "region": region_name}
            )
        ).json()
        # Tarix O'ZGARMAYDI — nusxa saqlangani uchun
        assert keyin["count"] == 1
        assert keyin["average"] == oldin["average"]
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_arxivlash_faol_guruhni_uzadi(
    admin_client, dataset, group_factory, region_name
) -> None:
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name])

        await admin_client.patch(
            f"{API}/{region_id}", json={"is_active": False, "detach_groups": True}
        )

        async with SessionFactory() as session:
            group = await session.get(TelegramGroupModel, groups[0])
            assert group.region is None
            # Guruh o'zi qoladi — faqat bog'lanish uziladi
            assert group.is_active is True
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_maydonsiz_ham_uziladi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """STANDART xatti-harakat: arxivlash guruhni uzadi.

    ⚠️ Qoida SERVERDA turishi shart. Ilgari standart «uzmaslik» edi va
    qaror klient tomonida qolardi: admin hududni o'chirardi, guruhlar
    esa eski hududda qolib so'rovnoma olishda davom etardi. Eski
    keshlangan sahifa yoki boshqa API klienti maydonni yubormasa,
    natija jimgina boshqacha bo'lardi.

    Shuning uchun bu test `detach_groups` ni ATAYLAB yubormaydi.
    """
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name])

        response = await admin_client.patch(
            f"{API}/{region_id}", json={"is_active": False}
        )
        assert response.json()["detached_groups"] == 1

        async with SessionFactory() as session:
            group = await session.get(TelegramGroupModel, groups[0])
            assert group.region is None
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_ataylab_soralsa_guruh_hududida_qoladi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """`detach_groups: false` — guruhlar eski hududda qoladi.

    Bu chekinish yo'li: hudud ro'yxatdan olib tashlansa-yu, guruhlar
    hali ko'chirilmagan bo'lsa, admin ularni o'z joyida qoldirib
    keyinroq qo'lda taqsimlashi mumkin.
    """
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name])

        response = await admin_client.patch(
            f"{API}/{region_id}",
            json={"is_active": False, "detach_groups": False},
        )
        assert response.json()["detached_groups"] == 0

        async with SessionFactory() as session:
            group = await session.get(TelegramGroupModel, groups[0])
            assert group.region == region_name
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_faolsiz_guruhga_tegilmaydi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """Faolsiz guruh allaqachon ishlamayapti — hududini o'chirish
    tarixdagi izni yo'qotardi."""
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name, region_name])

        async with SessionFactory() as session:
            group = await session.get(TelegramGroupModel, groups[1])
            group.is_active = False
            await session.commit()

        response = await admin_client.patch(
            f"{API}/{region_id}", json={"is_active": False, "detach_groups": True}
        )
        assert response.json()["detached_groups"] == 1

        async with SessionFactory() as session:
            faolsiz = await session.get(TelegramGroupModel, groups[1])
            assert faolsiz.region == region_name
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_arxiv_korinishi_aniq_son_beradi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """Admin tugmani bosishdan OLDIN nima to'xtashini bilishi kerak."""
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        await group_factory(data.agent_id, regions=[region_name, region_name])

        response = await admin_client.get(f"{API}/{region_id}/archive-preview")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["region"] == region_name
        assert body["active_groups"] == 2
    finally:
        await _cleanup_region(region_name)


@pytest.mark.asyncio
async def test_qayta_faollashtirish_guruhni_tiklamaydi(
    admin_client, dataset, group_factory, region_name
) -> None:
    """Uzish — qaytarib bo'lmaydigan amal, va bu OCHIQ aytilgan.

    Hududni qayta yoqish guruhlarni o'z-o'zidan qaytarmaydi: admin
    ularni qo'lda biriktiradi. Test shu kutilmani qotiradi, aks holda
    kimdir «qayta yoqsam tiklanadi» deb o'ylashi mumkin.
    """
    region_id = await _create_region(admin_client, region_name)
    try:
        data = await dataset(scores=[80])
        groups = await group_factory(data.agent_id, regions=[region_name])

        await admin_client.patch(
            f"{API}/{region_id}", json={"is_active": False, "detach_groups": True}
        )
        await admin_client.patch(f"{API}/{region_id}", json={"is_active": True})

        async with SessionFactory() as session:
            group = await session.get(TelegramGroupModel, groups[0])
            assert group.region is None
    finally:
        await _cleanup_region(region_name)
