"""`GET /settings` va `PUT /settings`.

Ikkita asosiy xavf shu yerda ushlanadi:

  1. REYESTRGA QO'SHILDI-YU, UI GA CHIQMADI.
     Yangi sozlama `SETTINGS_REGISTRY` ga yozilsa-yu, javobga tushmay
     qolsa — admin uni hech qachon ko'rmaydi va «sozlama ishlamayapti»
     degan xulosaga keladi. Shuning uchun test reyestr BO'YLAB yuradi,
     qattiq yozilgan ro'yxat bilan emas.

  2. MAXFIY QIYMAT TASHQARIGA CHIQDI.
     `type == "secret"` bo'lgan maydonning XOM qiymati javobda umuman
     bo'lmasligi kerak — faqat «to'ldirilgan / to'ldirilmagan» holati.
     Bitta sozlama noto'g'ri turga qo'yilsa, API kaliti brauzer
     konsolida turib qoladi.
"""

from __future__ import annotations

import httpx
import pytest

from src.conftest import API
from src.core.database import SessionFactory
from src.modules.settings.application.services import SettingsService
from src.modules.settings.domain.entities import (
    CATEGORY_LABEL_UZ,
    SECRET_MASK,
    SETTINGS_BY_KEY,
    SETTINGS_REGISTRY,
)

#: Ochiq matnda tashqariga chiqmasligi kerak bo'lgan sinov qiymati.
SIRLI = "pytest-SIRLI-QIYMAT-tashqariga-chiqmasin-7f3a"

#: Sinov uchun tanlangan maxfiy sozlama — SMS zaxira kanali paroli.
#: Uni o'zgartirish hech qanday jarayonni to'xtatmaydi.
SINOV_SECRET_KALITI = "sms.eskiz_password"


def _maydonlar(body: list[dict]) -> dict[str, dict]:
    """Kategoriyalarga bo'lingan javobni bitta `kalit → maydon` lug'atiga yig'adi."""
    return {
        maydon["key"]: maydon
        for kategoriya in body
        for maydon in kategoriya["fields"]
    }


# ══════════════════════════════════════════════════════════════
#  1) Reyestrdagi HAR BIR sozlama javobda bor
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reyestrdagi_har_bir_sozlama_javobda_bor(
    admin_client: httpx.AsyncClient,
) -> None:
    body = (await admin_client.get(f"{API}/settings")).json()
    maydonlar = _maydonlar(body)

    yetishmayotgan = set(SETTINGS_BY_KEY) - set(maydonlar)
    ortiqcha = set(maydonlar) - set(SETTINGS_BY_KEY)

    assert not yetishmayotgan, (
        f"reyestrda bor, UI ga chiqmagan sozlamalar: {sorted(yetishmayotgan)}"
    )
    assert not ortiqcha, f"reyestrda yo'q, javobda bor: {sorted(ortiqcha)}"


@pytest.mark.asyncio
async def test_har_bir_maydonda_ui_uchun_kerakli_hamma_narsa_bor(
    admin_client: httpx.AsyncClient,
) -> None:
    """UI forma quradi: yorliq, tur, tanlov variantlari va manba."""
    maydonlar = _maydonlar((await admin_client.get(f"{API}/settings")).json())

    for kalit, spec in SETTINGS_BY_KEY.items():
        maydon = maydonlar[kalit]
        assert set(maydon) == {
            "key", "label", "type", "options", "hint", "value", "is_set", "source"
        }, kalit
        assert maydon["label"] == spec.label_uz
        assert maydon["type"] == spec.type
        assert maydon["options"] == spec.options
        assert maydon["source"] in ("database", "env", "default"), kalit


@pytest.mark.asyncio
async def test_select_turidagi_sozlamada_variantlar_bosh_emas(
    admin_client: httpx.AsyncClient,
) -> None:
    """`select` da variantlarsiz forma — bo'sh ochiladigan ro'yxat."""
    maydonlar = _maydonlar((await admin_client.get(f"{API}/settings")).json())

    for kalit, maydon in maydonlar.items():
        if maydon["type"] != "select":
            continue
        assert maydon["options"], f"{kalit}: `select` variantlarsiz"
        for variant in maydon["options"]:
            assert set(variant) >= {"value", "label"}, kalit


