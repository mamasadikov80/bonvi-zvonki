"""So'rovnoma sozlamalarini O'QIYDIGAN funksiyalar.

`src/modules/surveys/application/services.py` dagi `resolve_*` oilasi.
Ular sozlamalar panelidagi qiymat bilan haqiqiy xatti-harakat orasidagi
YAGONA ko'prik. Ko'prik uzilsa hech qanday xato chiqmaydi: sozlama
saqlanadi, panelda ko'rinadi, lekin kod eski konstantani ishlatib
turaveradi — bu ilgari aynan shunday bo'lgan (izohlarga qarang).

Shu sababli har bir funksiya alohida tekshiriladi va faqat «to'g'ri
qiymat» emas, «axlat qiymat» ham beriladi: sozlama umumiy bazada,
unga qo'l bilan ham, eski migratsiya orqali ham tegib ketish mumkin.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.database import SessionFactory
from src.modules.surveys.application.services import (
    _as_bool,
    resolve_auto_send,
    resolve_message_ttl_hours,
    resolve_min_responses,
    resolve_period_days,
    resolve_suppression_days,
    resolve_survey_enabled,
)
from src.modules.surveys.domain.entities import (
    MIN_RESPONSES_FOR_RATING,
    SURVEY_MESSAGE_TTL_HOURS,
    SURVEY_PERIOD_DAYS,
    SURVEY_SUPPRESSION_DAYS,
    TELEGRAM_DELETE_LIMIT_HOURS,
)


async def _oqish(resolver):
    async with SessionFactory() as session:
        return await resolver(session)


# ══════════════════════════════════════════════════════════════
#  `_as_bool` — sof unit
#
#  Baza JSONB da haqiqiy `true`/`false` saqlaydi, `.env` esa matn
#  beradi. Ikkala manba ham shu funksiyadan o'tadi.
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "qiymat",
    [
        pytest.param(True, id="bool-true"),
        pytest.param("true", id="matn-true"),
        pytest.param("True", id="matn-True"),
        pytest.param("TRUE", id="matn-TRUE"),
        pytest.param("  true  ", id="matn-boshlari-bosh"),
        pytest.param("1", id="matn-1"),
        pytest.param("yes", id="matn-yes"),
        pytest.param("on", id="matn-on"),
        pytest.param("ha", id="ozbekcha-ha"),
        pytest.param(1, id="son-1"),
        pytest.param(42, id="son-42"),
        pytest.param(1.0, id="kasr-1.0"),
    ],
)
def test_as_bool_rost_deb_oqiydi(qiymat: Any) -> None:
    assert _as_bool(qiymat) is True


@pytest.mark.parametrize(
    "qiymat",
    [
        pytest.param(False, id="bool-false"),
        pytest.param("false", id="matn-false"),
        pytest.param("False", id="matn-False"),
        pytest.param("0", id="matn-0"),
        pytest.param("no", id="matn-no"),
        pytest.param("yoq", id="ozbekcha-yoq"),
        pytest.param("", id="bosh-matn"),
        pytest.param(None, id="none"),
        pytest.param(0, id="son-0"),
        pytest.param(0.0, id="kasr-0.0"),
        pytest.param("allaqanday-axlat", id="axlat"),
    ],
)
def test_as_bool_yolgon_deb_oqiydi(qiymat: Any) -> None:
    assert _as_bool(qiymat) is False


def test_as_bool_doim_haqiqiy_bool_qaytaradi() -> None:
    """`1` emas, `True`. Javob sxemalari qat'iy turga tayanadi."""
    for qiymat in (1, "true", 0, "", None, False):
        assert isinstance(_as_bool(qiymat), bool)


# ══════════════════════════════════════════════════════════════
#  `resolve_survey_enabled` — BOSH kalit
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("axlat", False),
    ],
    ids=lambda v: str(v),
)
async def test_sorovnoma_yoqilganmi(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.enabled", saqlangan)
    assert await _oqish(resolve_survey_enabled) is kutilgan


@pytest.mark.asyncio
async def test_sorovnoma_standart_holatda_ochiq(settings_guard) -> None:
    """Sozlama bo'sh bo'lsa — standart `False`. Pilot tugamaguncha yopiq."""
    await settings_guard("survey.enabled", "")
    assert await _oqish(resolve_survey_enabled) is False


# ══════════════════════════════════════════════════════════════
#  `resolve_auto_send` — avtomatik yuborish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [(True, True), (False, False), ("true", True), ("false", False), ("", False)],
    ids=lambda v: str(v),
)
async def test_avtomatik_yuborish(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.auto_send", saqlangan)
    assert await _oqish(resolve_auto_send) is kutilgan


@pytest.mark.asyncio
async def test_ikkala_bayroq_mustaqil(settings_guard) -> None:
    """`enabled` — «umuman mumkinmi», `auto_send` — «o'zi yuborsinmi».

    Ular bir-birini bosmasligi kerak: qo'lda yuborish yoqilgan, lekin
    avtomatik yuborish o'chiq — eng ko'p uchraydigan holat.
    """
    await settings_guard("survey.enabled", True)
    await settings_guard("survey.auto_send", False)

    assert await _oqish(resolve_survey_enabled) is True
    assert await _oqish(resolve_auto_send) is False


# ══════════════════════════════════════════════════════════════
#  `resolve_message_ttl_hours` — Telegram 48 soat chegarasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [
        pytest.param(0, 0, id="0-hech-qachon-ochirilmasin"),
        pytest.param(1, 1, id="1-soat"),
        pytest.param(24, 24, id="24-soat"),
        pytest.param(48, 48, id="48-aynan-chegara"),
        pytest.param(49, 48, id="49-chegaraga-tushiriladi"),
        pytest.param(999, 48, id="999-chegaraga-tushiriladi"),
        pytest.param(-5, 0, id="manfiy-0-deb-oqiladi"),
        pytest.param("36", 36, id="matn-son"),
    ],
)
async def test_xabar_muddati(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.message_ttl_hours", saqlangan)
    assert await _oqish(resolve_message_ttl_hours) == kutilgan


@pytest.mark.asyncio
async def test_xabar_muddati_chegarasi_48(settings_guard) -> None:
    """Telegram botga o'z xabarini 48 soatdan keyin o'chirishga ruxsat bermaydi.

    Kattaroq qiymat qabul qilinsa, admin «o'chadi» deb o'ylab turadi,
    xabar esa mijoz guruhida abadiy qolib ketadi.
    """
    await settings_guard("survey.message_ttl_hours", 10_000)
    assert await _oqish(resolve_message_ttl_hours) == TELEGRAM_DELETE_LIMIT_HOURS == 48


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "axlat", ["ertaga", "", None, "24 soat"], ids=lambda v: repr(v)
)
async def test_xabar_muddati_notogri_qiymatda_standartga_qaytadi(
    settings_guard, axlat
) -> None:
    await settings_guard("survey.message_ttl_hours", axlat)
    assert await _oqish(resolve_message_ttl_hours) == SURVEY_MESSAGE_TTL_HOURS == 24


