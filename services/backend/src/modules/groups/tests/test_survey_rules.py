"""So'rovnoma yaratish qoidalari: bosh kalit, biriktirish, takrorlanish.

IKKI XIL YO'L, BITTA QOIDA TO'PLAMI

  Endpoint testlari (`POST /groups/{id}/survey`) haqiqiy yozuv
  qoldiradi — ular O'ZIMIZ yaratgan guruh ustida ishlaydi va test
  oxirida guruh o'chadi (so'rovnomalar kaskad bilan ketadi).

  Ommaviy yuborish (`broadcast_surveys`) esa BAZADAGI HAR BIR guruhga
  tegadi — uni commit bilan sinash ishlatuvchining guruhlariga
  so'rovnoma navbatga tashlash demak. Shuning uchun u faqat
  `rollback_session` ichida, servis darajasida tekshiriladi.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/groups -q
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.core.database import SessionFactory
from src.modules.groups.application.services import GroupService
from src.modules.groups.tests.conftest import (
    API,
    MARK,
    build_agent,
    build_group,
    survey_count,
)
from src.modules.surveys.domain.entities import SurveyStatus
from src.modules.surveys.infrastructure.models import SurveyModel


def _skipped_reasons(natija: dict) -> dict:
    """`{guruh_id: sabab}` — o'zimiznikini tez topish uchun."""
    return {row["group_id"]: row["reason"] for row in natija["skipped"]}


# ══════════════════════════════════════════════════════════════
#  1. Bosh kalit: `survey.enabled`
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sorovnoma_ochirilgan_bolsa_ikkala_yol_ham_409(
    admin_client, seed, settings_guard
):
    """⚠️ Tekshiruv yaratishning IKKALA yo'lida ham turishi shart.

    Bittasida bo'lsa ikkinchisi teshik bo'lib qolardi: admin
    «yuborish o'chirilgan» deb turib tugmani bossa, so'rovnoma
    haqiqiy mijoz guruhiga ketardi.
    """
    await settings_guard("survey.enabled", False)

    xodim = await seed.agent()
    guruh = await seed.group(agent_id=xodim.id, region=f"{MARK}-hudud")

    bitta = await admin_client.post(
        f"{API}/groups/{guruh.id}/survey", json={"force": True}
    )
    assert bitta.status_code == 409, bitta.text
    assert bitta.json()["error"]["code"] == "survey_disabled"

    ommaviy = await admin_client.post(
        f"{API}/groups/surveys/broadcast", json={"force": True}
    )
    assert ommaviy.status_code == 409, ommaviy.text
    assert ommaviy.json()["error"]["code"] == "survey_disabled"

    # Hech narsa yaratilmadi — na bizning guruhga, na boshqasiga
    async with SessionFactory() as session:
        assert await survey_count(session, guruh.id) == 0


