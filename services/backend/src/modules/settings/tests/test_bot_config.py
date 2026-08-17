"""`GET /settings/bot-config` — ICHKI endpoint.

Bu endpoint Telegram bot tokenini MASKASIZ qaytaradi. Botning
foydalanuvchi hisobi yo'q, shuning uchun himoya JWT emas —
`X-Internal-Token` umumiy maxfiy kaliti.

«Docker ichki tarmog'ida turibdi» — himoya emas: backend porti hostga
chiqarilgan (`8010:8000`), ya'ni serverdagi istalgan jarayon shu
manzilni so'ray oladi. Token qo'lga tushsa — begona odam bot nomidan
yozadi va so'rovnoma javoblarini o'g'irlaydi.

Shuning uchun bu yerda uchta narsa tekshiriladi:
  • sarlavhasiz — 401;
  • noto'g'ri token bilan — 401 (uzunligi boshqa bo'lsa ham);
  • admin JWT ham yordam bermaydi — bu boshqa himoya kanali.
"""

from __future__ import annotations

import httpx
import pytest

from src.conftest import API
from src.core.config import settings as env_settings

TOKEN_BOR = bool(env_settings.INTERNAL_API_TOKEN)
token_kerak = pytest.mark.skipif(
    not TOKEN_BOR,
    reason="`.env` da INTERNAL_API_TOKEN sozlanmagan — ichki API butunlay yopiq",
)


def _sarlavha(token: str) -> dict[str, str]:
    return {"X-Internal-Token": token}


# ══════════════════════════════════════════════════════════════
#  Himoya
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sarlavhasiz_401(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get(f"{API}/settings/bot-config")

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "unauthorized"
    assert "bot_token" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="bosh"),
        pytest.param("notogri-token", id="notogri"),
        pytest.param("x" * 64, id="togri-uzunlikdagi-notogri"),
    ],
)
async def test_notogri_token_401(anon_client: httpx.AsyncClient, token: str) -> None:
    """Uzunligi bir xil bo'lsa ham o'tmaydi — taqqoslash to'liq bo'yicha."""
    response = await anon_client.get(
        f"{API}/settings/bot-config", headers=_sarlavha(token)
    )

    assert response.status_code == 401, response.text
    assert "bot_token" not in response.text


@pytest.mark.asyncio
async def test_admin_jwt_ichki_endpointni_ochmaydi(
    admin_client: httpx.AsyncClient,
) -> None:
    """Ikki himoya kanali aralashmasin.

    Admin brauzerdan kirgan bo'lsa ham, maskasiz token beriladigan
    endpoint uchun ALOHIDA kalit talab qilinadi.
    """
    response = await admin_client.get(f"{API}/settings/bot-config")
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_bot_identity_ham_himoyalangan(anon_client: httpx.AsyncClient) -> None:
    """Yozadigan ichki endpoint ham xuddi shunday yopiq.

    Ochiq qolsa begona odam `telegram.bot_username` ni almashtirib,
    deep-link'ni o'z botiga burib yuborardi.
    """
    response = await anon_client.post(
        f"{API}/settings/bot-identity", json={"username": "yolgonchi_bot"}
    )
    assert response.status_code == 401, response.text


# ══════════════════════════════════════════════════════════════
#  To'g'ri token bilan
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@token_kerak
async def test_togri_token_bilan_200_va_survey_mode_bor(
    anon_client: httpx.AsyncClient,
) -> None:
    response = await anon_client.get(
        f"{API}/settings/bot-config",
        headers=_sarlavha(env_settings.INTERNAL_API_TOKEN),
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert set(body) == {"bot_token", "bot_username", "miniapp_name", "survey_mode"}
    assert body["survey_mode"] in ("miniapp", "buttons")
    # Maydonlar doim matn — bot `None` bilan ishlay olmaydi
    assert all(isinstance(v, str) for v in body.values())


@pytest.mark.asyncio
@token_kerak
@pytest.mark.parametrize("rejim", ["miniapp", "buttons"])
async def test_survey_mode_paneldagi_tanlovni_aks_ettiradi(
    anon_client: httpx.AsyncClient, settings_guard, rejim: str
) -> None:
    """Admin rejimni almashtirsa, bot keyingi tekshiruvda yangisini oladi."""
    await settings_guard("survey.mode", rejim)

    body = (
        await anon_client.get(
            f"{API}/settings/bot-config",
            headers=_sarlavha(env_settings.INTERNAL_API_TOKEN),
        )
    ).json()
    assert body["survey_mode"] == rejim


@pytest.mark.asyncio
@token_kerak
async def test_bot_username_dagi_ortiqcha_belgilar_tozalanadi(
    anon_client: httpx.AsyncClient, settings_guard
) -> None:
    """Admin `@` bilan kiritsa ham bot toza username oladi.

    Deep-link `t.me/<username>?start=...` — ikkita `@` bilan ishlamaydi.
    """
    await settings_guard("telegram.bot_username", "@sinov_boti")
    await settings_guard("telegram.miniapp_name", "  survey  ")

    body = (
        await anon_client.get(
            f"{API}/settings/bot-config",
            headers=_sarlavha(env_settings.INTERNAL_API_TOKEN),
        )
    ).json()
    assert body["bot_username"] == "sinov_boti"
    assert body["miniapp_name"] == "survey"


@pytest.mark.asyncio
@token_kerak
async def test_sozlanmagan_maydonlar_bosh_matn_boladi(
    anon_client: httpx.AsyncClient, settings_guard
) -> None:
    """`None` emas, `""`. Bot `"".strip()` qilib xotirjam ishlaydi."""
    await settings_guard("telegram.miniapp_name", "")

    body = (
        await anon_client.get(
            f"{API}/settings/bot-config",
            headers=_sarlavha(env_settings.INTERNAL_API_TOKEN),
        )
    ).json()
    assert body["miniapp_name"] == ""


@pytest.mark.asyncio
@token_kerak
async def test_bot_token_bazadagi_qiymatdan_olinadi(
    anon_client: httpx.AsyncClient, settings_guard
) -> None:
    """Admin panelda tokenni o'zgartirsa — bot yangisini oladi (maskasiz).

    `GET /settings` dan farqi aynan shu: bu yerda maska YO'Q, aks holda
    bot ishlay olmasdi.
    """
    sinov_token = "123456:pytest-sinov-token-emas-haqiqiy"
    await settings_guard("telegram.bot_token", sinov_token)

    body = (
        await anon_client.get(
            f"{API}/settings/bot-config",
            headers=_sarlavha(env_settings.INTERNAL_API_TOKEN),
        )
    ).json()
    assert body["bot_token"] == sinov_token