# ══════════════════════════════════════════════════════════════
#  Kadans, tanaffus va minimal javob
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [
        pytest.param(7, 7, id="7-kun"),
        pytest.param(30, 30, id="30-kun"),
        pytest.param("21", 21, id="matn-son"),
        pytest.param(0, SURVEY_PERIOD_DAYS, id="0-standartga"),
        pytest.param(-3, SURVEY_PERIOD_DAYS, id="manfiy-standartga"),
        pytest.param("har hafta", SURVEY_PERIOD_DAYS, id="matn-standartga"),
        pytest.param(None, SURVEY_PERIOD_DAYS, id="bosh-standartga"),
    ],
)
async def test_kadans(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.period_days", saqlangan)
    assert await _oqish(resolve_period_days) == kutilgan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [
        pytest.param(3, 3, id="3-kun"),
        pytest.param(60, 60, id="60-kun"),
        pytest.param(0, SURVEY_SUPPRESSION_DAYS, id="0-standartga"),
        pytest.param(-1, SURVEY_SUPPRESSION_DAYS, id="manfiy-standartga"),
        pytest.param("yo'q", SURVEY_SUPPRESSION_DAYS, id="matn-standartga"),
    ],
)
async def test_takror_soramaslik_oynasi(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.suppression_days", saqlangan)
    assert await _oqish(resolve_suppression_days) == kutilgan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saqlangan", "kutilgan"),
    [
        pytest.param(1, 1, id="1-javob"),
        pytest.param(10, 10, id="10-javob"),
        pytest.param("3", 3, id="matn-son"),
        pytest.param(0, MIN_RESPONSES_FOR_RATING, id="0-standartga"),
        pytest.param(-2, MIN_RESPONSES_FOR_RATING, id="manfiy-standartga"),
        pytest.param("ko'p", MIN_RESPONSES_FOR_RATING, id="matn-standartga"),
    ],
)
async def test_minimal_javoblar_soni(settings_guard, saqlangan, kutilgan) -> None:
    await settings_guard("survey.min_responses", saqlangan)
    assert await _oqish(resolve_min_responses) == kutilgan


@pytest.mark.asyncio
async def test_standart_qiymatlar_reyestr_bilan_mos(settings_guard) -> None:
    """Kod konstantasi va reyestrdagi standart bir xil bo'lishi shart.

    Farq qilsa, sozlamaga tegilmagan tizim bilan sozlamasi «tozalangan»
    tizim boshqacha ishlab qolardi — buni tushuntirish qiyin bo'lardi.
    """
    from src.modules.settings.domain.entities import SETTINGS_BY_KEY

    assert SETTINGS_BY_KEY["survey.period_days"].default == SURVEY_PERIOD_DAYS
    assert SETTINGS_BY_KEY["survey.suppression_days"].default == SURVEY_SUPPRESSION_DAYS
    assert SETTINGS_BY_KEY["survey.min_responses"].default == MIN_RESPONSES_FOR_RATING
    assert (
        SETTINGS_BY_KEY["survey.message_ttl_hours"].default == SURVEY_MESSAGE_TTL_HOURS
    )
    assert SETTINGS_BY_KEY["survey.enabled"].default is False
    assert SETTINGS_BY_KEY["survey.auto_send"].default is False


@pytest.mark.asyncio
async def test_panelda_ozgartirilgan_qiymat_darhol_kuchga_kiradi(
    admin_client, settings_guard
) -> None:
    """Uchdan-uchgacha: admin `PUT /settings` qildi → o'quvchi yangisini oldi.

    Aynan shu zanjir ilgari uzilgan edi: sozlama saqlanardi, kod esa
    konstantani o'qib turaverardi.
    """
    from src.conftest import API

    await settings_guard("survey.period_days", 14)  # asl qiymat saqlab qo'yiladi

    response = await admin_client.put(
        f"{API}/settings", json={"values": {"survey.period_days": 9}}
    )
    assert response.status_code == 200, response.text

    assert await _oqish(resolve_period_days) == 9
