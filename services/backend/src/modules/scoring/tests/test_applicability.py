"""«Taalluqli emas» (`na`) — qisqa, takroriy suhbat haqqoniy baholanadi.

NEGA BU FAYL BOR. Bonvi mijozlarining aksariyati — eski mijoz. Ular
skript bo'yicha gaplashmaydi: «akajon, menga 50 ta chiqarib qo'ying»
deb 30 soniyada tugatadi. Bunday suhbatda ehtiyojni aniqlash ham,
mahsulotni taqdim etish ham, upsell ham TALAB QILINMAYDI.

Ilgari rubrika baribir to'liq qo'llanardi va xodim aybsiz holda 40–50
ball olardi — past ball xodim haqida emas, rubrikaning o'rinsizligi
haqida gapirardi. Endi bunday mezon nol olmaydi, u hisobdan chiqadi.

Bu fayl to'rt narsani qulflaydi:
  1. `na` mezon ball hisobiga KIRMAYDI (na nol, na maksimum);
  2. blok ko'rsatkichi qo'llanilganlar ichida hisoblanadi;
  3. `na` faqat `optional: true` mezonga qo'yiladi — aks holda hamma
     narsani tashlab yuborish mumkin bo'lardi;
  4. qo'llanilganlar juda kam qolsa javob RAD ETILADI.
"""

import json
from typing import Any

import pytest

from src.modules.scoring.application.validator import (
    MIN_APPLICABLE_POINTS,
    ScoreValidationError,
    validate,
)
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]

#: Standart rubrikada `na` QO'YIB BO'LMAYDIGAN mezonlar yig'indisi.
#: Salomlashish (5) + muomala (25) + savolga javob (10) + keyingi
#: qadam (5 + 6) = 51.
MAJBURIY_BALL = sum(
    int(c["points"])
    for b in BLOCKS
    for c in b["criteria"]
    if not c.get("optional")
)


def _points() -> dict[str, int]:
    return {
        c["id"]: int(c["points"]) for b in BLOCKS for c in b["criteria"]
    }


def _build(*, na: tuple[str, ...] = (), scores: dict[str, int] | None = None) -> str:
    """Javob quradi: `na` dagilar tashlanadi, qolganlari to'liq ball."""
    maks = _points()
    blocks: dict[str, Any] = {}

    for block in BLOCKS:
        items = []
        block_total = 0
        for criterion in block["criteria"]:
            cid = criterion["id"]
            if cid in na:
                items.append(
                    {
                        "id": cid,
                        "score": 0,
                        "verdict": "na",
                        "evidence": "Mijoz aniq buyurtma berdi — bu bosqich "
                        "talab qilinmadi",
                    }
                )
                continue
            score = (scores or {}).get(cid, maks[cid])
            block_total += score
            items.append(
                {
                    "id": cid,
                    "score": score,
                    "verdict": "pass",
                    "evidence": f"[00:10] — dalil ({cid})",
                }
            )
        blocks[block["key"]] = {"score": block_total, "criteria": items}

    return json.dumps(
        {
            "language_detected": "uz",
            "transcript_quality": "high",
            "blocks": blocks,
            "red_flags": [],
            "outcome_signal": {"type": "order_agreed", "confidence": 0.9},
            "client_sentiment": "positive",
            "coaching_note": "Tez va aniq javob berdingiz.",
            "confidence": 0.9,
            "call_scenario": "repeat_order",
        },
        ensure_ascii=False,
    )


def _check(raw: str):
    return validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)


# ══════════════════════════════════════════════════════════════
#  1. Qisqa takroriy buyurtma — to'liq ball olishi MUMKIN
# ══════════════════════════════════════════════════════════════


