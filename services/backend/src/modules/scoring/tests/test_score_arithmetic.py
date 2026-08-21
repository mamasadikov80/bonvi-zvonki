"""Ball arifmetikasi — kriteriya → blok → umumiy zanjiri.

Sof unit test: bazasiz, ilovasiz, kalitsiz.

NEGA MUHIM: LLM «bloklar 84, umumiy 96» deb qaytarishi mumkin va bu
yolg'on raqam bazaga tushsa, xodim noto'g'ri baholanadi — buni hech kim
sezmaydi. Shuning uchun validator modelning raqamiga ISHONMAYDI, uni
QAYTA hisoblaydi va mos kelmasa bahoni butunlay rad etadi.

`test_validator.py` javobning SHAKLINI tekshiradi; bu fayl esa
RAQAMLARNI: har bir ball qo'lda sanaladi va natija bilan solishtiriladi.
"""

import json
from typing import Any


from src.modules.scoring.application.validator import (
    validate,
)
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]

#: Rubrikadagi jarimalar — testda qo'lda hisoblash uchun
PENALTY = {f["type"]: int(f["penalty"]) for f in FLAGS}


def _criteria_points() -> dict[str, int]:
    """`{"A1": 5, "A2": 8, ...}` — har kriteriyaning maksimumi."""
    return {
        criterion["id"]: int(criterion["points"])
        for block in BLOCKS
        for criterion in block["criteria"]
    }


def _build(
    per_criterion: dict[str, int],
    *,
    red_flags: tuple[str, ...] = (),
    overall_override: int | None = None,
    block_score_override: dict[str, int] | None = None,
    model_penalty: int | None = None,
    na_ids: tuple[str, ...] = (),
) -> str:
    """Rubrikaga mos javob quradi — har kriteriya bali ANIQ berilgan.

    `stubs.build_payload` tasodifiy ball qo'yadi; bu yerda esa har bir
    raqam testda ko'rinib turishi kerak, chunki kutilayotgan natija
    qo'lda hisoblanadi.
    """
    blocks: dict[str, Any] = {}
    blocks_total = 0

    for block in BLOCKS:
        items = []
        block_total = 0
        for criterion in block["criteria"]:
            cid = criterion["id"]
            na = cid in na_ids
            score = 0 if na else per_criterion[cid]
            if not na:
                block_total += score
            items.append(
                {
                    "id": cid,
                    "score": score,
                    "verdict": "na" if na else "pass",
                    "evidence": f"[00:10] — dalil ({cid})",
                }
            )
        written = (block_score_override or {}).get(block["key"], block_total)
        blocks[block["key"]] = {"score": written, "criteria": items}
        blocks_total += written

    penalty = 0
    zeroed = False
    flag_items = []
    for flag_type in red_flags:
        penalty += PENALTY[flag_type]
        zeroed = zeroed or flag_type == "profanity"
        item: dict[str, Any] = {
            "type": flag_type,
            "severity": "high",
            "timestamp": "07:42",
            "quote": "iqtibos",
        }
        if model_penalty is not None:
            # Model o'zi jarima o'ylab topdi — validator buni olmasligi kerak
            item["penalty"] = model_penalty
        flag_items.append(item)

    overall = 0 if zeroed else max(0, min(100, blocks_total + penalty))

    return json.dumps(
        {
            "language_detected": "uz",
            "transcript_quality": "high",
            "blocks": blocks,
            "red_flags": flag_items,
            "outcome_signal": {
                "type": "follow_up",
                "products_mentioned": ["X-200"],
                "quantity_mentioned": 50,
                "confidence": 0.7,
                "evidence": "[00:58] — «ertaga aytaman»",
            },
            "client_sentiment": "neutral",
            "coaching_note": "E'tiroz bilan ishlashni kuchaytiring.",
            "confidence": 0.9,
            "call_scenario": "repeat_order" if na_ids else "new_client",
            "overall_score": overall if overall_override is None else overall_override,
        },
        ensure_ascii=False,
    )


