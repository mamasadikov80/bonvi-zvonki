"""`views/groups.py` — guruh so'rovnomasining matni va tugmalari.

Sof unit test: Telegram API ga chiqmaydi, faqat tayyorlangan obyektlar
tekshiriladi.

NEGA MUHIM: bu modul HAQIQIY mijozlar guruhiga tushadigan xabarni
quradi. Xato bu yerda emas, mijozning ekranida ko'rinadi:

  · yaroqsiz qisqa nomdan buzuq URL quriladi va tugma bosilganda hech
    narsa ochilmaydi — mijoz baho bermay ketadi;
  · rejim adashsa, tugmalar rejimida Mini App havolasi (yoki teskarisi)
    chiziladi va butun so'rovnoma yo'qoladi.
"""

import pytest

from src.views.groups import (
    DIGITS,
    MINIAPP_BUTTON,
    TOKEN_PREFIX,
    is_valid_miniapp_name,
    miniapp_link,
    survey_kb,
    survey_text,
)

TOKEN = "abc123token"
BOT = "bonvi_bot"
APP = "survey"


# ══════════════════════════════════════════════════════════════
#  is_valid_miniapp_name — BotFather qoidasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "name",
    ["abc", "survey", "survey_2026", "A" * 30, "a_b_c", "app123", "123"],
)
def test_yaroqli_qisqa_nomlar_qabul_qilinadi(name: str) -> None:
    assert is_valid_miniapp_name(name) is True


@pytest.mark.parametrize(
    ("name", "sabab"),
    [
        ("ab", "3 belgidan qisqa"),
        ("a" * 31, "30 belgidan uzun"),
        ("", "bo'sh"),
        ("@survey", "admin «@» bilan yozdi"),
        ("https://t.me/bot/survey", "admin to'liq havola qo'ydi"),
        ("my survey", "bo'shliq bor"),
        ("so'rov", "lotin bo'lmagan belgi"),
        ("survey-app", "chiziqcha ruxsat etilmagan"),
        ("survey.app", "nuqta ruxsat etilmagan"),
        (" survey", "boshida bo'shliq"),
        ("survey ", "oxirida bo'shliq"),
    ],
)
def test_yaroqsiz_qisqa_nomlar_rad_etiladi(name: str, sabab: str) -> None:
    assert is_valid_miniapp_name(name) is False, f"«{name}» o'tib ketdi ({sabab})"


def test_oxiridagi_yangi_qator_konfigda_kesiladi() -> None:
    """Nega bu yerda emas, `config_client` da tekshiriladi:

    `re.match(..., "survey\\n")` Python'da O'TADI — `$` oxirgi yangi
    qatordan oldin ham mos keladi. Amalda bunday qiymat bu funksiyaga
    yetib kelmaydi: `ConfigClient._pick_miniapp()` avval `strip()`
    qiladi. Shu himoyani yozib qo'yamiz.
    """
    assert is_valid_miniapp_name("survey\n".strip()) is True


def test_none_ham_yaroqsiz_deb_qaraladi() -> None:
    """Sozlama umuman kelmasligi mumkin — bu xato emas, bo'sh qiymat."""
    assert is_valid_miniapp_name(None) is False  # type: ignore[arg-type]


def test_chegara_uzunliklari() -> None:
    assert is_valid_miniapp_name("a" * 3) is True
    assert is_valid_miniapp_name("a" * 30) is True
    assert is_valid_miniapp_name("a" * 2) is False
    assert is_valid_miniapp_name("a" * 31) is False


# ══════════════════════════════════════════════════════════════
#  miniapp_link — deep-link formati
# ══════════════════════════════════════════════════════════════


def test_havola_formati_shartnomadagidek() -> None:
    assert (
        miniapp_link(BOT, APP, TOKEN)
        == f"https://t.me/{BOT}/{APP}?startapp={TOKEN}"
    )


def test_havolada_token_startapp_parametrida() -> None:
    """`startapp` — Telegram uni `initData.start_param` ichida IMZOLAB
    beradi, ya'ni token soxtalashtirib bo'lmaydigan holda yetib boradi."""
    havola = miniapp_link(BOT, APP, TOKEN)

    assert havola.endswith(f"?startapp={TOKEN}")
    assert havola.count("?") == 1


def test_havola_https_va_tme_domenida() -> None:
    havola = miniapp_link(BOT, APP, TOKEN)

    assert havola.startswith("https://t.me/")


# ══════════════════════════════════════════════════════════════
#  survey_kb — ikki rejim
# ══════════════════════════════════════════════════════════════