def test_qisqa_buyurtma_suhbati_jazolanmaydi() -> None:
    """⚠️ ASOSIY KAFOLAT — shu o'zgarishning butun maqsadi.

    Eski mijoz «50 ta chiqaring» dedi, xodim hurmat bilan qabul qildi
    va sanani aytdi. Ehtiyojni aniqlash, mahsulot taqdimoti, e'tiroz,
    upsell va qiymat argumenti — hech biri talab qilinmadi.

    ILGARI bu qo'ng'iroq 100 dan 51 ball olardi (34 ball «bajarilmagan»
    deb yozilardi). Endi — 100, chunki qo'llanilganining hammasi
    bajarilgan."""
    tashlangan = ("A2", "A3", "C2", "C3", "D1", "D2", "D4")

    draft = _check(_build(na=tashlangan))

    assert draft.overall == 100
    assert draft.na_criteria == list(tashlangan)
    assert draft.applicable_points == MAJBURIY_BALL == 51


def test_taalluqli_bolmagan_mezon_nol_ham_olmaydi() -> None:
    """`na` — «hisobga kirmaydi», «nol» EMAS.

    Farq blok ko'rsatkichida ko'rinadi: «Skript» blokida A2 (8) va A3
    (7) tashlansa, qolgani 10 balldan iborat. Xodim o'sha 10 tasini
    to'liq olgan bo'lsa — ko'rsatkich 25/25, 10/25 emas."""
    draft = _check(_build(na=("A2", "A3")))

    assert draft.blocks["script"]["applicable_max"] == 10
    assert draft.blocks["script"]["raw_score"] == 10
    assert draft.block_scores["script"] == 25


def test_qollanilganlar_ichida_yarim_ball_yarim_korsatkich() -> None:
    """Qo'llanilganining yarmi bajarilsa — ko'rsatkich ham yarmi."""
    # «Skript» blokida faqat A1 (5) va A4 (5) qoladi, xodim 5 ball oldi
    draft = _check(_build(na=("A2", "A3"), scores={"A1": 5, "A4": 0}))

    assert draft.blocks["script"]["applicable_max"] == 10
    assert draft.blocks["script"]["raw_score"] == 5
    assert draft.block_scores["script"] == 13  # 25 × 5/10 = 12.5 → 13


# ══════════════════════════════════════════════════════════════
#  2. Himoyalar — `na` yashirin ball ko'tarishga aylanmasin
# ══════════════════════════════════════════════════════════════


def test_majburiy_mezonni_tashlab_ketib_bolmaydi() -> None:
    """Salomlashish har qanday suhbatda tekshiriladi.

    Aks holda model istagan mezonni hisobdan chiqarib yuborardi va
    past ball umuman chiqmasdi."""
    with pytest.raises(ScoreValidationError) as exc:
        _check(_build(na=("A1",)))

    assert "A1" in exc.value.message
    assert "har qanday suhbatda" in exc.value.message.lower()


def test_hammasini_tashlab_ketishga_yol_yopiq() -> None:
    """Barcha ixtiyoriy mezonlar tashlansa ham 51 ball qoladi.

    Chegara `MIN_APPLICABLE_POINTS` (40) dan yuqori, ya'ni normal ish
    unga tegmaydi. Tegilsa — bu javob emas, nosozlik."""
    assert MAJBURIY_BALL > MIN_APPLICABLE_POINTS


def test_na_mezonga_qoyilgan_ball_hisobga_kirmaydi() -> None:
    """`na` + ball — o'z-o'ziga zid javob, lekin RAD ETILMAYDI.

    Bunday mezon hisobga umuman kirmaydi, ya'ni modelning u yerga
    nima yozgani ahamiyatsiz. Butun bahoni shu sabab tashlab yuborish
    qimmat (qayta so'rov = qayta to'lov) va befoyda bo'lardi."""
    payload = json.loads(_build(na=("A2",)))
    for item in payload["blocks"]["script"]["criteria"]:
        if item["id"] == "A2":
            item["score"] = 8

    draft = _check(json.dumps(payload, ensure_ascii=False))

    a2 = next(c for c in draft.blocks["script"]["criteria"] if c["id"] == "A2")
    assert a2["score"] == 0
    assert a2["applicable"] is False
    assert draft.blocks["script"]["applicable_max"] == 17  # 25 − 8