def _check(raw: str):
    return validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)


# ══════════════════════════════════════════════════════════════
#  1. Kriteriya → blok → umumiy
# ══════════════════════════════════════════════════════════════


def test_kriteriya_ballari_blokka_va_umumiyga_yigiladi() -> None:
    """Har raqam qo'lda sanalgan: A=15, B=17, C=16, D=13 → 61."""
    points = {
        "A1": 5, "A2": 4, "A3": 3, "A4": 3,      # script      = 15
        "B1": 8, "B2": 5, "B3": 2, "B4": 2,      # communication = 17
        "C1": 6, "C2": 5, "C3": 5,               # resolution  = 16
        "D1": 4, "D2": 3, "D3": 3, "D4": 3,      # sales_skill = 13
    }

    draft = _check(_build(points))

    assert draft.block_scores == {
        "script": 15,
        "communication": 17,
        "resolution": 16,
        "sales_skill": 13,
    }
    assert draft.blocks_total == 61
    assert draft.overall == 61


def test_blok_bali_kriteriyalardan_hisoblanadi() -> None:
    """Blok «20» deb yozilgan, kriteriyalari esa 15 — 15 olinadi.

    ⚠️ ILGARI bunday javob rad etilardi. `na` paydo bo'lgach model
    tashlangan mezondan keyin blok maksimumini «to'ldirishga» urinib
    yig'indini oshirib yozadigan bo'ldi va javoblar yo'q qilinaverdi.
    Yig'indi — hisoblanadigan qiymat; modelning da'vosi ogohlantirish
    sifatida yoziladi, ballga ta'sir qilmaydi."""
    points = dict.fromkeys(_criteria_points(), 0) | {
        "A1": 5, "A2": 4, "A3": 3, "A4": 3
    }

    draft = _check(_build(points, block_score_override={"script": 20}))

    assert draft.blocks["script"]["raw_score"] == 15
    assert draft.overall == 15
    assert draft.warnings


def test_model_yozgan_umumiy_ball_etiborsiz_qoldiriladi() -> None:
    """Model «96» deb yozdi, bloklar 61 — natija 61.

    ⚠️ ILGARI bunday javob RAD ETILARDI. Endi `overall_score` modeldan
    umuman so'ralmaydi: hisobda bo'lish bor (qo'llanilgan mezonlar
    ichidagi foiz) va uni modeldan talab qilish javobning rad etilishi
    hamda qayta so'rov — ya'ni ikki baravar pul — degani edi.
    Model yozib yuborgan qiymat esa e'tiborsiz qoldiriladi: umumiy
    ballning yagona egasi — validator.
    """
    points = {
        "A1": 5, "A2": 4, "A3": 3, "A4": 3,
        "B1": 8, "B2": 5, "B3": 2, "B4": 2,
        "C1": 6, "C2": 5, "C3": 5,
        "D1": 4, "D2": 3, "D3": 3, "D4": 3,
    }

    draft = _check(_build(points, overall_override=96))

    assert draft.overall == 61


def test_hamma_kriteriya_notoliq_bolsa_ham_zanjir_saqlanadi() -> None:
    """Nol ballar ham qo'shiladi — «kriteriya berilmadi» bilan adashmasin."""
    points = dict.fromkeys(_criteria_points(), 0)

    draft = _check(_build(points))

    assert draft.blocks_total == 0
    assert draft.overall == 0
    assert draft.zeroed is False  # nol ball ≠ red flag bilan nollangan


# ══════════════════════════════════════════════════════════════
#  2. Chegaralar: 0 va 100
# ══════════════════════════════════════════════════════════════