@pytest.mark.asyncio
async def test_kategoriyalar_toliq_va_ozbekcha_nomlangan(
    admin_client: httpx.AsyncClient,
) -> None:
    body = (await admin_client.get(f"{API}/settings")).json()

    kutilgan = {s.category.value for s in SETTINGS_REGISTRY}
    assert {k["category"] for k in body} == kutilgan
    for kategoriya in body:
        spec_kategoriya = next(
            c for c in CATEGORY_LABEL_UZ if c.value == kategoriya["category"]
        )
        assert kategoriya["label"] == CATEGORY_LABEL_UZ[spec_kategoriya]


# ══════════════════════════════════════════════════════════════
#  2) Maxfiy qiymatlar HECH QACHON qaytarilmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_maxfiy_maydonlarning_xom_qiymati_javobda_yoq(
    admin_client: httpx.AsyncClient,
) -> None:
    """Har bir `secret` maydon — yo `None`, yo maska. Uchinchisi yo'q."""
    maydonlar = _maydonlar((await admin_client.get(f"{API}/settings")).json())

    secret_kalitlar = [k for k, s in SETTINGS_BY_KEY.items() if s.is_secret]
    assert secret_kalitlar, "reyestrda birorta maxfiy sozlama yo'q — test ma'nosiz"

    for kalit in secret_kalitlar:
        qiymat = maydonlar[kalit]["value"]
        assert qiymat in (None, SECRET_MASK), f"{kalit} xom qiymat qaytardi"


@pytest.mark.asyncio
async def test_saqlangan_maxfiy_qiymat_javobga_umuman_tushmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """Haqiqiy qiymat yozib ko'ramiz va butun javob matnidan qidiramiz."""
    await settings_guard(SINOV_SECRET_KALITI, SIRLI)

    response = await admin_client.get(f"{API}/settings")
    assert SIRLI not in response.text, "maxfiy qiymat javobda ochiq chiqdi"

    maydon = _maydonlar(response.json())[SINOV_SECRET_KALITI]
    assert maydon["value"] == SECRET_MASK
    assert maydon["is_set"] is True, "to'ldirilgani bilinishi kerak"


