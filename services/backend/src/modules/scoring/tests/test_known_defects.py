"""Auditda topilgan uchta xato — TUZATILDI, bu testlar qo'riqchi bo'lib qoldi.

Har bir test KUTILAYOTGAN, TO'G'RI xatti-harakatni yozadi. Ilgari ular
`xfail(strict=True)` bilan turgan edi; xato tuzatilgach belgi olib
tashlandi va endi ular oddiy regressiya testi: shakl yoki arifmetika
yana buzilsa suite darhol qizaradi.

Har bir xato pastda «nima bo'ladi» emas, «KIMGA nima yo'qotadi» tilida
izohlangan.
"""

import json

from src.modules.pipeline.tests.stubs import build_payload
from src.modules.scoring.application.score_writer import _blocks_payload
from src.modules.scoring.application.validator import (
    _validate_red_flags,
    validate,
)
from src.modules.scoring.domain.entities import BLOCK_MAX, ScoreBlock
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]


# ══════════════════════════════════════════════════════════════
#  6. Takroriy red flag dalili yo'qolmasin
#     (ilgari ikkinchi hodisa jimgina tashlab yuborilardi)
# ══════════════════════════════════════════════════════════════


def test_bir_xil_turdagi_ikki_qoidabuzarlik_ham_saqlanadi() -> None:
    """Qo'ng'iroqda ikki marta baqirilgan — ikkalasi ham ko'rinishi kerak."""
    raw = [
        {
            "type": "shouting",
            "severity": "high",
            "timestamp": "02:15",
            "quote": "Nega tushunmayapsiz?!",
        },
        {
            "type": "shouting",
            "severity": "high",
            "timestamp": "07:42",
            "quote": "Menga baqirmang dedim!",
        },
    ]

    clean, penalty, zeroed = _validate_red_flags(raw, rubric_red_flags=FLAGS)

    # Ikkala dalil ham saqlanadi — menejer nima bo'lganini to'liq ko'radi
    assert len(clean) == 2
    assert [f["timestamp"] for f in clean] == ["02:15", "07:42"]
    assert [f["quote"] for f in clean] == [
        "Nega tushunmayapsiz?!",
        "Menga baqirmang dedim!",
    ]
    # Jarima esa bir marta — ikki marta jarimalash ataylab qilinmaydi
    assert penalty == -20
    assert zeroed is False


def test_turli_turdagi_qoidabuzarliklar_saqlanadi() -> None:
    """Nazorat testi: turli turlar har biri o'z jarimasini oladi."""
    raw = [
        {"type": "shouting", "timestamp": "02:15", "quote": "a"},
        {"type": "badmouthing", "timestamp": "05:01", "quote": "b"},
    ]

    clean, penalty, _ = _validate_red_flags(raw, rubric_red_flags=FLAGS)

    assert [f["type"] for f in clean] == ["shouting", "badmouthing"]
    assert penalty == -35


# ══════════════════════════════════════════════════════════════
#  7. `BLOCK_MAX` faol rubrikadan olinadi, kodda qotirilmaydi
# ══════════════════════════════════════════════════════════════


def test_block_max_faol_rubrikaga_mos_keladi() -> None:
    """Kodda va rubrikada boshqa-boshqa maksimum bo'lsa, razrez foizi
    100% dan oshib ketadi va xodim haqiqiy natijasini ko'rmaydi."""
    rubric_max = {block["key"]: int(block["max"]) for block in BLOCKS}
    code_max = {block.value: value for block, value in BLOCK_MAX.items()}

    # Rubrikaning o'zi 100 ballga sozlangan (`RubricService._validate` talabi)
    assert sum(rubric_max.values()) == 100

    assert code_max == rubric_max
    assert sum(BLOCK_MAX.values()) == 100


def test_block_max_va_rubrika_bir_xil_bloklarni_biladi() -> None:
    """Nazorat testi: blok kalitlari ham mos bo'lishi shart."""
    assert {b["key"] for b in BLOCKS} == {b.value for b in ScoreBlock}


# ══════════════════════════════════════════════════════════════
#  8. `score_writer` yozgan `blocks` shakli iste'molchilarga mos keladi
# ══════════════════════════════════════════════════════════════


def _draft():
    raw = json.dumps(build_payload(BLOCKS, FLAGS, seed=11), ensure_ascii=False)
    return validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)


def test_yozilgan_bloklar_analitikadagi_float_bilan_moslashadi() -> None:
    """Yozilgan har bir qiymat TEKIS son bo'lishi kerak."""
    payload = _blocks_payload(_draft())

    # `analytics/application/services.py:block_breakdown` AYNAN shu tsiklni
    # bajaradi — filtrlashdan OLDIN, ya'ni `blocks` ga tushgan HAR qanday
    # begona kalit (masalan eski `_meta`) ham shu yerga kelib qolardi.
    totals: dict[str, list[float]] = {}
    for key, value in payload.items():
        totals.setdefault(key, []).append(float(value))

    assert totals["script"][0] == float(_draft().block_scores["script"])


def test_yozilgan_bloklar_barcha_rubrika_kalitlarini_oz_ichiga_oladi() -> None:
    """Nazorat testi: rubrikadagi har bir blok yozuvda bo'lishi shart."""
    payload = _blocks_payload(_draft())

    assert {b["key"] for b in BLOCKS} <= set(payload)