def test_toliq_bajarilgan_qongiroq_aniq_100_ball_oladi() -> None:
    """Rubrika 100 ballga sozlangan — natija undan OSHMAYDI."""
    draft = _check(_build(_criteria_points()))

    assert draft.blocks_total == 100
    assert draft.overall == 100
    assert draft.overall <= 100


def test_bir_necha_jarima_birikkanda_ball_manfiy_bolmaydi() -> None:
    """−25 −20 −15 −15 −10 = −85, bloklar 61 → 61−85 = −24 → 0."""
    points = {
        "A1": 5, "A2": 4, "A3": 3, "A4": 3,
        "B1": 8, "B2": 5, "B3": 2, "B4": 2,
        "C1": 6, "C2": 5, "C3": 5,
        "D1": 4, "D2": 3, "D3": 3, "D4": 3,
    }
    flags = (
        "off_policy_deal",
        "shouting",
        "unrealistic_promise",
        "badmouthing",
        "ignored_complaint",
    )

    draft = _check(_build(points, red_flags=flags))

    assert draft.penalty_total == -85
    assert draft.blocks_total == 61
    assert draft.overall == 0  # −24 emas
    assert draft.overall >= 0


def test_toliq_ball_ustiga_jarima_tushsa_ayiriladi() -> None:
    """100 − 20 = 80. Chegara ishlaydi, lekin jarimani yutmaydi."""
    draft = _check(_build(_criteria_points(), red_flags=("shouting",)))

    assert draft.blocks_total == 100
    assert draft.penalty_total == -20
    assert draft.overall == 80


def test_haqorat_barcha_ballni_noldan_boshlab_yoqadi() -> None:
    """`zeroes_score` — ayirish emas, TO'G'RIDAN-TO'G'RI nol."""
    draft = _check(_build(_criteria_points(), red_flags=("profanity",)))

    assert draft.zeroed is True
    assert draft.overall == 0


# ══════════════════════════════════════════════════════════════
#  3. Jarima RUBRIKADAN olinadi
# ══════════════════════════════════════════════════════════════


def test_model_ozi_yozgan_jarima_etiborsiz_qoldiriladi() -> None:
    """Model «−1» deb yozsa ham rubrikadagi −20 qo'llanadi.

    Aks holda model o'ziga qulay jarima o'ylab topib ballni ko'tarardi.
    """
    draft = _check(
        _build(_criteria_points(), red_flags=("shouting",), model_penalty=-1)
    )

    assert draft.red_flags[0]["penalty"] == PENALTY["shouting"] == -20
    assert draft.penalty_total == -20
    assert draft.overall == 80  # 100 − 20, model aytgan 100 − 1 = 99 EMAS


def test_model_haddan_tashqari_jarima_yozsa_ham_rubrika_yengadi() -> None:
    """Teskari yo'nalish: model «−999» yozdi, natija baribir −10."""
    draft = _check(
        _build(
            _criteria_points(),
            red_flags=("ignored_complaint",),
            model_penalty=-999,
        )
    )

    assert draft.penalty_total == -10
    assert draft.overall == 90


def test_bir_necha_jarima_rubrikadagi_qiymatlar_yigindisi() -> None:
    """Har bayroq o'z rubrika qiymatini oladi — modelniki emas."""
    flags = ("off_policy_deal", "ignored_complaint")

    draft = _check(
        _build(_criteria_points(), red_flags=flags, model_penalty=0)
    )

    assert [f["penalty"] for f in draft.red_flags] == [-25, -10]
    assert draft.penalty_total == PENALTY["off_policy_deal"] + PENALTY[
        "ignored_complaint"
    ]
    assert draft.overall == 65


def test_jarima_yorligi_ham_rubrikadan_keladi() -> None:
    """Menejer o'zbekcha yorliqni ko'radi — model matni emas."""
    draft = _check(_build(_criteria_points(), red_flags=("badmouthing",)))

    expected = next(f for f in FLAGS if f["type"] == "badmouthing")["label"]
    assert draft.red_flags[0]["label"] == expected
