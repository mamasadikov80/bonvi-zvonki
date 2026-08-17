"""`GroupService.autobind` — avtomatik biriktirishning qat'iy qoidalari.

Bu qoidalar kodda ATAYLAB shunday yozilgan va ularning har biri bitta
haqiqiy nosozlikning oldini oladi. Shuning uchun ular test bilan
qotiriladi: keyinchalik kimdir «soddalashtiraman» deb o'zgartirsa,
sabab bilan qizil chiroq yonsin.

Hammasi COMMIT QILINMAYDIGAN sessiyada — bazada iz qolmaydi.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/groups -q
"""

from datetime import UTC, datetime

import pytest

from src.modules.groups.application.services import GroupService
from src.modules.groups.domain.entities import BindSource
from src.modules.groups.tests.conftest import (
    MARK,
    build_agent,
    build_group,
    telegram_user_id,
)


async def _royxatdan_otgan_xodim(session):
    """Botga kontaktini yuborgan (ya'ni `telegram_user_id` si bor) xodim."""
    agent = build_agent(
        telegram_user_id_=telegram_user_id(), enrolled_at=datetime.now(UTC)
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest.mark.asyncio
async def test_manual_biriktirilgan_guruhga_avtomatika_tegmaydi(rollback_session):
    """⚠️ Eng muhim qoida: odam qarori ustun.

    Admin qo'lda biriktirgan guruhni avtomatika qayta yozsa, admin
    tuzatgan narsa botning keyingi aylanishida yana buzilardi.
    """
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)
    boshqa_xodim = build_agent()
    session.add(boshqa_xodim)
    await session.flush()

    guruh = build_group(
        agent_id=boshqa_xodim.id,
        region=f"{MARK}-qolda-qoyilgan",
        bound_by=BindSource.MANUAL.value,
    )
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id,
        title=guruh.title,
        candidate_user_ids=[xodim.telegram_user_id],
    )

    assert natija["reason"] == "manual"
    assert natija["agent_id"] == boshqa_xodim.id  # o'zgarmadi
    assert natija["region"] == f"{MARK}-qolda-qoyilgan"
    assert natija["bound_by"] == BindSource.MANUAL.value

    await session.refresh(guruh)
    assert guruh.agent_id == boshqa_xodim.id
    assert guruh.bound_by == BindSource.MANUAL.value


@pytest.mark.asyncio
async def test_xodim_topilsa_biriktiriladi_va_bound_by_auto_boladi(rollback_session):
    """Nomzodlar orasidan ro'yxatdan o'tgan xodim topilsa — biriktiriladi."""
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)

    guruh = build_group()
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id,
        title=guruh.title,
        # Bot guruhda ko'rgan id lar: begonalar orasida bittasi xodimniki
        candidate_user_ids=[telegram_user_id(), xodim.telegram_user_id],
    )

    assert natija["reason"] == "matched"
    assert natija["agent_id"] == xodim.id
    assert natija["agent_name"] == xodim.full_name
    assert natija["bound"] is True
    assert natija["bound_by"] == BindSource.AUTO.value

    await session.refresh(guruh)
    assert guruh.agent_id == xodim.id
    assert guruh.bound_by == BindSource.AUTO.value


@pytest.mark.asyncio
async def test_xodimda_aynan_bitta_hudud_bolsa_osha_hudud_qoyiladi(rollback_session):
    """Hudud xodimning BIRIKTIRILGAN GURUHLARIDAN olinadi.

    ⚠️ `agents.region` ishlatilmaydi — u yashash joyi. Shu sababli
    xodimning `region` maydoni ataylab boshqa qiymatda.
    """
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)
    ishlaydigan_hudud = f"{MARK}-samarqand"

    eski_guruh = build_group(agent_id=xodim.id, region=ishlaydigan_hudud)
    yangi_guruh = build_group()
    session.add_all([eski_guruh, yangi_guruh])
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=yangi_guruh.chat_id,
        title=yangi_guruh.title,
        candidate_user_ids=[xodim.telegram_user_id],
    )

    assert natija["region"] == ishlaydigan_hudud
    assert natija["region"] != xodim.region  # `agents.region` EMAS

    await session.refresh(yangi_guruh)
    assert yangi_guruh.region == ishlaydigan_hudud
    assert yangi_guruh.bound_at is not None  # xodim + hudud → tayyor


