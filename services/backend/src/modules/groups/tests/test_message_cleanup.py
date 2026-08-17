"""Guruhdagi so'rovnoma xabarlarini o'chirish navbati.

⚠️ `expired_survey_messages()` — O'CHIRISHNING YAGONA MANBAI. Bot
guruhdagi xabarlarni umuman ko'rmaydi: u faqat shu ro'yxatdan kelgan
`(chat_id, message_id)` juftligini o'chiradi. Ro'yxatga ortiqcha yozuv
tushishi — begona xabarni o'chirishga urinish, tushmay qolishi esa
guruhda abadiy qoladigan xabar degani.

Hammasi COMMIT QILINMAYDIGAN sessiyada ishlaydi.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/groups -q
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.groups.application.services import GroupService
from src.modules.groups.tests.conftest import (
    MARK,
    build_agent,
    build_group,
    build_survey,
)
from src.modules.surveys.application.services import resolve_message_ttl_hours


async def _guruh_va_xodim(session):
    xodim = build_agent()
    session.add(xodim)
    await session.flush()
    guruh = build_group(agent_id=xodim.id, region=f"{MARK}-hudud")
    session.add(guruh)
    await session.flush()
    return xodim, guruh


@pytest.mark.asyncio
async def test_faqat_ttl_otgan_va_ochirilmagan_xabar_royxatga_tushadi(
    rollback_session, settings_guard
):
    """To'rt xil yozuv — faqat bittasi navbatga tushishi kerak."""
    await settings_guard("survey.message_ttl_hours", 24)
    session = rollback_session
    xodim, guruh = await _guruh_va_xodim(session)
    hozir = datetime.now(UTC)

    yangi = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=101,
        sent_at=hozir - timedelta(hours=1),  # TTL hali o'tmagan
    )
    eski = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=102,
        sent_at=hozir - timedelta(hours=30),  # TTL o'tgan
    )
    allaqachon_ochirilgan = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=103,
        sent_at=hozir - timedelta(hours=30),
        message_deleted_at=hozir - timedelta(hours=1),
    )
    yuborilmagan = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=None,  # bot hali guruhga tashlamagan
        sent_at=hozir - timedelta(hours=30),
    )
    session.add_all([yangi, eski, allaqachon_ochirilgan, yuborilmagan])
    await session.flush()

    royxat = await GroupService(session).expired_survey_messages()
    tokenlar = {row["token"] for row in royxat}

    assert eski.token in tokenlar
    assert yangi.token not in tokenlar
    assert allaqachon_ochirilgan.token not in tokenlar
    assert yuborilmagan.token not in tokenlar

    # Bot aynan shu juftlik bo'yicha o'chiradi — qiymatlar to'g'ri bo'lsin
    qator = next(row for row in royxat if row["token"] == eski.token)
    assert qator["chat_id"] == guruh.chat_id
    assert qator["chat_message_id"] == 102


@pytest.mark.asyncio
async def test_ochirilgan_deb_belgilangan_xabar_navbatdan_chiqadi(
    rollback_session, settings_guard
):
    """`mark_message_deleted` — idempotent va navbatni bo'shatadi.

    Bot o'chira olmagan holatda ham chaqiradi (Telegram 48 soatdan keyin
    ruxsat bermaydi), aks holda o'sha xabar har aylanishda qaytib kelib
    navbatni cheksiz to'ldirardi.
    """
    await settings_guard("survey.message_ttl_hours", 24)
    session = rollback_session
    xodim, guruh = await _guruh_va_xodim(session)

    sorovnoma = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=201,
        sent_at=datetime.now(UTC) - timedelta(hours=30),
    )
    session.add(sorovnoma)
    await session.flush()

    service = GroupService(session)
    assert sorovnoma.token in {
        row["token"] for row in await service.expired_survey_messages()
    }

    assert await service.mark_message_deleted(sorovnoma.token) == {"status": "ok"}
    birinchi_belgi = sorovnoma.message_deleted_at
    assert birinchi_belgi is not None

    # Ikkinchi chaqiruv hech narsani o'zgartirmaydi
    assert await service.mark_message_deleted(sorovnoma.token) == {"status": "ok"}
    assert sorovnoma.message_deleted_at == birinchi_belgi

    assert sorovnoma.token not in {
        row["token"] for row in await service.expired_survey_messages()
    }


@pytest.mark.asyncio
async def test_ttl_nol_bolsa_royxat_butunlay_bosh(rollback_session, settings_guard):
    """«Hech qachon o'chirilmasin» — navbat umuman yig'ilmaydi."""
    session = rollback_session
    xodim, guruh = await _guruh_va_xodim(session)
    sorovnoma = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=301,
        sent_at=datetime.now(UTC) - timedelta(days=30),  # juda eski
    )
    session.add(sorovnoma)
    await session.flush()

    service = GroupService(session)

    # Avval ishlayotganiga ishonch hosil qilamiz — bo'sh ro'yxat
    # «ma'lumot yo'q» sababli chiqmasin
    await settings_guard("survey.message_ttl_hours", 24)
    assert sorovnoma.token in {
        row["token"] for row in await service.expired_survey_messages()
    }

    await settings_guard("survey.message_ttl_hours", 0)
    assert await service.expired_survey_messages() == []


@pytest.mark.asyncio
async def test_48_dan_katta_qiymat_48_ga_tushiriladi(rollback_session, settings_guard):
    """Telegram botga o'z xabarini 48 soatdan keyin o'chirtirmaydi.

    Kattaroq qiymat jimgina 48 ga tushiriladi — aks holda admin
    «o'chadi» deb o'ylab turardi, xabar esa guruhda abadiy qolardi.
    """
    await settings_guard("survey.message_ttl_hours", 1000)
    session = rollback_session

    assert await resolve_message_ttl_hours(session) == 48

    xodim, guruh = await _guruh_va_xodim(session)
    hozir = datetime.now(UTC)
    ellik_soat = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=401,
        sent_at=hozir - timedelta(hours=50),
    )
    qirq_soat = build_survey(
        agent_id=xodim.id,
        group_id=guruh.id,
        chat_message_id=402,
        sent_at=hozir - timedelta(hours=40),
    )
    session.add_all([ellik_soat, qirq_soat])
    await session.flush()

    tokenlar = {
        row["token"] for row in await GroupService(session).expired_survey_messages()
    }
    # 1000 soat qo'llanganida ikkalasi ham tushmasdi, 24 soat qo'llanganida
    # ikkalasi ham tushardi — bu juftlik aynan 48 ni qotiradi
    assert ellik_soat.token in tokenlar
    assert qirq_soat.token not in tokenlar


@pytest.mark.asyncio
async def test_notogri_qiymatlar_xavfsiz_qiymatga_tushadi(
    rollback_session, settings_guard
):
    """Sozlamada axlat bo'lsa ham kod ishlashda davom etsin."""
    session = rollback_session

    await settings_guard("survey.message_ttl_hours", "salom")
    assert await resolve_message_ttl_hours(session) == 24  # standart qiymat

    await settings_guard("survey.message_ttl_hours", -5)
    assert await resolve_message_ttl_hours(session) == 0  # ya'ni «hech qachon»