def test_blok_bali_na_larni_qoshsa_ham_hisob_ozgarmaydi() -> None:
    """Model `na` mezonning ballini blok yig'indisiga qo'shib yuborsa —
    yig'indi baribir kriteriyalardan qayta hisoblanadi."""
    toza = _check(_build(na=("A2",)))
    payload = json.loads(_build(na=("A2",)))
    payload["blocks"]["script"]["score"] += 8

    draft = _check(json.dumps(payload, ensure_ascii=False))

    assert draft.overall == toza.overall
    assert draft.warnings


# ══════════════════════════════════════════════════════════════
#  3. Butunlay taalluqli bo'lmagan blok
# ══════════════════════════════════════════════════════════════


def test_toliq_na_blok_korsatilmaydi() -> None:
    """«Savdo qobiliyati» blokida D3 majburiy, shuning uchun bu blok
    hech qachon butunlay tushib qolmaydi — lekin mexanizm ishlashi
    kerak: `applicable_max = 0` bo'lgan blok razrezga TUSHMAYDI.

    Uni 0 deb chizish xodimni aybdor ko'rsatardi, maksimum deb chizish
    esa tekshirilmagan ish uchun ball berardi."""
    # Sun'iy rubrika: bitta blokning hamma mezoni ixtiyoriy
    bloklar = [
        {
            "key": "script",
            "label": "Skript",
            "max": 50,
            "criteria": [
                {"id": "A1", "label": "Salom", "points": 50, "optional": False}
            ],
        },
        {
            "key": "sales_skill",
            "label": "Savdo",
            "max": 50,
            "criteria": [
                {"id": "D1", "label": "Upsell", "points": 50, "optional": True}
            ],
        },
    ]
    payload = {
        "language_detected": "uz",
        "transcript_quality": "high",
        "blocks": {
            "script": {
                "score": 40,
                "criteria": [
                    {
                        "id": "A1",
                        "score": 40,
                        "verdict": "partial",
                        "evidence": "[00:01] salom",
                    }
                ],
            },
            "sales_skill": {
                "score": 0,
                "criteria": [
                    {
                        "id": "D1",
                        "score": 0,
                        "verdict": "na",
                        "evidence": "Mijoz o'zi buyurtma berdi",
                    }
                ],
            },
        },
        "red_flags": [],
        "outcome_signal": {"type": "order_agreed", "confidence": 0.9},
        "client_sentiment": "positive",
        "coaching_note": "Yaxshi.",
        "confidence": 0.9,
        "call_scenario": "repeat_order",
    }

    draft = validate(
        json.dumps(payload, ensure_ascii=False),
        rubric_blocks=bloklar,
        rubric_red_flags=FLAGS,
    )

    assert "sales_skill" not in draft.block_scores, "razrezga tushmasin"
    assert draft.applicable_max == 50, "faqat qo'llanilgan blok maksimumi"
    assert draft.overall == 80, "40/50 → 80"


# ══════════════════════════════════════════════════════════════
#  4. Jarima normallashtirilgan ball USTIGA tushadi
# ══════════════════════════════════════════════════════════════


def test_jarima_normallashtirishdan_keyin_ayiriladi() -> None:
    """Baqirish −20: qisqa suhbatda ham jarima to'liq ta'sir qiladi."""
    payload = json.loads(_build(na=("A2", "A3", "C2", "C3", "D1", "D2", "D4")))
    payload["red_flags"] = [
        {
            "type": "shouting",
            "severity": "high",
            "timestamp": "01:12",
            "quote": "NEGA HALIGACHA YUBORMADINGIZ",
        }
    ]

    draft = _check(json.dumps(payload, ensure_ascii=False))

    assert draft.penalty_total == -20
    assert draft.overall == 80


