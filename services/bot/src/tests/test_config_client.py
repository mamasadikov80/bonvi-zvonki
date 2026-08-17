"""`services/config_client.py` — so'rovnoma qaysi shaklda chiziladi?

Sof unit test: HTTP so'rov qilinmaydi, faqat qaror mantiqi tekshiriladi.

NEGA MUHIM: qaror BITTA joyda turishi kerak. `pending`, `throttle` va
callback handleri qisqa nomni uch marta so'raydi — agar har biri o'zi
hisoblasa, biri Mini App havolasini, ikkinchisi 1–5 tugmalarini chizib
qo'yardi va bitta guruhda ikki xil so'rovnoma paydo bo'lardi.

Ikki manba birlashtiriladi:
  · `survey.mode`        — admin paneldagi ANIQ tanlov
  · `telegram.miniapp_name` — BotFather'dagi qisqa nom

Nom to'ldirilmagan bo'lsa Mini App tanlangan bo'lsa ham TUGMALAR
ishlaydi: ro'yxatdan o'tkazilmagan ilovaga havola qurish guruhga
buzuq tugma yuborardi.
"""

import pytest

from src.services.config_client import (
    MODE_BUTTONS,
    MODE_MINIAPP,
    BotConfig,
    ConfigClient,
)


def _config(**kwargs) -> BotConfig:
    base = {"token": "123:ABC", "username": "bonvi_bot"}
    return BotConfig(**{**base, **kwargs})


# ══════════════════════════════════════════════════════════════
#  effective_miniapp_name — yakuniy qaror
# ══════════════════════════════════════════════════════════════


def test_miniapp_rejimi_va_nom_bor_nom_qaytadi() -> None:
    config = _config(miniapp_name="survey", survey_mode=MODE_MINIAPP)

    assert config.effective_miniapp_name == "survey"
    assert config.has_miniapp is True


def test_miniapp_rejimi_lekin_nom_yoq_bosh_qaytadi() -> None:
    """Nomsiz havola qurib bo'lmaydi — eski oqimda qolamiz."""
    config = _config(miniapp_name="", survey_mode=MODE_MINIAPP)

    assert config.effective_miniapp_name == ""
    assert config.has_miniapp is False


def test_tugmalar_rejimi_tanlansa_nom_borligi_ahamiyatsiz() -> None:
    """Admin «Oddiy tugmalar» ni tanladi — nom bo'lsa ham hurmat qilinadi."""
    config = _config(miniapp_name="survey", survey_mode=MODE_BUTTONS)

    assert config.effective_miniapp_name == ""
    assert config.has_miniapp is False


def test_tugmalar_rejimi_va_nom_yoq() -> None:
    config = _config(miniapp_name="", survey_mode=MODE_BUTTONS)

    assert config.effective_miniapp_name == ""


def test_standart_rejim_miniapp() -> None:
    """Sozlama qo'shilmagan eski backend bilan ham oqim buzilmasin."""
    config = _config(miniapp_name="survey")

    assert config.survey_mode == MODE_MINIAPP
    assert config.effective_miniapp_name == "survey"


def test_has_token_bosh_tokenni_farqlaydi() -> None:
    assert _config().has_token is True
    assert BotConfig(token="", username="bonvi_bot").has_token is False


def test_config_ozgarmas() -> None:
    """`frozen=True` — qaror bir marta hisoblanadi va o'zgarmaydi."""
    config = _config(miniapp_name="survey")

    with pytest.raises((AttributeError, TypeError)):
        config.miniapp_name = "boshqa"  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════
#  _read_mode — noma'lum qiymat
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def client() -> ConfigClient:
    """Tarmoqqa chiqmaydi: faqat sof `_read_*` metodlari chaqiriladi.

    Manzil ataylab mavjud bo'lmagan xost — biror test tasodifan
    so'rov yuborsa, u haqiqiy backend'ga TUSHMASLIGI kerak.
    """
    return ConfigClient(base_url="http://pytest-backend-yoq:8000")


def test_buttons_qiymati_tanildi(client: ConfigClient) -> None:
    assert client._read_mode({"survey_mode": "buttons"}) == MODE_BUTTONS


def test_buttons_katta_harf_va_boshjoy_bilan_ham_tanildi(client: ConfigClient) -> None:
    assert client._read_mode({"survey_mode": "  BUTTONS "}) == MODE_BUTTONS


def test_miniapp_qiymati_tanildi(client: ConfigClient) -> None:
    assert client._read_mode({"survey_mode": "miniapp"}) == MODE_MINIAPP


@pytest.mark.parametrize(
    "raw", ["webapp", "kk", "1", "tugmalar", "MINI_APP", "null"]
)
def test_nomalum_rejim_miniapp_deb_qabul_qilinadi(
    client: ConfigClient, raw: str
) -> None:
    """Xato yozilgan sozlama tufayli so'rovnoma to'xtab qolmasin."""
    assert client._read_mode({"survey_mode": raw}) == MODE_MINIAPP


def test_maydon_umuman_bolmasa_miniapp(client: ConfigClient) -> None:
    """Eskiroq backend `survey_mode` yubormaydi — avvalgi xatti-harakat."""
    assert client._read_mode({}) == MODE_MINIAPP


def test_bosh_qiymat_miniapp(client: ConfigClient) -> None:
    assert client._read_mode({"survey_mode": ""}) == MODE_MINIAPP
    assert client._read_mode({"survey_mode": None}) == MODE_MINIAPP


def test_nomalum_rejim_haqida_bir_marta_ogohlantiriladi(
    client: ConfigClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Har 30 soniyada takrorlansa log o'qib bo'lmas holga kelardi."""
    with caplog.at_level("WARNING"):
        client._read_mode({"survey_mode": "webapp"})
        client._read_mode({"survey_mode": "webapp"})

    ogohlantirishlar = [r for r in caplog.records if "webapp" in r.getMessage()]
    assert len(ogohlantirishlar) == 1


# ══════════════════════════════════════════════════════════════
#  _read_miniapp — yaroqsiz nom bo'sh deb qaraladi
# ══════════════════════════════════════════════════════════════


def test_yaroqli_nom_oqiladi(client: ConfigClient) -> None:
    assert client._read_miniapp({"miniapp_name": "survey_2026"}) == "survey_2026"


def test_yaroqsiz_nom_bosh_deb_qaraladi(client: ConfigClient) -> None:
    """«@survey» dan buzuq URL quriladi va u HAQIQIY guruhga tushardi."""
    assert client._read_miniapp({"miniapp_name": "@survey"}) == ""


def test_nom_umuman_bolmasa_bosh(client: ConfigClient) -> None:
    assert client._read_miniapp({}) == ""


def test_muqobil_kalitlar_ham_oqiladi(client: ConfigClient) -> None:
    """Bot va backend parallel yozilgan — nom biroz boshqacha bo'lishi mumkin."""
    assert client._read_miniapp({"bot_miniapp_name": "survey"}) == "survey"
    assert client._read_miniapp({"telegram.miniapp_name": "survey"}) == "survey"


def test_birinchi_topilgan_kalit_yutadi(client: ConfigClient) -> None:
    natija = client._read_miniapp(
        {"miniapp_name": "birinchi", "bot_miniapp_name": "ikkinchi"}
    )

    assert natija == "birinchi"


def test_keshlangan_nom_sorovsiz_bosh_boladi(client: ConfigClient) -> None:
    """Hali hech narsa olinmagan — chizuvchi tugmalar rejimida qolsin."""
    assert client.miniapp_name == ""