@pytest.mark.asyncio
async def test_toldirilmagan_maxfiy_maydon_is_set_false(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    await settings_guard(SINOV_SECRET_KALITI, "")

    maydon = _maydonlar((await admin_client.get(f"{API}/settings")).json())[
        SINOV_SECRET_KALITI
    ]
    assert maydon["is_set"] is False
    assert maydon["value"] is None


@pytest.mark.asyncio
async def test_maska_qaytarib_yuborilsa_qiymat_ozgarmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """UI maskani ko'rsatadi. Foydalanuvchi maydonga tegmay «Saqlash»
    bossa, brauzer maskani qaytaradi — u kalitni O'CHIRIB yubormasin.
    """
    await settings_guard(SINOV_SECRET_KALITI, SIRLI)

    response = await admin_client.put(
        f"{API}/settings", json={"values": {SINOV_SECRET_KALITI: SECRET_MASK}}
    )
    assert response.status_code == 200, response.text

    async with SessionFactory() as session:
        saqlangan = await SettingsService(session).get_value(SINOV_SECRET_KALITI)
    assert saqlangan == SIRLI, "maska kalitni bosib yozib yubordi"


@pytest.mark.asyncio
async def test_put_javobi_ham_maxfiy_qiymatni_ochmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """`PUT` ham `list_for_ui()` qaytaradi — u yerda ham maska bo'lsin."""
    await settings_guard(SINOV_SECRET_KALITI, "eski-qiymat")

    response = await admin_client.put(
        f"{API}/settings", json={"values": {SINOV_SECRET_KALITI: SIRLI}}
    )
    assert response.status_code == 200, response.text
    assert SIRLI not in response.text, "yangi kalit darhol javobda qaytib chiqdi"


@pytest.mark.asyncio
async def test_health_endpointi_ham_kalitlarni_oshkor_qilmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """`/settings/health` faqat «sozlangan / sozlanmagan» deyishi kerak."""
    await settings_guard(SINOV_SECRET_KALITI, SIRLI)
    await settings_guard("llm.anthropic_api_key", SIRLI)

    response = await admin_client.get(f"{API}/settings/health")
    assert response.status_code == 200, response.text
    assert SIRLI not in response.text

    sms = next(item for item in response.json() if item["id"] == "sms")
    assert sms["configured"] in (True, False)


# ══════════════════════════════════════════════════════════════
#  3) `PUT /settings` — nima qabul qilinadi, nima rad etiladi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_togri_qiymat_saqlanadi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    await settings_guard("survey.period_days", 14)

    response = await admin_client.put(
        f"{API}/settings", json={"values": {"survey.period_days": 21}}
    )
    assert response.status_code == 200, response.text

    maydon = _maydonlar(response.json())["survey.period_days"]
    assert maydon["value"] == 21
    assert maydon["source"] == "database"


@pytest.mark.asyncio
async def test_nomalum_kalit_rad_etiladi(admin_client: httpx.AsyncClient) -> None:
    """Reyestrda yo'q kalit bazaga umuman tushmasligi kerak."""
    response = await admin_client.put(
        f"{API}/settings", json={"values": {"yoq.sozlama": "qiymat"}}
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"

    async with SessionFactory() as session:
        from sqlalchemy import select

        from src.modules.settings.infrastructure.models import SettingModel

        qoldi = (
            await session.execute(
                select(SettingModel).where(SettingModel.key == "yoq.sozlama")
            )
        ).scalar_one_or_none()
    assert qoldi is None, "rad etilgan kalit baribir bazaga yozilib qolgan"


@pytest.mark.asyncio
async def test_nomalum_kalit_bilan_birga_kelgan_togri_kalit_ham_saqlanmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """Saqlash — bo'linmas amal. Yarmi o'tib, yarmi o'tmasligi mumkin emas."""
    await settings_guard("survey.period_days", 14)

    response = await admin_client.put(
        f"{API}/settings",
        json={"values": {"survey.period_days": 30, "yoq.sozlama": 1}},
    )
    assert response.status_code == 404, response.text

    async with SessionFactory() as session:
        qiymat = await SettingsService(session).get_value("survey.period_days")
    assert int(qiymat) == 14, "xato so'rov qisman saqlanib qolgan"


@pytest.mark.asyncio
async def test_bosh_royxat_bilan_soralsa_hech_narsa_ozgarmaydi(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.put(f"{API}/settings", json={"values": {}})
    assert response.status_code == 200, response.text
    assert _maydonlar(response.json()).keys() == set(SETTINGS_BY_KEY)


@pytest.mark.asyncio
async def test_select_royxatidan_tashqari_qiymat_rad_etiladi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """`survey.mode` faqat `miniapp` yoki `buttons` bo'lishi mumkin."""
    await settings_guard("survey.mode", "miniapp")  # asl qiymat saqlab qo'yiladi

    response = await admin_client.put(
        f"{API}/settings", json={"values": {"survey.mode": "telepatiya"}}
    )
    assert response.status_code in (400, 422), response.text


@pytest.mark.asyncio
async def test_number_turiga_matn_rad_etiladi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    await settings_guard("survey.period_days", 14)

    response = await admin_client.put(
        f"{API}/settings", json={"values": {"survey.period_days": "juda ko'p"}}
    )
    assert response.status_code in (400, 422), response.text


@pytest.mark.asyncio
async def test_number_turiga_matn_yozilsa_ham_oquvchi_yiqilmaydi(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """Yuqoridagi kamchilik tuzatilgunicha — hech bo'lmasa tizim ishlaydi.

    Bazaga matn tushib qolgan taqdirda ham sozlamani o'qiydigan kod
    standart qiymatga qaytadi, 500 bermaydi.
    """
    await settings_guard("survey.period_days", "juda ko'p")

    from src.modules.surveys.application.services import resolve_period_days

    async with SessionFactory() as session:
        assert await resolve_period_days(session) == 14

    # UI ham ochilaveradi
    assert (await admin_client.get(f"{API}/settings")).status_code == 200