# ══════════════════════════════════════════════════════════════
#  5. Eski rubrika (bayroqsiz) — ESKICHA ishlaydi
# ══════════════════════════════════════════════════════════════


def test_bayroqsiz_rubrikada_na_qabul_qilinmaydi() -> None:
    """Rubrikada `optional` yo'q bo'lsa — hech narsa tashlanmaydi.

    Bu himoya: yangilanish o'tkazib yuborilsa tizim eskicha, qattiq
    baholaydi — ya'ni «yumshoq» rejim tasodifan yoqilib qolmaydi."""
    eski = [
        {**b, "criteria": [{k: v for k, v in c.items() if k != "optional"}
                           for c in b["criteria"]]}
        for b in BLOCKS
    ]

    with pytest.raises(ScoreValidationError):
        validate(_build(na=("A2",)), rubric_blocks=eski, rubric_red_flags=FLAGS)


# ══════════════════════════════════════════════════════════════
#  6. Javob SHAKLI — obyekt ham, ro'yxat ham
# ══════════════════════════════════════════════════════════════


def test_kriteriyalar_obyekt_shaklida_ham_qabul_qilinadi() -> None:
    """Sxema aynan SHU shaklni talab qiladi: `{"A1": {...}, ...}`.

    ⚠️ Shakl ataylab o'zgartirilgan. Ro'yxat (`[{"id": "A1", ...}]`)
    ko'rinishida har mezonga ALOHIDA chegara qo'yib bo'lmasdi va model
    `na` bilan tashlangan mezonning ballini qolganlariga taqsimlardi
    (A4 ga 5 o'rniga 15). Obyektda har kalit o'z sxemasini oladi —
    bunday javob tuzilishiga ko'ra mumkin emas."""
    royxat = json.loads(_build(na=("A2", "A3")))
    obyekt = json.loads(_build(na=("A2", "A3")))
    for key, block in obyekt["blocks"].items():
        block["criteria"] = {
            item.pop("id"): item for item in block["criteria"]
        }
        # Sxemada blok bali umuman yo'q — u hisoblanadi
        block.pop("score")

    a = _check(json.dumps(royxat, ensure_ascii=False))
    b = _check(json.dumps(obyekt, ensure_ascii=False))

    assert a.overall == b.overall
    assert a.na_criteria == b.na_criteria
    assert a.block_scores == b.block_scores


def test_sxemada_har_mezon_oz_chegarasini_oladi() -> None:
    """Sxema — birinchi to'siq, validator esa oxirgisi."""
    from src.modules.scoring.application.prompt import build_schema

    schema = build_schema(BLOCKS, FLAGS)
    script = schema["properties"]["blocks"]["properties"]["script"]
    criteria = script["properties"]["criteria"]["properties"]

    assert criteria["A1"]["properties"]["score"]["maximum"] == 5
    assert criteria["A2"]["properties"]["score"]["maximum"] == 8
    # `na` faqat ixtiyoriy mezonda — sxemaning o'zi to'sadi
    assert "na" not in criteria["A1"]["properties"]["verdict"]["enum"]
    assert "na" in criteria["A2"]["properties"]["verdict"]["enum"]
    # Har mezon MAJBURIY: model uni tushirib qoldira olmaydi
    assert set(script["properties"]["criteria"]["required"]) == set(criteria)


# ══════════════════════════════════════════════════════════════
#  7. `na` budjeti — uzun suhbatda ommaviy tashlab ketish yo'q
# ══════════════════════════════════════════════════════════════


def test_qisqa_suhbatda_budjet_halaqit_bermaydi() -> None:
    """30 soniyalik «50 ta chiqaring» — bosqichlar uchun VAQT yo'q."""
    draft = validate(
        _build(na=("A2", "A3", "C2", "C3", "D1", "D2", "D4")),
        rubric_blocks=BLOCKS,
        rubric_red_flags=FLAGS,
        duration_sec=35,
    )

    assert draft.overall == 100


