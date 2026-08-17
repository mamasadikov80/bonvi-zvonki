"""So'rovnoma domenining sof funksiyalari — bazasiz, ilovasiz.

Bu uchtasi kichkina ko'rinadi, lekin uchalasi ham tizimning eng nozik
va'dalarini ushlab turadi:

  • `new_survey_token()`  — TOKEN KIRISH KALITI. Uni topgan odam
    boshqa mijozning so'rovnomasini to'ldira oladi.
  • `normalize_red_flags()` — bazaga yoziladigan kalitlar. Noma'lum
    kalit o'tib ketsa, u yozuvda abadiy qolib, hech qanday yorliqqa
    mos kelmaydi.
  • `respondent_hash()`  — anonim dedup. Formulasi BOT dagisi bilan
    bayt-ba-bayt bir xil bo'lishi shart, aks holda bir odam bitta
    so'rovnomaga ikki marta baho qo'yadi.
"""

import pytest

from src.modules.surveys.application.webapp import HASH_LENGTH, respondent_hash
from src.modules.surveys.domain.entities import (
    RED_FLAG_LABELS,
    SURVEY_TOKEN_MAX_LEN,
    new_survey_token,
    normalize_red_flags,
)

# ══════════════════════════════════════════════════════════════
#  new_survey_token()
# ══════════════════════════════════════════════════════════════


def test_token_takrorlanmaydi() -> None:
    """Ikkita bir xil token = ikkinchi so'rovnoma yozilmaydi
    (`surveys.token` ustuni UNIQUE), ya'ni bu shunchaki nazariy xavf emas."""
    tokens = {new_survey_token() for _ in range(500)}

    assert len(tokens) == 500


def test_token_uzunligi_barqaror_va_ustunga_sigadi() -> None:
    """`surveys.token` — `String(64)`. Uzunlik suzib ketsa, token
    bazaga yozilayotganda kesilib, deep-link ishlamay qoladi."""
    lengths = {len(new_survey_token()) for _ in range(50)}

    assert len(lengths) == 1
    assert lengths.pop() <= SURVEY_TOKEN_MAX_LEN


def test_token_url_uchun_xavfsiz() -> None:
    """Token `t.me/<bot>?start=srv_<token>` havolasiga tushadi —
    qochirish talab qiladigan belgi bo'lmasligi kerak."""
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )

    for _ in range(50):
        assert set(new_survey_token()) <= allowed


# ══════════════════════════════════════════════════════════════
#  normalize_red_flags()
# ══════════════════════════════════════════════════════════════


def test_notanish_kalit_rad_etiladi() -> None:
    """Noma'lum kalit bazaga tushsa — u yerdan hech qachon ketmaydi
    va hech qanday yorliqqa mos kelmaydi."""
    with pytest.raises(ValueError) as exc:
        normalize_red_flags(["rude", "hech_qanday_kalit"])

    # Xabarda AYNAN noto'g'ri kalit turishi kerak — 422 shu matnni oladi
    assert "hech_qanday_kalit" in str(exc.value)
    assert "rude" not in str(exc.value)


def test_dublikat_tozalanadi_va_tartib_saqlanadi() -> None:
    """Tartib ma'lumot beradi: mijoz avval nimani belgilagani muhim."""
    result = normalize_red_flags(["late_reply", "rude", "late_reply", "rude"])

    assert result == ["late_reply", "rude"]


def test_bosh_royxat_bosh_qaytadi() -> None:
    """`None` ham, `[]` ham bir xil — «hech narsa belgilanmagan»."""
    assert normalize_red_flags(None) == []
    assert normalize_red_flags([]) == []


def test_barcha_registr_kalitlari_qabul_qilinadi() -> None:
    """Registr o'zi bilan zid bo'lmasligi kerak: `GET /surveys/red-flags`
    bergan har bir kalit qaytib kelganda qabul qilinishi shart."""
    keys = list(RED_FLAG_LABELS)

    assert normalize_red_flags(keys) == keys


# ══════════════════════════════════════════════════════════════
#  respondent_hash()
# ══════════════════════════════════════════════════════════════


def test_bir_xil_kirish_bir_xil_hash_beradi() -> None:
    """Dedup shunga tayanadi: bir odam ikkinchi marta bosganda AYNAN
    o'sha hash chiqishi kerak, aks holda ikkinchi baho o'tib ketadi."""
    first = respondent_hash("token-abc", 12345)
    second = respondent_hash("token-abc", 12345)

    assert first == second
    assert len(first) == HASH_LENGTH


def test_turli_tokenda_hash_ham_turlicha() -> None:
    """MAXFIYLIK SHARTI: har so'rovnomaning tokeni har xil, demak bir
    odamning turli so'rovnomalardagi izlari bir-biriga BOG'LANMAYDI.
    Aks holda «bu odam o'tgan safar necha yulduz qo'ygan edi» degan
    savolga javob topiladi va anonimlik yo'qoladi."""
    assert respondent_hash("token-a", 12345) != respondent_hash("token-b", 12345)


def test_turli_odam_turli_hash() -> None:
    assert respondent_hash("token-abc", 111) != respondent_hash("token-abc", 222)


def test_hash_telegram_identifikatorini_ochib_qomaydi() -> None:
    """Hash — bir tomonlama: ichida ochiq matnda na token, na Telegram
    identifikatori qolmaydi."""
    digest = respondent_hash("token-abc", 987654321)

    assert "token-abc" not in digest
    assert "987654321" not in digest
    assert set(digest) <= set("0123456789abcdef")
