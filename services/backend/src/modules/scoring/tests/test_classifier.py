"""Qo'ng'iroq turini aniqlash — javobni o'qish va xavfsiz standartlar.

NEGA BU MUHIM. Tur BAHOLANADIMI degan savolni hal qiladi. Ikki xato
ham qimmat, lekin BIR XIL EMAS:

  · savdo qo'ng'irog'i «internal» deb o'qilsa — u baholanmaydi va
    xodimning ishi hisobga olinmay qoladi (JIMGINA yo'qotish);
  · ichki suhbat «sales» deb o'qilsa — savdo rubrikasi unga nol
    qo'yadi va o'rtachani pasaytiradi (ko'rinadigan zarar).

Shuning uchun tushunarsiz javobda `unclear` tanlanadi: u ham
baholanmaydi, lekin ekranda ochiq ko'rinadi va sababi yoziladi.
Qo'lda tuzatish yo'q — demak noto'g'ri tur JIMGINA o'tib ketmasligi
kerak.
"""

import pytest

from src.modules.calls.domain.entities import CallType
from src.modules.scoring.application.classifier import (
    ClassificationError,
    build_user_prompt,
    parse,
)


def _json(**fields) -> str:
    import json

    base = {
        "call_type": "sales",
        "confidence": 0.9,
        "reason": "Mijoz narx so'radi",
        "misconduct": False,
    }
    base.update(fields)
    return json.dumps(base, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
#  Turlar va baholanishi
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("xom", "kutilgan", "baholanadimi"),
    [
        ("sales", CallType.SALES, True),
        ("service", CallType.SERVICE, False),
        ("internal", CallType.INTERNAL, False),
        ("personal", CallType.PERSONAL, False),
        ("unclear", CallType.UNCLEAR, False),
    ],
)
def test_faqat_savdo_baholanadi(xom, kutilgan, baholanadimi) -> None:
    """⚠️ ASOSIY QOIDA: `sales` dan boshqa hech nima baholanmaydi.

    Kimdir kelajakda `service` ni ham baholashga qo'shsa, bu test
    darhol yiqiladi — o'zgarish ONGLI bo'lishi kerak.
    """
    result = parse(_json(call_type=xom))
    assert result.call_type is kutilgan
    assert result.scorable is baholanadimi


def test_notanish_tur_unclear_boladi() -> None:
    """Model o'ylab topgan tur — taxmin qilmaymiz, baholamaymiz ham."""
    result = parse(_json(call_type="marketing"))
    assert result.call_type is CallType.UNCLEAR
    assert result.scorable is False


def test_tur_yozilmagan_bolsa_unclear() -> None:
    result = parse('{"confidence": 0.8, "reason": "", "misconduct": false}')
    assert result.call_type is CallType.UNCLEAR


# ══════════════════════════════════════════════════════════════
#  Ishonch va sabab
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("xom", "kutilgan"),
    [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (1.7, 1.0), (-3, 0.0), ("yo'q", 0.0)],
)
def test_ishonch_chegaradan_chiqmaydi(xom, kutilgan) -> None:
    """Buzuq qiymat butun bosqichni yiqitmasligi kerak."""
    assert parse(_json(confidence=xom)).confidence == kutilgan


def test_sabab_saqlanadi_va_qisqartiriladi() -> None:
    """Sabab — qo'lda tuzatish yo'qligining o'rnini bosadigan narsa.

    Menejer nega shu tur tanlangani o'qib, xato bo'lsa «Qayta baholash»
    ni bosadi. Ustun 300 belgi, shuning uchun kesiladi."""
    uzun = "x" * 500
    result = parse(_json(reason=uzun))
    assert len(result.reason) == 300


# ══════════════════════════════════════════════════════════════
#  Xavfsizlik bayrog'i
# ══════════════════════════════════════════════════════════════


def test_qopollik_bayrogi_oqiladi() -> None:
    """Baholanmagan qo'ng'iroqda ham qo'pollik ko'rinmay qolmasligi kerak.

    Ichki suhbat baholanmaydi, ya'ni rubrikadagi qoidabuzarlik
    tekshiruvi ham ishlamaydi. Shu bayroq — yagona qolgan himoya."""
    result = parse(
        _json(call_type="internal", misconduct=True, misconduct_note="So'kindi")
    )
    assert result.misconduct is True
    assert result.misconduct_note == "So'kindi"
    assert result.scorable is False


def test_bayroq_yozilmasa_false() -> None:
    result = parse('{"call_type": "sales", "confidence": 1, "reason": "ok"}')
    assert result.misconduct is False
    assert result.misconduct_note is None


# ══════════════════════════════════════════════════════════════
#  Buzuq javob
# ══════════════════════════════════════════════════════════════


def test_kod_blokiga_oralgan_json_oqiladi() -> None:
    """Ba'zi modellar JSON ni ```json ... ``` ichiga o'raydi."""
    result = parse('```json\n{"call_type": "internal", "confidence": 0.9, '
                   '"reason": "sklad", "misconduct": false}\n```')
    assert result.call_type is CallType.INTERNAL


@pytest.mark.parametrize("xom", ["", "salom", "{buzuq", "[1,2,3]"])
def test_tushunarsiz_javob_xato_beradi(xom) -> None:
    """Jimgina `unclear` qilib qo'ymaydi — bu MODEL nosozligi.

    Bosqich xato bilan tugaydi va `with_backoff` qayta uradi. Aks
    holda tarmoq uzilishi «turi aniqlanmadi» bo'lib ko'rinardi."""
    with pytest.raises(ClassificationError):
        parse(xom)


# ══════════════════════════════════════════════════════════════
#  Prompt
# ══════════════════════════════════════════════════════════════


def test_promptda_transkript_va_yonalish_bor() -> None:
    prompt = build_user_prompt(
        transcript="[00:00] SPEAKER_0: Salom", duration_sec=125, direction="outbound"
    )
    assert "SPEAKER_0: Salom" in prompt
    assert "Chiquvchi" in prompt
    assert "2 daq 5 son" in prompt


def test_kiruvchi_yonalish_ham_korsatiladi() -> None:
    prompt = build_user_prompt(transcript="matn", duration_sec=10, direction="inbound")
    assert "Kiruvchi" in prompt