def test_uzun_suhbatda_ommaviy_na_rad_etiladi() -> None:
    """⚠️ BIRINCHI MUAMMONING KO'ZGUSI.

    O'lchandi: chegarasiz qoldirilganda model 10 daqiqalik suhbatda ham
    yettita mezonni «taalluqli emas» deb belgilab, 12 ta qo'ng'iroqning
    8 tasiga 100 ball qo'ydi. Ilgari hamma asossiz PAST ball olardi,
    endi asossiz YUQORI olardi — ikkalasi ham vositani foydasiz qiladi.

    10 daqiqalik suhbatda vaqt ham, mavzu ham bo'lgan: u yerda
    «taalluqli emas» degan da'vo deyarli har doim «xodim qilmadi»
    degani."""
    with pytest.raises(ScoreValidationError) as exc:
        validate(
            _build(na=("A2", "A3", "C2", "C3", "D1", "D2", "D4")),
            rubric_blocks=BLOCKS,
            rubric_red_flags=FLAGS,
            duration_sec=600,
        )

    assert "daqiqa" in exc.value.message
    assert "`fail`" in exc.value.message


def test_uzun_suhbatda_ozgina_na_qabul_qilinadi() -> None:
    """Chegara `na` ni butunlay taqiqlamaydi — o'rinlisi qoladi.

    Uzun suhbatda ham upsell (6) va qiymat argumenti (5) o'rinsiz
    bo'lishi mumkin: masalan mijoz shikoyat bilan qo'ng'iroq qilgan."""
    draft = validate(
        _build(na=("D2", "D4")),
        rubric_blocks=BLOCKS,
        rubric_red_flags=FLAGS,
        duration_sec=600,
    )

    assert draft.na_criteria == ["D2", "D4"]
    assert draft.applicable_points == 100 - 11


def test_budjet_uzunlikka_qarab_pasayadi() -> None:
    from src.modules.scoring.application.validator import na_budget

    assert na_budget(30) > na_budget(150) > na_budget(600)


def test_oxirgi_urinishda_budjet_QOLDA_qollanadi() -> None:
    """⚠️ Baho YO'QOLMAYDI, lekin haddan tashqari `na` ham o'tmaydi.

    Budjetdan oshgani javobni rad etadi va model qaytadan so'raladi —
    bu to'g'ri va odatda yordam beradi (o'lchandi: ikkinchi urinishda
    ball 58–92 oralig'iga tushdi). Lekin urinishlar tugagach rad
    etishda ma'no qolmaydi: qo'ng'iroq umuman baholanmagan bo'lib
    qolardi va uch marta to'langan pul behuda ketardi.

    Shuning uchun oxirgi urinishda budjet QO'LDA qo'llanadi: eng arzon
    `na` lar qoladi, qolganlari «bajarilmagan» deb hisoblanadi. Baho
    tekshiruv navbatiga ham tushadi."""
    draft = validate(
        _build(na=("A2", "A3", "C2", "C3", "D1", "D2", "D4")),
        rubric_blocks=BLOCKS,
        rubric_red_flags=FLAGS,
        duration_sec=600,
        enforce_na_budget=False,
    )

    assert draft.na_over_budget is True
    assert draft.warnings
    # Budjet 20: A3 (7) + D2 (6) + D4 (5) = 18 sig'di, qolganlari
    # hisobga qaytarildi
    assert set(draft.na_criteria) == {"A3", "D2", "D4"}
    assert draft.applicable_points == 100 - 18
    # Ball endi 100 emas — qaytarilgan mezonlar nol oldi
    assert draft.overall < 100


def test_budjet_ichida_bolsa_bayroq_qoyilmaydi() -> None:
    draft = validate(
        _build(na=("D2", "D4")),
        rubric_blocks=BLOCKS,
        rubric_red_flags=FLAGS,
        duration_sec=600,
        enforce_na_budget=False,
    )

    assert draft.na_over_budget is False
