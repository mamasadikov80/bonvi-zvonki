"""Sinxronizatsiya oralig'i {SYNC_MAX_DAYS} kun bilan cheklanadi.

NEGA BU TEST BOR. Chegara ikki joyda ko'rinadi: sana tanlagichga
beriladigan `GET /calls/sync/window` va so'rovni qisqartiradigan
`POST /calls/sync`. Ular bir-biridan ajralib ketsa nosozlik JIM
bo'ladi — admin «1-martdan» deb tanlaydi, «12 ta yangi» degan javob
oladi va mart ma'lumoti yo'q deb o'ylaydi. Aslida oraliq
qisqartirilgan.

Chegarasiz so'rovning narxi ham bor: MoyZvonki bir necha yillik
arxivni sahifalab beradi va so'rov soatlab ishlaydi — admin uni
to'xtata olmaydi.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.calls.presentation.router import _as_utc, _earliest_allowed
from src.modules.moizvonki.domain.entities import SYNC_MAX_DAYS

API = "http://test/api/v1"


def timezone_of(hours: int):
    from datetime import timezone

    return timezone(timedelta(hours=hours))


def test_chegara_konstantaga_teng() -> None:
    """Endpoint qaytaradigan kun aynan `SYNC_MAX_DAYS` orqada."""
    kutilgan = datetime.now(UTC).date() - timedelta(days=SYNC_MAX_DAYS)
    assert _earliest_allowed().date() == kutilgan


def test_kun_boshiga_tekislanadi() -> None:
    """Soatga bog'liq bo'lmasligi kerak.

    Aks holda ertalab sinxronlagan admin kechqurun sinxronlaganidan
    boshqa oraliq olardi va nega ba'zi qo'ng'iroqlar tushmaganini
    tushunmasdi."""
    limit = _earliest_allowed()
    assert (limit.hour, limit.minute, limit.second, limit.microsecond) == (0, 0, 0, 0)
    assert limit.tzinfo is not None


# ══════════════════════════════════════════════════════════════
#  Qisqartirish mantiqi — endpoint aynan shu ikki qatorni bajaradi
# ══════════════════════════════════════════════════════════════


def _qisqartir(soralgan: datetime) -> tuple[datetime, bool]:
    limit = _earliest_allowed()
    asked = _as_utc(soralgan)
    since = max(asked, limit)
    return since, since > asked


def test_chegara_ichidagi_sana_ozgarmaydi() -> None:
    soralgan = datetime.now(UTC) - timedelta(days=SYNC_MAX_DAYS - 5)
    since, clamped = _qisqartir(soralgan)
    assert since == soralgan
    assert clamped is False


def test_juda_eski_sana_qisqartiriladi() -> None:
    # ⚠️ Chegaraga NISBATAN hisoblanadi, qat'iy 365 kun emas:
    # `SYNC_MAX_DAYS` bir yilga ko'tarilganda qat'iy raqam chegaraning
    # aynan o'ziga tushib qolib, test jimgina ma'nosiz bo'lib qolardi.
    soralgan = datetime.now(UTC) - timedelta(days=SYNC_MAX_DAYS + 60)
    since, clamped = _qisqartir(soralgan)
    assert clamped is True
    assert since == _earliest_allowed()


def test_qisqartirish_haqida_xabar_beriladi() -> None:
    """⚠️ Jim qisqartirish eng yomon variant — belgi majburiy."""
    _, clamped = _qisqartir(datetime.now(UTC) - timedelta(days=SYNC_MAX_DAYS + 1))
    assert clamped is True, "chegaradan bir kun oldingi sana ham belgilanishi kerak"


# ══════════════════════════════════════════════════════════════
#  Mintaqasiz sana
# ══════════════════════════════════════════════════════════════


def test_mintaqasiz_sana_500_bermaydi() -> None:
    """«Z» siz sana jo'natgan mijoz sinxronizatsiyani yiqitmasligi kerak.

    Pydantic mintaqasiz `datetime` ni qabul qiladi, uni mintaqali
    chegara bilan solishtirish esa `TypeError` beradi."""
    naive = datetime.now() - timedelta(days=10)  # noqa: DTZ005 — ataylab mintaqasiz
    since, _ = _qisqartir(naive)
    assert since.tzinfo is not None


@pytest.mark.parametrize("offset_hours", [5, -8])
def test_boshqa_mintaqadagi_sana_utcga_keltiriladi(offset_hours: int) -> None:
    tz = timezone_of(offset_hours)
    soralgan = datetime.now(tz) - timedelta(days=10)
    since, clamped = _qisqartir(soralgan)
    assert clamped is False
    assert since == soralgan  # bir xil payt, boshqa ko'rinish


# ══════════════════════════════════════════════════════════════
#  To'liq chegaradan tashqaridagi oraliq
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_endpoint_chegarani_beradi(admin_client) -> None:
    """Sana tanlagich shu javobga tayanadi — shakli qulflanadi."""
    response = await admin_client.get(f"{API}/calls/sync/window")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"] == SYNC_MAX_DAYS
    assert body["earliest"] == str(_earliest_allowed().date())


@pytest.mark.asyncio
async def test_toliq_tashqaridagi_oraliq_rad_etiladi(admin_client) -> None:
    """⚠️ Boshini qirqish oraliqni TESKARI qilardi — aniq xato kerak.

    «1-mart — 2-mart» so'ralsa, boshini chegaraga tortish «3-iyuldan
    2-martgacha» degan ma'nosiz oraliq beradi va javob «0 ta yangi»
    bo'lib chiqadi: admin ma'lumot yo'q deb o'ylaydi, aslida so'rov
    noto'g'ri. MoyZvonki'ga ham bejiz so'rov ketmasligi kerak."""
    limit = _earliest_allowed()
    response = await admin_client.post(
        f"{API}/calls/sync",
        json={
            "date_from": (limit - timedelta(days=60)).isoformat(),
            "date_to": (limit - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    # Xabar admin nima qilishini AYTISHI kerak — quruq «noto'g'ri» emas
    assert str(SYNC_MAX_DAYS) in error["message"]
    assert f"{limit:%d.%m.%Y}" in error["message"]