@pytest.mark.asyncio
async def test_xodimda_ikkitadan_kop_hudud_bolsa_hudud_null_qoladi(rollback_session):
    """Noto'g'ri hudud — baho boshqa hududning hisobotiga tushib ketishi.

    Bo'sh hudud esa shunchaki adminni daraxtda kutib turadi, shuning
    uchun ikkilanish holatida hech narsa qo'yilmaydi.
    """
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)

    session.add_all(
        [
            build_group(agent_id=xodim.id, region=f"{MARK}-samarqand"),
            build_group(agent_id=xodim.id, region=f"{MARK}-buxoro"),
        ]
    )
    yangi_guruh = build_group()
    session.add(yangi_guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=yangi_guruh.chat_id,
        title=yangi_guruh.title,
        candidate_user_ids=[xodim.telegram_user_id],
    )

    assert natija["agent_id"] == xodim.id
    assert natija["region"] is None
    assert natija["bound"] is True  # xodim biriktirildi

    await session.refresh(yangi_guruh)
    assert yangi_guruh.region is None
    # Hududsiz guruh so'rovnomaga TAYYOR EMAS
    assert yangi_guruh.bound_at is None


@pytest.mark.asyncio
async def test_guruhda_hudud_bolsa_tegilmaydi(rollback_session):
    """Hudud qayerdandir kelgan — uni qayta o'ylash shart emas."""
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)
    mavjud_hudud = f"{MARK}-oldindan-qoyilgan"

    session.add(build_group(agent_id=xodim.id, region=f"{MARK}-yagona-hudud"))
    guruh = build_group(region=mavjud_hudud)
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id,
        title=guruh.title,
        candidate_user_ids=[xodim.telegram_user_id],
    )

    assert natija["agent_id"] == xodim.id  # xodim baribir biriktirildi
    assert natija["region"] == mavjud_hudud  # hudud esa tegilmadi

    await session.refresh(guruh)
    assert guruh.region == mavjud_hudud


@pytest.mark.asyncio
async def test_hech_kim_topilmasa_avval_biriktirilgan_xodim_uzilmaydi(rollback_session):
    """Bugun guruhda faqat mijoz yozgan bo'lishi mumkin.

    Bu «sotuvchi almashdi» degani emas — biriktirish saqlanib qoladi.
    """
    session = rollback_session
    xodim = await _royxatdan_otgan_xodim(session)
    guruh = build_group(
        agent_id=xodim.id,
        region=f"{MARK}-hudud",
        bound_by=BindSource.AUTO.value,
    )
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id,
        title=guruh.title,
        # Faqat begona id lar: ro'yxatdan o'tgan xodim yo'q
        candidate_user_ids=[telegram_user_id(), telegram_user_id()],
    )

    assert natija["reason"] == "matched"
    assert natija["agent_id"] == xodim.id
    assert natija["agent_name"] == xodim.full_name

    await session.refresh(guruh)
    assert guruh.agent_id == xodim.id


@pytest.mark.asyncio
async def test_xodimsiz_guruhda_hech_kim_topilmasa_no_agent(rollback_session):
    """Xodimi aniqlanmagan guruh daraxtdagi `unassigned` ga tushadi."""
    session = rollback_session
    guruh = build_group()
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id, title=guruh.title, candidate_user_ids=[]
    )

    assert natija["reason"] == "no_agent"
    assert natija["agent_id"] is None
    assert natija["bound"] is False


@pytest.mark.asyncio
async def test_faolsiz_xodim_nomzod_bolmaydi(rollback_session):
    """Ishdan ketgan xodimga yangi guruh biriktirilmaydi."""
    session = rollback_session
    xodim = build_agent(
        telegram_user_id_=telegram_user_id(),
        enrolled_at=datetime.now(UTC),
        is_active=False,
    )
    session.add(xodim)
    await session.flush()

    guruh = build_group()
    session.add(guruh)
    await session.flush()

    natija = await GroupService(session).autobind(
        chat_id=guruh.chat_id,
        title=guruh.title,
        candidate_user_ids=[xodim.telegram_user_id],
    )

    assert natija["reason"] == "no_agent"
    assert natija["agent_id"] is None
