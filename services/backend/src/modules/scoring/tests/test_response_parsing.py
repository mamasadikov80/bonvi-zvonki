"""LLM javobini o'qish va ro'yxatdagi qiymatlarni tekshirish.

Sof unit test: bazasiz, ilovasiz.

IKKI XIL XATO
  · SHAKL — model JSON'ni ```json ... ``` ichiga o'raydi yoki oldidan
    bir-ikki jumla yozadi. Bu KECHIRILADI: matn ochiladi, JSON o'qiladi.
    Aks holda mukammal baho shunchaki formatlash tufayli yo'qolardi.
  · MA'NO — `sentiment`, `outcome`, `quality` uchun faqat ro'yxatdagi
    qiymatlar. Bular UI'da rang va filtr bo'lib ishlatiladi: model
    «очень позитивный» yozib yuborsa, dashboard'da jimgina bo'sh
    ustun paydo bo'lardi. Shuning uchun RAD ETILADI.
"""

import json

import pytest

from src.modules.pipeline.tests.stubs import build_payload
from src.modules.scoring.application.validator import (
    VALID_OUTCOMES,
    VALID_QUALITY,
    VALID_SENTIMENTS,
    ScoreValidationError,
    loads,
    validate,
)
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]


def _payload(**overrides) -> dict:
    data = build_payload(BLOCKS, FLAGS, seed=42)
    data.update(overrides)
    return data


def _check(data: dict | str):
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)


# ══════════════════════════════════════════════════════════════
#  4. ```json ... ``` va boshqa o'ramlar
# ══════════════════════════════════════════════════════════════


def test_json_belgisi_bilan_oralgan_javob_ochiladi() -> None:
    body = json.dumps({"overall_score": 61}, ensure_ascii=False)

    assert loads(f"```json\n{body}\n```") == {"overall_score": 61}


def test_tilsiz_uchlik_tirnoq_ham_ochiladi() -> None:
    """Ba'zi modellar `json` so'zini yozmaydi — bir xil ishlashi kerak."""
    assert loads('```\n{"a": 1}\n```') == {"a": 1}


def test_oram_atrofidagi_bosh_joy_halaqit_bermaydi() -> None:
    assert loads('  \n ```json  \n {"a": 1} \n``` \n ') == {"a": 1}


def test_oralgan_toliq_javob_validatordan_otadi() -> None:
    """Faqat `loads` emas — butun zanjir o'ramni ko'tarishi kerak."""
    body = json.dumps(_payload(), ensure_ascii=False)

    draft = _check(f"```json\n{body}\n```")

    assert draft.overall == draft.blocks_total


def test_javob_oldidagi_jumla_kechiriladi() -> None:
    """«Mana natija:» — oxirgi imkoniyat: birinchi `{` dan oxirgi `}` gacha."""
    body = json.dumps({"overall_score": 61}, ensure_ascii=False)

    assert loads(f"Mana natija:\n{body}\nUmid qilamanki foydali bo'ldi.") == {
        "overall_score": 61
    }


def test_bosh_javob_ozbekcha_sabab_bilan_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        loads("   \n  ")

    assert "bo'sh javob" in exc.value.message


def test_royxat_qaytarilsa_rad_etiladi() -> None:
    """JSON to'g'ri, lekin obyekt emas — bloklarni qayerdan olamiz?"""
    with pytest.raises(ScoreValidationError) as exc:
        loads("[1, 2, 3]")

    assert "obyekt" in exc.value.message


def test_yopilmagan_json_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError):
        loads('```json\n{"blocks": {\n```')


# ══════════════════════════════════════════════════════════════
#  5. Ro'yxatdagi qiymatlar (VALID_*)
# ══════════════════════════════════════════════════════════════


def test_notogri_sentiment_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        _check(_payload(client_sentiment="очень позитивный"))

    assert "client_sentiment" in exc.value.message
    # Xabar ruxsat etilganlarni ham ko'rsatsin — admin nima kutilishini bilsin
    assert "positive" in exc.value.message


@pytest.mark.parametrize("value", VALID_SENTIMENTS)
def test_royxatdagi_har_sentiment_qabul_qilinadi(value: str) -> None:
    assert _check(_payload(client_sentiment=value)).sentiment == value


def test_sentiment_katta_harf_va_boshjoyga_bardosh_beradi() -> None:
    """«  NEGATIVE » — ma'no to'g'ri, shakl e'tiborsiz."""
    assert _check(_payload(client_sentiment="  NEGATIVE ")).sentiment == "negative"


def test_notogri_outcome_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        _check(
            _payload(
                outcome_signal={"type": "sotildi", "confidence": 0.5}
            )
        )

    assert "outcome_signal.type" in exc.value.message


@pytest.mark.parametrize("value", VALID_OUTCOMES)
def test_royxatdagi_har_outcome_qabul_qilinadi(value: str) -> None:
    draft = _check(_payload(outcome_signal={"type": value, "confidence": 0.5}))

    assert draft.outcome_signal["type"] == value


def test_outcome_obyekt_bolmasa_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        _check(_payload(outcome_signal="follow_up"))

    assert "outcome_signal" in exc.value.message


def test_notogri_transcript_quality_rad_etiladi() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        _check(_payload(transcript_quality="o'rtacha"))

    assert "transcript_quality" in exc.value.message


@pytest.mark.parametrize("value", VALID_QUALITY)
def test_royxatdagi_har_quality_qabul_qilinadi(value: str) -> None:
    assert _check(_payload(transcript_quality=value)).transcript_quality == value


def test_bosh_sentiment_ham_rad_etiladi() -> None:
    """Maydon umuman bo'lmasa — «neutral» deb taxmin qilinmaydi."""
    data = _payload()
    data.pop("client_sentiment")

    with pytest.raises(ScoreValidationError):
        _check(data)


def test_notanish_til_other_ga_aylanadi() -> None:
    """Til — ro'yxatdan tashqarida bo'lsa RAD ETILMAYDI, `other` bo'ladi.

    Sabab: til bahoning to'g'riligiga ta'sir qilmaydi, faqat statistika
    uchun. Butun bahoni shu tufayli yo'qotish mantiqsiz bo'lardi.
    """
    assert _check(_payload(language_detected="tj")).language_detected == "other"
    assert _check(_payload(language_detected="")).language_detected == "mixed"
