"""Qaysi nosozlikda qayta uriniladi va qaysisida — yo'q.

NEGA BU MUHIM. Quvurdagi bitta qaror pul va navbat holatini belgilaydi:

  · O'tkinchi nosozlikda (429, 5xx, tarmoq) qayta urinilmasa —
    qo'ng'iroq `failed` bo'lib qoladi va uni odam qo'lda qayta ishga
    tushirishi kerak. Gemini o'rtacha yuklamada ham 503 «high demand»
    qaytaradi, ya'ni bu nazariy emas, kundalik holat.
  · Mijoz xatosida (noto'g'ri kalit, noto'g'ri model nomi) qayta
    urinilsa — har urinish pul yeydi va natija baribir o'sha xato
    bo'ladi. Bunday xato TEZ ko'rinishi kerak.

Shuning uchun qoida testda qulflangan: kimdir `is_retryable` ga yangi
tur qo'shsa, bu yerda ham ongli o'zgarish talab qilinadi.
"""

import httpx
import pytest

from src.modules.ai.domain.errors import (
    AIAuthError,
    AIConfigError,
    AIDependencyError,
    AIModelError,
    AINetworkError,
    AIRateLimitError,
    AIRequestError,
    AIUnavailableError,
)
from src.modules.pipeline.infrastructure.limits import (
    is_rate_limited,
    is_retryable,
    with_backoff,
)


class _StatusError(Exception):
    """Provayder SDK'si beradigan, `status_code` li xom xato."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


def _response_error(status: int) -> Exception:
    """`response.status_code` orqali holat beradigan xato (httpx uslubi)."""
    request = httpx.Request("POST", "https://example.test")
    return httpx.HTTPStatusError(
        "xato",
        request=request,
        response=httpx.Response(status, request=request),
    )


# ══════════════════════════════════════════════════════════════
#  Qayta urinish MA'NOLI
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "exc",
    [
        AIRateLimitError("chegara"),
        AIUnavailableError("model band"),
        AINetworkError("ulanish uzildi"),
        _StatusError(429),
        _StatusError(500),
        _StatusError(502),
        _StatusError(503),
        _StatusError(504),
        _response_error(503),
    ],
    ids=lambda e: type(e).__name__ + str(getattr(e, "status_code", "")),
)
def test_otkinchi_nosozlikda_qayta_uriniladi(exc: Exception) -> None:
    assert is_retryable(exc)


# ══════════════════════════════════════════════════════════════
#  Qayta urinish BEFOYDA
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "exc",
    [
        AIAuthError("kalit noto'g'ri"),
        AIModelError("bunday model yo'q"),
        AIRequestError("so'rov qabul qilinmadi"),
        # ⚠️ Bu ikkalasining `status_code` i 5xx (409 va 503), lekin u
        # BIZNING API javobimiz kodi. Qayta urinish ularni tuzatmaydi:
        # biri sozlama xatosi, ikkinchisi o'rnatilmagan kutubxona.
        AIConfigError("provayder sozlanmagan"),
        AIDependencyError("google-genai o'rnatilmagan"),
        _StatusError(400),
        _StatusError(401),
        _StatusError(404),
        _response_error(422),
        ValueError("kutilmagan"),
    ],
    ids=lambda e: type(e).__name__ + str(getattr(e, "status_code", "")),
)
def test_mijoz_xatosida_qayta_urinilmaydi(exc: Exception) -> None:
    """Noto'g'ri kalit yoki model — qayta urinish faqat pul yeydi."""
    assert not is_retryable(exc)


def test_rate_limit_alohida_ham_taniladi() -> None:
    """`is_rate_limited` chegara bilan boshqa nosozlikni ARALASHTIRMAYDI.

    Ikkalasi ham qayta urinishga tushadi, lekin sabab bir xil emas:
    chegara — bizning tezligimiz, 503 — provayderning holati.
    """
    assert is_rate_limited(AIRateLimitError("chegara"))
    assert is_rate_limited(_StatusError(429))
    assert not is_rate_limited(AIUnavailableError("model band"))
    assert not is_rate_limited(_StatusError(503))


# ══════════════════════════════════════════════════════════════
#  `with_backoff` xulqi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_503_dan_keyin_muvaffaqiyat() -> None:
    """Ikki marta 503, uchinchisida natija — chaqiruv YIQILMAYDI."""
    urinishlar = 0

    async def action() -> str:
        nonlocal urinishlar
        urinishlar += 1
        if urinishlar <= 2:
            raise AIUnavailableError("Google Gemini serveri javob bermadi (503)")
        return "matn"

    natija = await with_backoff(
        action, max_retries=4, base_sec=0.0, max_sec=0.0, label="transcribe"
    )

    assert natija == "matn"
    assert urinishlar == 3


@pytest.mark.asyncio
async def test_notogri_model_darhol_yiqiladi() -> None:
    """Qayta urinilmaydigan xato BIRINCHI urinishdayoq ko'tariladi."""
    urinishlar = 0

    async def action() -> str:
        nonlocal urinishlar
        urinishlar += 1
        raise AIModelError("«yo'q-model» ni provayder tanimadi")

    with pytest.raises(AIModelError):
        await with_backoff(
            action, max_retries=4, base_sec=0.0, max_sec=0.0, label="score"
        )

    assert urinishlar == 1


@pytest.mark.asyncio
async def test_urinishlar_chegarasi_hurmat_qilinadi() -> None:
    """`max_retries` dan keyin xato chiqadi — cheksiz aylanish yo'q."""
    urinishlar = 0

    async def action() -> str:
        nonlocal urinishlar
        urinishlar += 1
        raise AIUnavailableError("model band")

    with pytest.raises(AIUnavailableError):
        await with_backoff(
            action, max_retries=2, base_sec=0.0, max_sec=0.0, label="transcribe"
        )

    # 1 ta asosiy + 2 ta qayta urinish
    assert urinishlar == 3