def test_miniapp_rejimida_bitta_url_tugma() -> None:
    """Ball, izoh va sabab — hammasi Telegram ichidagi sahifada."""
    markup = survey_kb(BOT, TOKEN, miniapp_name=APP)

    assert len(markup.inline_keyboard) == 1
    qator = markup.inline_keyboard[0]
    assert len(qator) == 1

    tugma = qator[0]
    assert tugma.text == MINIAPP_BUTTON
    assert tugma.url == miniapp_link(BOT, APP, TOKEN)
    # URL tugma anonimlik uchun yaxshiroq: uni bosgani haqida Telegram
    # hech kimga hech narsa yubormaydi
    assert tugma.callback_data is None


def test_tugmalar_rejimida_beshta_rate_callback() -> None:
    markup = survey_kb(BOT, TOKEN, miniapp_name="")

    assert len(markup.inline_keyboard) == 1
    qator = markup.inline_keyboard[0]
    assert len(qator) == 5

    assert [t.text for t in qator] == list(DIGITS)
    assert [t.callback_data for t in qator] == [
        f"rate:{TOKEN}:{n}" for n in range(1, 6)
    ]
    assert all(t.url is None for t in qator)


def test_standart_holat_tugmalar_rejimi() -> None:
    """`miniapp_name` berilmasa — eski, ishlashi tekshirilgan oqim."""
    markup = survey_kb(BOT, TOKEN)

    assert len(markup.inline_keyboard[0]) == 5


def test_tugmalar_rejimida_shaxsiy_chatga_otish_tugmasi_yoq() -> None:
    """ATAYLAB olib tashlangan: mijoz botni alohida `/start` qilishi
    ortiqcha qadam edi va so'rovnoma shu yerda uzilib qolardi."""
    markup = survey_kb(BOT, TOKEN, miniapp_name="")

    hamma = [t for qator in markup.inline_keyboard for t in qator]
    assert all((t.callback_data or "").startswith("rate:") for t in hamma)
    assert not any((t.url or "") for t in hamma)


def test_har_rejimda_token_tugmaga_tushadi() -> None:
    """Token yo'qolsa javob qaysi so'rovnomaniki ekani bilinmay qolardi."""
    miniapp = survey_kb(BOT, TOKEN, miniapp_name=APP)
    tugmalar = survey_kb(BOT, TOKEN, miniapp_name="")

    assert TOKEN in miniapp.inline_keyboard[0][0].url
    assert all(TOKEN in t.callback_data for t in tugmalar.inline_keyboard[0])


# ══════════════════════════════════════════════════════════════
#  survey_text — hisoblagich matni
# ══════════════════════════════════════════════════════════════


def test_hech_kim_baho_bermaganda() -> None:
    for name in ("", APP):
        matn = survey_text(0, miniapp_name=name)

        assert "Hali hech kim baho bermadi" in matn


def test_javoblar_soni_matnda_korinadi() -> None:
    matn = survey_text(7, miniapp_name="")

    assert "7 kishi baho berdi" in matn


def test_hisoblagich_ikkala_rejimda_bir_xil() -> None:
    """Shakl va siqib yangilanishi (`services/throttle.py`) o'zgarmadi."""
    assert "12 kishi baho berdi" in survey_text(12, miniapp_name="")
    assert "12 kishi baho berdi" in survey_text(12, miniapp_name=APP)


def test_matnda_anonimlik_vadasi_bor() -> None:
    """Mijoz nega baho berishga rozi bo'lishini shu satrdan biladi."""
    for name in ("", APP):
        assert "anonim" in survey_text(3, miniapp_name=name)


def test_matnda_kim_baho_bergani_yozilmaydi() -> None:
    """Faqat UMUMIY son — hech qanday ism, ID yoki ro'yxat yo'q."""
    matn = survey_text(5, miniapp_name="")

    assert "@" not in matn
    assert matn.count("kishi") == 1


def test_ikki_rejim_matni_farq_qiladi() -> None:
    """Mini App'da davr eslatilmaydi — sahifaning o'zi tushuntiradi."""
    tugmalar = survey_text(0, miniapp_name="")
    miniapp = survey_text(0, miniapp_name=APP)

    assert tugmalar != miniapp
    assert "2 hafta" in tugmalar
    assert "2 hafta" not in miniapp


def test_deep_link_prefiksi_ozgarmadi() -> None:
    """Guruh tugmasi va shaxsiy chatdagi `/start` bitta formatdan
    foydalanadi — prefiks o'zgarsa eski havolalar ishlamay qoladi."""
    assert TOKEN_PREFIX == "srv_"