# ══════════════════════════════════════════════════════════════
#  2. Tuzilmaviy to'siq: biriktirilmagan guruh
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_biriktirilmagan_guruhga_sorovnoma_yaratilmaydi(
    admin_client, seed, settings_guard
):
    """Xodimsiz — bahoni kimga yozishni bilmaymiz.
    Hududsiz — guruh ishchi guruh emas (admin uni «keraksiz» deb belgilagan).

    `force=True` ham yordam bermaydi: tuzilmaviy qoidalarni chetlab
    bo'lmaydi, ular vaqtga oid emas.
    """
    await settings_guard("survey.enabled", True)

    xodim = await seed.agent()
    hududsiz = await seed.group(agent_id=xodim.id, region=None)
    xodimsiz = await seed.group(agent_id=None, region=f"{MARK}-hudud")
    faolsiz = await seed.group(
        agent_id=xodim.id, region=f"{MARK}-hudud", is_active=False
    )

    for guruh, kutilgan_kod in (
        (hududsiz, "group_not_bound"),
        (xodimsiz, "group_not_bound"),
        (faolsiz, "group_inactive"),
    ):
        response = await admin_client.post(
            f"{API}/groups/{guruh.id}/survey", json={"force": True}
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == kutilgan_kod

    async with SessionFactory() as session:
        for guruh in (hududsiz, xodimsiz, faolsiz):
            assert await survey_count(session, guruh.id) == 0


# ══════════════════════════════════════════════════════════════
#  3. Navbatda turgan so'rovnoma
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_navbatdagi_sorovnoma_bolsa_yangisi_yaratilmaydi(
    admin_client, seed, settings_guard
):
    """Aks holda guruhga ikkita bir xil xabar tushardi."""
    await settings_guard("survey.enabled", True)

    xodim = await seed.agent()
    guruh = await seed.group(agent_id=xodim.id, region=f"{MARK}-hudud")

    birinchi = await admin_client.post(
        f"{API}/groups/{guruh.id}/survey", json={"force": True}
    )
    assert birinchi.status_code == 201, birinchi.text
    assert birinchi.json()["reused"] is False

    ikkinchi = await admin_client.post(
        f"{API}/groups/{guruh.id}/survey", json={"force": True}
    )
    assert ikkinchi.status_code == 201, ikkinchi.text
    assert ikkinchi.json()["reused"] is True
    # AYNAN o'sha so'rovnoma qaytadi — bot ikkinchi xabar yubormaydi
    assert ikkinchi.json()["token"] == birinchi.json()["token"]
    assert ikkinchi.json()["survey_id"] == birinchi.json()["survey_id"]

    async with SessionFactory() as session:
        assert await survey_count(session, guruh.id) == 1


@pytest.mark.asyncio
async def test_suppression_oynasi_forcesiz_ishlaydi_force_bilan_chetlanadi(
    admin_client, seed, settings_guard
):
    """Vaqtga oid to'siq — tuzilmaviydan farqli, admin uni chetlab o'tadi."""
    await settings_guard("survey.enabled", True)
    await settings_guard("survey.suppression_days", 10)

    xodim = await seed.agent()
    guruh = await seed.group(
        agent_id=xodim.id,
        region=f"{MARK}-hudud",
        last_survey_at=datetime.now(UTC) - timedelta(days=2),
    )

    tosiq = await admin_client.post(
        f"{API}/groups/{guruh.id}/survey", json={"force": False}
    )
    assert tosiq.status_code == 409, tosiq.text
    assert tosiq.json()["error"]["code"] == "survey_suppressed"

    async with SessionFactory() as session:
        assert await survey_count(session, guruh.id) == 0

    majburiy = await admin_client.post(
        f"{API}/groups/{guruh.id}/survey", json={"force": True}
    )
    assert majburiy.status_code == 201, majburiy.text
    assert majburiy.json()["reused"] is False

    async with SessionFactory() as session:
        assert await survey_count(session, guruh.id) == 1


# ══════════════════════════════════════════════════════════════
#  4. Ommaviy yuborish — faqat rollback sessiyada
# ══════════════════════════════════════════════════════════════


async def _biriktirilgan_guruh(session, xodim_id, **kwargs):
    guruh = build_group(agent_id=xodim_id, region=f"{MARK}-hudud", **kwargs)
    session.add(guruh)
    await session.flush()
    return guruh


async def _takroriy_navbat(session) -> int:
    """Bittadan ortiq `pending` so'rovnomasi bor guruhlar soni.

    Bunday guruh — guruhga ikkita bir xil xabar tushishi demak.
    """
    guruhlar = (
        select(SurveyModel.group_id)
        .where(
            SurveyModel.status == SurveyStatus.PENDING,
            SurveyModel.group_id.isnot(None),
        )
        .group_by(SurveyModel.group_id)
        .having(func.count(SurveyModel.id) > 1)
        .subquery()
    )
    return (
        await session.execute(select(func.count()).select_from(guruhlar))
    ).scalar_one()


@pytest.mark.asyncio
async def test_broadcast_force_false_suppression_oynasini_hurmat_qiladi(
    rollback_session, settings_guard
):
    await settings_guard("survey.enabled", True)
    session = rollback_session
    xodim = build_agent()
    session.add(xodim)
    await session.flush()

    yaqinda = await _biriktirilgan_guruh(
        session, xodim.id, last_survey_at=datetime.now(UTC) - timedelta(days=2)
    )
    kutgan = await _biriktirilgan_guruh(
        session, xodim.id, last_survey_at=datetime.now(UTC) - timedelta(days=30)
    )
    hech_qachon = await _biriktirilgan_guruh(session, xodim.id)
    hududsiz = build_group(agent_id=xodim.id, region=None)
    session.add(hududsiz)
    await session.flush()

    natija = await GroupService(session).broadcast_surveys(
        force=False, window_days=10
    )
    sabab = _skipped_reasons(natija)

    assert sabab[yaqinda.id] == "survey_suppressed"
    assert sabab[hududsiz.id] == "group_not_bound"
    assert kutgan.id not in sabab
    assert hech_qachon.id not in sabab

    assert await survey_count(session, yaqinda.id) == 0
    assert await survey_count(session, hududsiz.id) == 0
    assert await survey_count(session, kutgan.id) == 1
    assert await survey_count(session, hech_qachon.id) == 1

    # Hisob-kitob har doim to'g'ri chiqadi
    assert (
        natija["created"] + natija["reused"] + len(natija["skipped"])
        == natija["total_groups"]
    )


@pytest.mark.asyncio
async def test_broadcast_force_true_suppression_oynasini_chetlab_otadi(
    rollback_session, settings_guard
):
    """«Hozir hammaga yubor» tugmasining butun mazmuni shu.

    10 kunlik oyna sabab jimgina hech narsa yubormaslik — buzuq
    xatti-harakat.
    """
    await settings_guard("survey.enabled", True)
    session = rollback_session
    xodim = build_agent()
    session.add(xodim)
    await session.flush()

    yaqinda = await _biriktirilgan_guruh(
        session, xodim.id, last_survey_at=datetime.now(UTC) - timedelta(hours=1)
    )
    hududsiz = build_group(agent_id=xodim.id, region=None)
    session.add(hududsiz)
    await session.flush()

    natija = await GroupService(session).broadcast_surveys(force=True)
    sabab = _skipped_reasons(natija)

    assert yaqinda.id not in sabab
    assert await survey_count(session, yaqinda.id) == 1
    # Tuzilmaviy qoida esa `force` bilan ham ishlaydi
    assert sabab[hududsiz.id] == "group_not_bound"
    assert await survey_count(session, hududsiz.id) == 0


@pytest.mark.asyncio
async def test_broadcast_ketma_ket_chaqirilsa_takror_yaratmaydi(
    rollback_session, settings_guard
):
    """IDEMPOTENTLIK — server qayta ishga tushsa takror yubormaslik kafolati.

    Uch marta ketma-ket chaqiriladi. Birinchisi yaratadi, keyingi
    ikkitasi FAQAT `reused` beradi:

      · `created` NOL bo'ladi — bazada birorta yangi so'rovnoma yo'q,
      · `reused` birinchi yurishdagi `created + reused` ga TENG bo'ladi —
        ya'ni o'sha paytda yaratilganlarning hammasi endi navbatda
        turibdi va qaytadan yaratilmadi,
      · `skipped` ro'yxati uzunligi o'zgarmaydi — to'sqinlik qilgan
        guruhlar to'plami ham barqaror.

    Bu tekshiruv bazadagi boshqa guruhlarni ham qamrab oladi, shuning
    uchun kuchli: qaysidir guruh ikkinchi yurishda takror so'rovnoma
    olsa, `created` nolda qolmasdi.
    """
    await settings_guard("survey.enabled", True)
    session = rollback_session
    xodim = build_agent()
    session.add(xodim)
    await session.flush()

    birinchi_guruh = await _biriktirilgan_guruh(session, xodim.id)
    ikkinchi_guruh = await _biriktirilgan_guruh(session, xodim.id)
    service = GroupService(session)

    boshlangich_takror = await _takroriy_navbat(session)

    yurish_1 = await service.broadcast_surveys(force=False, window_days=7)
    assert yurish_1["created"] >= 2
    assert await survey_count(session, birinchi_guruh.id) == 1
    assert await survey_count(session, ikkinchi_guruh.id) == 1

    kutilgan_reused = yurish_1["created"] + yurish_1["reused"]

    for nechanchi in (2, 3):
        yurish = await service.broadcast_surveys(force=False, window_days=7)
        assert yurish["created"] == 0, f"{nechanchi}-yurishda yangisi yaratildi"
        assert yurish["reused"] == kutilgan_reused
        assert len(yurish["skipped"]) == len(yurish_1["skipped"])
        assert await survey_count(session, birinchi_guruh.id) == 1
        assert await survey_count(session, ikkinchi_guruh.id) == 1

    # Butun baza bo'yicha ham: uchta yurish birorta guruhga ikkinchi
    # `pending` so'rovnoma qo'shmadi. Boshlang'ich holat bilan
    # solishtiriladi — bazada avvaldan turgan ma'lumot testni
    # sababsiz qizartirmasin.
    assert await _takroriy_navbat(session) == boshlangich_takror
