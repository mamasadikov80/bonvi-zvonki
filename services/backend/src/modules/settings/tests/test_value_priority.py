"""USTUVORLIK:  baza  >  `.env`  >  reyestrdagi standart qiymat.

Nega muhim: tizim ikki xil sozlanadi — deploy paytida `.env` orqali,
ish vaqtida esa dashboard orqali. Agar tartib buzilsa, admin panelda
qiymatni o'zgartiradi-yu, kod baribir `.env` dagi eskisini o'qib
turaveradi. Bunday xato hech qanday xato xabari bermaydi — shunchaki
«sozlama ishlamayapti» bo'lib qoladi.

`.env` qatlamini tekshirish uchun `monkeypatch` ishlatiladi:
`src.core.config.settings` obyektining maydoni vaqtincha almashtiriladi
(fayl o'zgartirilmaydi). Baza qatlami esa `settings_guard` orqali —
u test oxirida asl qiymatni qaytaradi.
"""

from __future__ import annotations

import pytest

from src.core.config import settings as env_settings
from src.core.database import SessionFactory
from src.core.exceptions import NotFoundError
from src.modules.settings.application.services import SettingsService
from src.modules.settings.domain.entities import (
    SETTINGS_BY_KEY,
    SETTINGS_REGISTRY,
    SettingCategory,
    SettingSpec,
)

#: ⚠️ SINOV UCHUN VAQTINCHALIK SOZLAMA.
#:
#: Ilgari bu yerda haqiqiy sozlama (`asr.provider`, keyin `llm.provider`)
#: ishlatilardi va u ikki marta yiqildi: o'sha sozlamalar reyestrdan
#: olib tashlanganda test ham buzildi. Holbuki test SOZLAMANI emas,
#: USTUVORLIK MEXANIZMINI tekshiradi.
#:
#: Endi test o'ziga xos, o'zi yaratadigan sozlamada ishlaydi. Reyestr
#: qanday o'zgarmasin, mexanizm tekshirilaveradi.
KALIT = "survey.sinov_qatlami"
#: `.env` qatlamini `Settings` obyektining MAVJUD maydoni orqali
#: sinaymiz: pydantic yangi maydon qo'shishga ruxsat bermaydi, prod
#: konfiguratsiyasiga esa faqat test uchun maydon qo'shish noto'g'ri
#: bo'lardi. Bu maydonni shu fayldagi boshqa testlar ishlatmaydi.
ENV_MAYDONI = "ESKIZ_EMAIL"
STANDART = "standart-qiymat"


@pytest.fixture(autouse=True)
def sinov_sozlamasi():
    """Reyestrga vaqtincha sozlama qo'shadi va oxirida olib tashlaydi."""
    spec = SettingSpec(
        key=KALIT,
        category=SettingCategory.SURVEY,
        label_uz="Sinov qatlami",
        type="string",
        default=STANDART,
        env_var=ENV_MAYDONI,
    )
    SETTINGS_REGISTRY.append(spec)
    SETTINGS_BY_KEY[KALIT] = spec
    try:
        yield spec
    finally:
        SETTINGS_REGISTRY.remove(spec)
        SETTINGS_BY_KEY.pop(KALIT, None)


async def _oqish(kalit: str = KALIT):
    async with SessionFactory() as session:
        return await SettingsService(session).get_value(kalit)


# ══════════════════════════════════════════════════════════════
#  Uch qatlam
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_uchinchi_qatlam_reyestrdagi_standart(
    settings_guard, monkeypatch
) -> None:
    """Bazada ham, `.env` da ham qiymat yo'q → reyestrdagi standart."""
    await settings_guard(KALIT, "")  # bo'sh qiymat «yo'q» deb hisoblanadi
    monkeypatch.setattr(env_settings, ENV_MAYDONI, "")

    assert await _oqish() == STANDART


@pytest.mark.asyncio
async def test_ikkinchi_qatlam_env_standartdan_ustun(
    settings_guard, monkeypatch
) -> None:
    """Bazada qiymat yo'q → `.env` standartni bosadi."""
    await settings_guard(KALIT, "")
    monkeypatch.setattr(env_settings, ENV_MAYDONI, "env-qiymati")

    assert await _oqish() == "env-qiymati"


@pytest.mark.asyncio
async def test_birinchi_qatlam_baza_envdan_ustun(settings_guard, monkeypatch) -> None:
    """Ikkalasi ham to'ldirilgan → BAZA yutadi.

    Aynan shu qator dashboard'ni ma'noli qiladi: admin qiymatni
    o'zgartirsa, `.env` da nima turganidan qat'i nazar yangisi ishlaydi.
    """
    monkeypatch.setattr(env_settings, ENV_MAYDONI, "env-qiymati")
    await settings_guard(KALIT, "kotib")

    assert await _oqish() == "kotib"


@pytest.mark.asyncio
async def test_bazadagi_bosh_qiymat_envga_yol_beradi(
    settings_guard, monkeypatch
) -> None:
    """Admin maydonni tozalasa — `.env` qiymatiga qaytiladi, bo'shga emas.

    Aks holda kalitni tozalash integratsiyani butunlay o'ldirardi.
    """
    monkeypatch.setattr(env_settings, ENV_MAYDONI, "env-qiymati")
    await settings_guard(KALIT, "")

    assert await _oqish() == "env-qiymati"


@pytest.mark.asyncio
async def test_null_qiymat_ham_bosh_deb_hisoblanadi(
    settings_guard, monkeypatch
) -> None:
    monkeypatch.setattr(env_settings, ENV_MAYDONI, "env-qiymati")
    await settings_guard(KALIT, None)

    assert await _oqish() == "env-qiymati"


@pytest.mark.asyncio
async def test_manbasi_javobda_togri_korsatiladi(settings_guard, monkeypatch) -> None:
    """`source` maydoni diagnostika uchun — u ham ustuvorlikka mos bo'lsin."""
    from src.modules.settings.application.services import SettingsService as S

    monkeypatch.setattr(env_settings, ENV_MAYDONI, "env-qiymati")
    await settings_guard(KALIT, "kotib")

    async with SessionFactory() as session:
        royxat = await S(session).list_for_ui()
    maydon = next(
        f for k in royxat for f in k["fields"] if f["key"] == KALIT
    )
    assert maydon["source"] == "database"


# ══════════════════════════════════════════════════════════════
#  Boolean va son qiymatlari
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_false_qiymat_yozilsa_standartga_qaytmaydi(settings_guard) -> None:
    """`False` — haqiqiy qiymat, «to'ldirilmagan» emas.

    `if not value` deb tekshirilsa, o'chirilgan bayroq har safar
    standart holatiga (yoqilganiga) qaytib turardi — sozlamani
    o'chirib bo'lmay qolardi.
    """
    # `survey.enabled` standarti `True` — shuning uchun `False` yozilsa
    # standartga qaytmaganini ko'rsata oladi
    await settings_guard("survey.enabled", False)
    assert await _oqish("survey.enabled") is False


@pytest.mark.asyncio
async def test_nol_qiymat_yozilsa_standartga_qaytmaydi(settings_guard) -> None:
    """`0` ham haqiqiy qiymat — masalan «xabarni hech qachon o'chirma»."""
    await settings_guard("survey.message_ttl_hours", 0)
    assert await _oqish("survey.message_ttl_hours") == 0


# ══════════════════════════════════════════════════════════════
#  Reyestr yaxlitligi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_all_values_reyestrdagi_hamma_kalitni_qaytaradi() -> None:
    async with SessionFactory() as session:
        qiymatlar = await SettingsService(session).get_all_values()

    assert set(qiymatlar) == set(SETTINGS_BY_KEY)


@pytest.mark.asyncio
async def test_nomalum_kalitni_oqish_404_beradi() -> None:
    async with SessionFactory() as session:
        with pytest.raises(NotFoundError):
            await SettingsService(session).get_value("umuman.yoq.kalit")


def test_reyestrda_kalitlar_takrorlanmaydi() -> None:
    kalitlar = [s.key for s in SETTINGS_REGISTRY]
    assert len(kalitlar) == len(set(kalitlar))


def test_har_bir_kalit_kategoriya_prefiksi_bilan_boshlanadi() -> None:
    """`settings_guard` va `set_value` kategoriyani kalitdan ajratib oladi."""
    for spec in SETTINGS_REGISTRY:
        assert spec.key.split(".")[0] == spec.category.value, spec.key


def test_maxfiy_sozlamalarda_standart_qiymat_yoq() -> None:
    """Kodga yozilgan «standart kalit» — eng klassik sizib chiqish yo'li."""
    for spec in SETTINGS_REGISTRY:
        if spec.is_secret:
            assert spec.default in (None, ""), f"{spec.key} da standart kalit yozilgan"
