"""LLM javobini tekshirish — ishonmaymiz, HISOBLAYMIZ.

Nega bu fayl bor: model «bloklar 84, umumiy 96» deb qaytarishi mumkin,
va bu yolg'on ball bazaga tushsa uni hech kim sezmaydi — xodim esa
noto'g'ri baholanadi. Shuning uchun:

  · arifmetika QAYTA hisoblanadi (kriteriya → blok → umumiy),
  · red flag kalitlari rubrikaga solishtiriladi,
  · o'ylab topilgan blok/kriteriya/flag kalitlari rad etiladi.

Rad etilgan javob SAQLANMAYDI: qo'ng'iroq «xato» holatida qoladi va
sabab o'zbekcha yoziladi, admin uni ko'radi.

## QO'LLANILGAN MEZONLAR ICHIDA HISOBLASH (`na`)

Mijozlarning aksariyati — eski mijoz va ular qisqa gaplashadi:
«menga 50 ta chiqaring». Bunday suhbatda ehtiyojni aniqlash ham,
mahsulotni taqdim etish ham, upsell ham TALAB QILINMAYDI. Ilgari
rubrika baribir to'liq qo'llanardi va xodim aybsiz holda 40–50 ball
olardi — past ball xodim haqida emas, rubrikaning o'rinsizligi haqida
gapirardi.

Endi model bunday mezonni `verdict: "na"` deb belgilaydi va u
hisobdan CHIQADI: nol ham olmaydi, maksimum ham olmaydi. Ball
QO'LLANILGAN mezonlar ichida hisoblanadi:

    blok ko'rsatkichi = blok_maksimumi × olingan / qo'llanilgan
    umumiy ball      = 100 × Σ blok ko'rsatkichi / Σ blok maksimumi

Ya'ni «10 balldan 8» ham, «25 balldan 20» ham bir xil — 80%.

⚠️ UCH HIMOYA bor, aks holda `na` yashirin ball ko'tarishga aylanardi
— va bu ATAYLAB qo'yilgan emas, O'LCHOVDAN keyin qo'shilgan: chegarasiz
qoldirilganda model 10 daqiqalik suhbatda ham yettita mezonni tashlab
yuborib, 12 ta qo'ng'iroqning 8 tasiga 100 ball qo'ydi.

  1. `na` faqat rubrikada `optional: true` deb belgilangan mezonga
     qo'yiladi. Salomlashish, muomala madaniyati, savolga to'g'ri
     javob va kelishuvning aniqligi HAR QANDAY suhbatda tekshiriladi.
  2. `na` uchun BUDJET suhbat uzunligiga bog'liq (`na_budget`): qisqa
     suhbatda chegara amalda yo'q, 4 daqiqadan uzunida esa ko'pi bilan
     20 ball. Uzun suhbatda vaqt ham, mavzu ham bo'lgan — u yerda
     «taalluqli emas» deyish deyarli har doim «qilinmadi» degani.
  3. Qo'llanilgan mezonlar yig'indisi `MIN_APPLICABLE_POINTS` dan
     past tushsa — javob rad etiladi. Bu «hammasini `na` qilib
     yuborish» yo'lini yopadi.
"""

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.exceptions import AppError

#: Modellar ba'zan JSON'ni ```json ... ``` ichida qaytaradi
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

VALID_SENTIMENTS = ("positive", "neutral", "negative")
VALID_OUTCOMES = ("order_agreed", "follow_up", "rejected", "info_only", "unclear")
VALID_QUALITY = ("high", "medium", "low")
VALID_VERDICTS = ("pass", "partial", "fail", "na")
VALID_SCENARIOS = (
    "new_client",
    "repeat_order",
    "price_check",
    "issue",
    "personal",
    "no_content",
    "other",
)

#: «Taalluqli emas» deb belgilangan verdikt.
NOT_APPLICABLE = "na"

#: `na` uchun BUDJET — suhbat uzunligiga qarab.
#
# ⚠️ NEGA UZUNLIKKA BOG'LIQ. O'lchandi: chegarasiz qoldirilganda model
# 10 DAQIQALIK suhbatda ham yettita mezonni «taalluqli emas» deb
# belgilab, 12 ta qo'ng'iroqning 8 tasiga 100 ball qo'ydi. Bu — birinchi
# muammoning KO'ZGUSI: ilgari hamma qo'ng'iroq asossiz past ball olardi,
# endi asossiz yuqori olardi. Ikkalasi ham vositani foydasiz qiladi.
#
# Mantiq oddiy: 30 soniyalik «50 ta chiqaring» suhbatida ehtiyojni
# aniqlashga ham, taqdimotga ham VAQT yo'q — ular haqiqatan taalluqli
# emas. 10 daqiqalik suhbatda esa vaqt ham, mavzu ham bo'lgan: u yerda
# «taalluqli emas» degan da'vo deyarli har doim «xodim qilmadi» degani.
#
# Qiymatlar: (soniya chegarasi, `na` ga ruxsat etilgan umumiy ball).
NA_BUDGET: tuple[tuple[int, int], ...] = (
    (90, 100),   # qisqa suhbat — cheklov amalda yo'q
    (240, 32),   # 1.5–4 daqiqa — yarmigacha
    (10**9, 20),  # 4 daqiqadan uzun — faqat eng o'rinsizlari
)


def na_budget(duration_sec: int) -> int:
    """Shu uzunlikdagi suhbatda `na` ga ruxsat etilgan umumiy ball."""
    for chegara, budjet in NA_BUDGET:
        if duration_sec < chegara:
            return budjet
    return NA_BUDGET[-1][1]


#: Qo'llanilgan mezonlar yig'indisi shundan past bo'lsa — javob rad
#: etiladi.
#
# NEGA CHEGARA BOR. `na` — foydali vosita, lekin u nazoratsiz qolsa
# baholashning o'zi ma'nosini yo'qotadi: model hamma qiyin mezonni
# «taalluqli emas» deb belgilab, har qo'ng'iroqqa 95 ball qo'yishi
# mumkin va buni hech kim sezmasdi (ball ko'tarilgani shikoyat
# tug'dirmaydi).
#
# 40 — standart rubrikadagi «har doim baholanadigan» mezonlar
# yig'indisidan (51) past, ya'ni normal ish bu chegaraga tegmaydi.
# Unga tegilsa — demak rubrika deyarli butunlay o'chirilgan va bu
# javob emas, nosozlik.
MIN_APPLICABLE_POINTS = 40


def _round_half_up(value: float) -> int:
    """Yarim ball YUQORIGA yaxlitlanadi.

    ⚠️ `round()` ISHLATILMAYDI: Python'da u «bankir yaxlitlashi» qiladi
    va `round(12.5)` → 12 beradi. Ball — odam haqidagi raqam, shubhali
    holat esa rubrikaning o'zida ham xodim foydasiga hal qilinadi
    («Shubhali holatda xodim foydasiga»). Bir ballik farq katta emas,
    lekin qoida BIR XIL tomonga qarab ishlashi kerak — aks holda
    «nega 12, hisoblasam 12.5 chiqyapti» degan savol javobsiz qoladi.
    """
    return math.floor(value + 0.5)


class ScoreValidationError(AppError):
    """LLM javobi rubrikaga mos kelmadi — baho SAQLANMAYDI."""

    status_code = 422
    code = "score_invalid"


@dataclass(slots=True)
class ScoreDraft:
    """Tekshiruvdan o'tgan baho — bazaga yozishga tayyor."""

    overall: int
    blocks: dict[str, Any]
    block_scores: dict[str, int]
    """Blok ko'rsatkichi — QO'LLANILGAN mezonlar ichida hisoblanib,
    blok maksimumiga keltirilgan (`max × olingan / qo'llanilgan`).

    ⚠️ Xom yig'indi EMAS. Aynan shu qiymat ekranda va analitikada
    ko'rinadi: «Skript 22/25» degan yozuv qisqa suhbatda ham to'g'ri
    o'qiladi, xom yig'indi esa «5/25» bo'lib, xodimni aybdor
    ko'rsatardi. Xomi `blocks[key]["raw_score"]` da turadi.

    Butunlay `na` bo'lgan blok bu lug'atga UMUMAN kirmaydi — uni 0
    deb ham, maksimum deb ham ko'rsatish yolg'on bo'lardi."""

    red_flags: list[dict[str, Any]]
    penalty_total: int
    outcome_signal: dict[str, Any]
    sentiment: str
    coaching_note: str
    confidence: float
    language_detected: str
    transcript_quality: str
    applicable_points: int = 100
    """Shu suhbatga QO'LLANILGAN mezonlar yig'indisi (100 dan)."""
    earned_points: int = 0
    """Qo'llanilgan mezonlardan olingan xom ball."""
    na_criteria: list[str] = field(default_factory=list)
    """Taalluqli emas deb belgilangan kriteriya kalitlari."""
    scenario: str = "other"
    """Suhbat turi (`repeat_order`, `price_check`, ...) — BALL EMAS,
    `na` qarorlarini tushuntiradigan kontekst."""
    na_over_budget: bool = False
    """Uzun suhbatda haddan ortiq mezon «taalluqli emas» deb
    belgilangan. Baho qabul qilindi (urinishlar tugadi), lekin u
    ODAM ko'rishi kerak: ehtimol xodim bosqichlarni o'tkazib
    yuborgan-u, model buni «talab qilinmadi» deb o'qigan."""
    zeroed: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def blocks_total(self) -> int:
        return sum(self.block_scores.values())

    @property
    def applicable_max(self) -> int:
        """Ko'rsatkichlar qaysi maksimumga nisbatan hisoblangani.

        Butunlay `na` bo'lgan blok bu songa kirmaydi, ya'ni ekranda
        «68 / 75» deb ko'rsatish mumkin va bu haqiqatga mos bo'ladi."""
        return sum(
            int(block.get("max", 0))
            for block in self.blocks.values()
            if block.get("applicable_max", 0) > 0
        )


# ── Yordamchilar ──────────────────────────────────────────────


def _as_int(value: Any, *, where: str) -> int:
    if isinstance(value, bool):
        raise ScoreValidationError(f"{where}: ball son bo'lishi kerak")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    raise ScoreValidationError(f"{where}: «{value}» ball emas — butun son kutilgan")


def loads(raw: str) -> dict[str, Any]:
    """Modelning matnli javobini JSON'ga aylantiradi."""
    text = (raw or "").strip()
    if not text:
        raise ScoreValidationError("AI bo'sh javob qaytardi — baho olinmadi")

    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Ba'zi modellar JSON oldidan bir-ikki jumla yozadi — oxirgi
        # imkoniyat sifatida birinchi `{` dan oxirgi `}` gacha olamiz
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ScoreValidationError(
                f"AI javobini JSON sifatida o'qib bo'lmadi: {exc.msg}"
            ) from exc
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc2:
            raise ScoreValidationError(
                f"AI javobini JSON sifatida o'qib bo'lmadi: {exc2.msg}"
            ) from exc2

    if not isinstance(data, dict):
        raise ScoreValidationError("AI javobi obyekt (JSON object) emas")
    return data


# ── Asosiy tekshiruv ──────────────────────────────────────────


def validate(
    raw: str,
    *,
    rubric_blocks: list[dict[str, Any]],
    rubric_red_flags: list[dict[str, Any]],
    duration_sec: int | None = None,
    enforce_na_budget: bool = True,
) -> ScoreDraft:
    """Javobni rubrikaga solishtirib tekshiradi va qayta hisoblaydi.

    `duration_sec` berilsa, `na` uchun budjet ham tekshiriladi: uzun
    suhbatda mezonlarni ommaviy «taalluqli emas» deb tashlab ketish
    mumkin emas.

    ⚠️ `enforce_na_budget=False` — OXIRGI urinish uchun. Budjetdan
    oshgani javobni rad etadi va model qaytadan so'raladi, lekin
    urinishlar tugagach rad etishda ma'no qolmaydi: natijada
    qo'ng'iroq umuman baholanmagan bo'lib qoladi (o'lchandi — shunday
    holat bo'ldi) va uch marta to'langan pul ham behuda ketadi.
    Shuning uchun oxirgi urinishda baho QABUL QILINADI, `na_over_budget`
    bayrog'i esa uni menejerning tekshiruv navbatiga olib chiqadi.
    """
    data = loads(raw)

    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, dict):
        raise ScoreValidationError("AI javobida `blocks` obyekti yo'q")

    expected_keys = {b["key"] for b in rubric_blocks}
    got_keys = set(blocks_raw)

    unknown = sorted(got_keys - expected_keys)
    if unknown:
        raise ScoreValidationError(
            f"AI rubrikada yo'q blokni qaytardi: {', '.join(unknown)}. "
            f"Ruxsat etilganlari: {', '.join(sorted(expected_keys))}"
        )
    missing = sorted(expected_keys - got_keys)
    if missing:
        raise ScoreValidationError(
            f"AI javobida bloklar yetishmaydi: {', '.join(missing)}"
        )

    #: Ballga TA'SIR QILMAYDIGAN nomuvofiqliklar (masalan modelning
    #: o'zi yozgan blok bali kriteriyalar yig'indisiga teng emas).
    #: Baho saqlanadi, lekin nomuvofiqlik yo'qolmaydi.
    warnings: list[str] = []

    # ── 1-o'tish: kriteriyalarni tekshirish ───────────────────
    tozalangan: dict[str, list[dict[str, Any]]] = {}
    for spec in rubric_blocks:
        key = spec["key"]
        label = spec.get("label", key)
        payload = blocks_raw[key]
        if not isinstance(payload, dict):
            raise ScoreValidationError(f"«{label}» bloki obyekt emas")

        criteria_clean, score = _validate_criteria(
            payload.get("criteria"), spec=spec, label=label
        )
        tozalangan[key] = criteria_clean

        # ⚠️ Blok bali MODELDAN OLINMAYDI, kriteriyalardan hisoblanadi.
        #
        # Ilgari model uni o'zi yozardi va validator solishtirardi.
        # `na` paydo bo'lgach bu doimiy nosozlik manbaiga aylandi:
        # tashlangan mezondan keyin model blok maksimumini
        # «to'ldirishga» urinib, yig'indini oshirib yozardi va butun
        # javob rad etilardi — o'lchandi, beshta qo'ng'iroqning
        # ikkitasi shu sababli umuman baholanmay qoldi.
        yozilgan = payload.get("score")
        if yozilgan is not None:
            try:
                if _as_int(yozilgan, where=f"«{label}» bloki") != score:
                    warnings.append(
                        f"«{label}»: model {yozilgan} deb yozdi, kriteriyalar "
                        f"yig'indisi {score}"
                    )
            except ScoreValidationError:
                warnings.append(
                    f"«{label}»: blok bali son emas — e'tiborsiz qoldirildi"
                )

    # ── `na` budjeti ──────────────────────────────────────────
    na_over_budget = _apply_na_budget(
        tozalangan,
        duration_sec=duration_sec,
        enforce=enforce_na_budget,
        warnings=warnings,
    )

    # ── 2-o'tish: bloklar bo'yicha hisob ──────────────────────
    block_scores: dict[str, int] = {}
    blocks_clean: dict[str, Any] = {}
    applicable_points = 0
    earned_points = 0
    na_criteria: list[str] = []
    displayed_max = 0

    for spec in rubric_blocks:
        key = spec["key"]
        label = spec.get("label", key)
        block_max = int(spec.get("max", 0))
        criteria_clean = tozalangan[key]

        block_applicable = sum(c["max"] for c in criteria_clean if c["applicable"])
        score = sum(c["score"] for c in criteria_clean if c["applicable"])

        applicable_points += block_applicable
        earned_points += score
        na_criteria.extend(
            c["id"] for c in criteria_clean if not c["applicable"]
        )

        # ── Blok ko'rsatkichi ─────────────────────────────────
        #
        # Xom yig'indi emas, QO'LLANILGAN mezonlar ichidagi ulush.
        # Qisqa buyurtma suhbatida «Skript» blokining yarmi taalluqli
        # bo'lmasligi mumkin: xom 5/25 «xodim yomon ishladi» degan
        # yolg'on xabar berardi, 22/25 esa haqiqatni aytadi —
        # qo'llanilganining hammasi bajarilgan.
        if block_applicable > 0:
            display = _round_half_up(block_max * score / block_applicable)
            display = max(0, min(block_max, display))
            block_scores[key] = display
            displayed_max += block_max
        else:
            # Butunlay taalluqli bo'lmagan blok umuman ko'rsatilmaydi.
            # 0 deb yozish xodimni aybdor qilardi, maksimum deb yozish
            # esa tekshirilmagan ish uchun ball berardi.
            display = None

        blocks_clean[key] = {
            "score": display if display is not None else 0,
            "max": block_max,
            "raw_score": score,
            "applicable_max": block_applicable,
            "label": label,
            "criteria": criteria_clean,
        }

    if applicable_points < MIN_APPLICABLE_POINTS or displayed_max == 0:
        belgilangan = ", ".join(na_criteria) or "yo'q"
        raise ScoreValidationError(
            f"Qo'llanilgan mezonlar juda kam ({applicable_points} ball, kamida "
            f"{MIN_APPLICABLE_POINTS} kerak): «taalluqli emas» deb "
            f"belgilanganlari — {belgilangan}. Salomlashish, muomala "
            "madaniyati, savolga javob va kelishuv aniqligi har qanday "
            "suhbatda baholanadi. Baho saqlanmadi."
        )

    red_flags, penalty_total, zeroed = _validate_red_flags(
        data.get("red_flags"), rubric_red_flags=rubric_red_flags
    )

    # ── Umumiy ball ───────────────────────────────────────────
    #
    # ⚠️ MODELDAN OLINMAYDI, hisoblanadi. Ilgari model `overall_score`
    # ni o'zi qaytarardi va validator arifmetikani tekshirardi. Endi
    # hisobda bo'lish bor (qo'llanilgan mezonlar ichidagi foiz), ya'ni
    # modeldan uni so'rash — javobning rad etilishi va qayta so'rov
    # (ikki baravar pul) ehtimolini oshirish degani.
    #
    # Foiz KO'RSATILADIGAN qiymatlardan chiqariladi: ekranda bloklar
    # yig'indisi 68, maksimum 75 bo'lsa, umumiy ball 91 bo'lishi kerak.
    # Boshqacha hisoblansa, menejer ekrandagi sonlarni qo'shib boshqa
    # natija olardi va bahoga ishonchi yo'qolardi.
    base = _round_half_up(100 * sum(block_scores.values()) / displayed_max)
    expected_overall = 0 if zeroed else max(0, min(100, base + penalty_total))

    confidence = _validate_confidence(data.get("confidence"))
    sentiment = _validate_choice(
        data.get("client_sentiment"), VALID_SENTIMENTS, "`client_sentiment`"
    )
    quality = _validate_choice(
        data.get("transcript_quality"), VALID_QUALITY, "`transcript_quality`"
    )
    outcome = _validate_outcome(data.get("outcome_signal"))

    coaching = str(data.get("coaching_note") or "").strip()
    if not coaching:
        raise ScoreValidationError(
            "AI `coaching_note` yozmadi — xodimga tavsiyasiz baho foydasiz"
        )

    language = str(data.get("language_detected") or "").strip().lower() or "mixed"
    if language not in ("uz", "ru", "mixed", "other"):
        language = "other"

    scenario = str(data.get("call_scenario") or "").strip().lower()
    if scenario not in VALID_SCENARIOS:
        # ⚠️ Bu maydon uchun javob RAD ETILMAYDI. U ballga ta'sir
        # qilmaydi — faqat kontekst. Butun bahoni notanish yorliq
        # uchun tashlab yuborish qimmat va befoyda bo'lardi.
        scenario = "other"

    return ScoreDraft(
        overall=expected_overall,
        blocks=blocks_clean,
        block_scores=block_scores,
        red_flags=red_flags,
        penalty_total=penalty_total,
        outcome_signal=outcome,
        sentiment=sentiment,
        coaching_note=coaching,
        confidence=confidence,
        language_detected=language,
        transcript_quality=quality,
        applicable_points=applicable_points,
        earned_points=earned_points,
        na_criteria=na_criteria,
        scenario=scenario,
        zeroed=zeroed,
        na_over_budget=na_over_budget,
        warnings=warnings,
    )


def _apply_na_budget(
    blocks: dict[str, list[dict[str, Any]]],
    *,
    duration_sec: int | None,
    enforce: bool,
    warnings: list[str],
) -> bool:
    """`na` budjetini qo'llaydi. `True` — budjet oshgan edi.

    Ikki xil ish qiladi:

      · `enforce=True` (odatiy urinish) — javobni RAD ETADI, model
        qaytadan so'raladi va odatda o'zi tuzatadi (o'lchandi: ikkinchi
        urinishda ball 58–92 oralig'iga tushdi, ya'ni model mezonlarni
        haqiqatan baholadi);
      · `enforce=False` (OXIRGI urinish) — rad etishda ma'no qolmaydi,
        chunki natijada qo'ng'iroq umuman baholanmagan bo'lib qolardi
        va uch marta to'langan pul behuda ketardi. Bunda budjet
        QO'LDA qo'llanadi: eng ARZON `na` lar qoldiriladi, qolganlari
        «bajarilmagan» (0 ball, `fail`) deb hisoblanadi.

    ⚠️ NEGA ARZONLARI QOLDIRILADI. Kichik balli mezon (upsell — 6,
    qiymat argumenti — 5) haqiqatan o'rinsiz bo'lishi ehtimoli
    yuqoriroq; katta balli mezon (ehtiyojni aniqlash — 8) esa uzun
    suhbatda deyarli har doim bo'lishi kerak edi. Qaror odam uchun
    ko'rinadi: baho tekshiruv navbatiga tushadi.
    """
    if duration_sec is None:
        return False

    na_items = [
        c
        for criteria in blocks.values()
        for c in criteria
        if not c["applicable"]
    ]
    if not na_items:
        return False

    tashlangan_ball = sum(c["max"] for c in na_items)
    budjet = na_budget(duration_sec)
    if tashlangan_ball <= budjet:
        return False

    daqiqa = duration_sec // 60
    ro_yxat = ", ".join(c["id"] for c in na_items)
    xabar = (
        f"Suhbat {daqiqa} daqiqa davom etgan, ya'ni bosqichlar uchun vaqt "
        f"bo'lgan. «Taalluqli emas» deb {tashlangan_ball} ball tashlab "
        f"yuborilgan ({ro_yxat}), bunday suhbatda ruxsat etilgani — "
        f"{budjet} ball. Vaziyat imkon bergan-u xodim foydalanmagan bo'lsa, "
        "bu `na` emas, `fail`."
    )
    if enforce:
        raise ScoreValidationError(xabar + " Baho saqlanmadi.")

    # Budjetni qo'lda qo'llash: arzonlaridan boshlab sig'gani qoladi
    qolgan = budjet
    qaytarilgan: list[str] = []
    for item in sorted(na_items, key=lambda c: c["max"]):
        if item["max"] <= qolgan:
            qolgan -= item["max"]
            continue
        item["applicable"] = True
        item["verdict"] = "fail"
        item["score"] = 0
        # ⚠️ Dalil MATNI ham belgilanadi. Aks holda kartochkada
        # «bajarilmagan» degan verdikt turadi-yu, uning yonida
        # «bu suhbatga taalluqli emas» degan dalil qoladi — menejer
        # buni tizim nosozligi deb o'qirdi.
        item["evidence"] = (
            "[Tizim: uzun suhbat, «taalluqli emas» chegarasidan oshgani "
            "uchun hisobga qaytarildi] " + (item.get("evidence") or "")
        ).strip()
        item["improvement"] = (
            item.get("improvement")
            or "Suhbat uzun edi — bu bosqichni o'tkazib yubormaslik kerak"
        )
        qaytarilgan.append(item["id"])

    warnings.append(
        xabar + f" Chegaradan oshgani hisobga qaytarildi: {', '.join(qaytarilgan)}."
    )
    return True


def _validate_criteria(
    raw: Any, *, spec: dict[str, Any], label: str
) -> tuple[list[dict[str, Any]], int]:
    """Kriteriyalarni tekshiradi va blok balini HISOBLAYDI.

    Qaytaradi: (tozalangan ro'yxat, olingan ball).

    Qaysi mezon qo'llanilgani `clean[i]["applicable"]` da turadi —
    budjet qo'llangandan KEYIN o'sha ro'yxatdan qayta hisoblanadi,
    shuning uchun bu yerda alohida qaytarilmaydi.

    Kirish ikki shaklda bo'lishi mumkin:

      · obyekt — `{"A1": {"score": 5, ...}, ...}` (sxema shuni talab
        qiladi: har mezon o'z chegarasi va o'z verdikt ro'yxati bilan);
      · ro'yxat — `[{"id": "A1", "score": 5, ...}, ...]` (eski shakl).

    ⚠️ IKKALASI HAM QABUL QILINADI. Sxemani qo'llab-quvvatlamaydigan
    provayder ro'yxat qaytarishi mumkin va bunda bahoni tashlab
    yuborish o'rinsiz bo'lardi — ma'lumot baribir to'liq.

    `na` — faqat rubrikada `optional: true` deb belgilangan kriteriyada.
    Aks holda model istagan mezonni hisobdan chiqarib yuborardi va past
    ball umuman chiqmasdi: «salomlashmadi» ham «taalluqli emas» bo'lib
    ketardi.
    """
    if isinstance(raw, dict):
        items: list[Any] = [
            {"id": cid, **(payload if isinstance(payload, dict) else {})}
            for cid, payload in raw.items()
        ]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    if not items:
        raise ScoreValidationError(
            f"«{label}» bloki uchun kriteriyalar berilmadi — har ball dalil "
            "bilan asoslanishi kerak"
        )

    known = {c["id"]: int(c.get("points", 0)) for c in spec.get("criteria", [])}
    optional = {
        c["id"]: bool(c.get("optional")) for c in spec.get("criteria", [])
    }
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    total = 0
    #: Faqat xato xabari uchun: qaysi mezonlar hisobga kirmadi
    na_ids: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            raise ScoreValidationError(f"«{label}» bloki: kriteriya obyekt emas")
        cid = str(item.get("id") or "").strip()
        if cid not in known:
            raise ScoreValidationError(
                f"«{label}» bloki: rubrikada yo'q kriteriya «{cid}». "
                f"Mavjudlari: {', '.join(sorted(known))}"
            )
        if cid in seen:
            raise ScoreValidationError(
                f"«{label}» bloki: «{cid}» kriteriyasi ikki marta qaytarilgan"
            )
        seen.add(cid)

        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = "partial"

        score = _as_int(item.get("score"), where=f"«{label}» / {cid}")
        if not 0 <= score <= known[cid]:
            raise ScoreValidationError(
                f"«{label}» / {cid}: {score} ball, ruxsat etilgani 0..{known[cid]}"
            )

        if verdict == NOT_APPLICABLE:
            if not optional.get(cid):
                raise ScoreValidationError(
                    f"«{label}» / {cid}: bu mezon HAR QANDAY suhbatda "
                    "baholanadi, «taalluqli emas» deb belgilash mumkin emas. "
                    "Vaziyat talab qilgan-u xodim bajarmagan bo'lsa — `fail` "
                    "qo'ying. Baho saqlanmadi."
                )
            # ⚠️ `na` da ball E'TIBORSIZ qoldiriladi, javob rad
            # ETILMAYDI. Bunday mezon hisobga umuman kirmaydi, ya'ni
            # modelning u yerga nima yozgani ahamiyatsiz — butun
            # bahoni shu sabab tashlab yuborish qimmat va befoyda.
            score = 0
            na_ids.append(cid)
        else:
            total += score

        clean.append(
            {
                "id": cid,
                "score": score,
                "max": known[cid],
                "verdict": verdict,
                "applicable": verdict != NOT_APPLICABLE,
                "evidence": str(item.get("evidence") or "").strip(),
                "improvement": str(item.get("improvement") or "").strip() or None,
            }
        )

    absent = sorted(set(known) - seen)
    if absent:
        raise ScoreValidationError(
            f"«{label}» bloki: {', '.join(absent)} kriteriyalari baholanmagan. "
            "Har bir mezon javobda bo'lishi shart — «taalluqli emas» deb "
            "belgilangani ham (`verdict: \"na\"`)."
        )
    return clean, total


def _validate_red_flags(
    raw: Any, *, rubric_red_flags: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, bool]:
    """Qaytaradi: (hodisalar, umumiy jarima, ball nolga tushirilganmi).

    HAR BIR hodisa saqlanadi — dalil (vaqt, iqtibos) yo'qolmasin.
    Jarima esa har TUR uchun bir marta: ikki marta baqirgani uchun
    ikki marta jarimalanmaydi.
    """
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ScoreValidationError("`red_flags` ro'yxat (array) bo'lishi kerak")

    known = {f["type"]: f for f in rubric_red_flags}
    clean: list[dict[str, Any]] = []
    penalty = 0
    zeroed = False
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            raise ScoreValidationError("`red_flags` ichidagi element obyekt emas")
        flag_type = str(item.get("type") or "").strip()
        spec = known.get(flag_type)
        if spec is None:
            raise ScoreValidationError(
                f"AI o'ylab topilgan red flag qaytardi: «{flag_type}». "
                f"Rubrikada faqat shular bor: {', '.join(sorted(known))}. "
                "Baho saqlanmadi."
            )
        # ⚠️ Jarima MODELDAN olinmaydi — rubrikadan olinadi. Aks holda
        # model o'zi jarima o'ylab topib ballni buzardi.
        #
        # Takror haqida: bir xil turdagi ikkinchi qoidabuzarlik SAQLANADI
        # (menejer ikkala baqirishning ham vaqti va iqtibosini ko'rishi
        # kerak), lekin JARIMA har tur uchun BIR MARTA hisoblanadi.
        # `counted=False` — bu hodisa ballga ta'sir qilmagani belgisi,
        # `penalty=0` esa massivdagi jarimalar yig'indisi `penalty_total`
        # dan farq qilib qolmasligi uchun.
        counted = flag_type not in seen
        flag_penalty = int(spec.get("penalty", 0)) if counted else 0
        if counted:
            seen.add(flag_type)
            penalty += flag_penalty
            zeroed = zeroed or bool(spec.get("zeroes_score"))

        clean.append(
            {
                "type": flag_type,
                "label": spec.get("label", flag_type),
                "severity": str(item.get("severity") or "high").strip(),
                "timestamp": str(item.get("timestamp") or "").strip() or None,
                "quote": str(item.get("quote") or "").strip(),
                "penalty": flag_penalty,
                "counted": counted,
            }
        )

    return clean, penalty, zeroed


def _validate_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoreValidationError(
            f"`confidence` son emas: «{value}»"
        ) from exc
    if not 0.0 <= number <= 1.0:
        raise ScoreValidationError(
            f"`confidence` 0 va 1 orasida bo'lishi kerak, kelgani: {number}"
        )
    return round(number, 3)


def _validate_choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ScoreValidationError(
            f"{label} noto'g'ri: «{value}». Ruxsat etilganlari: {', '.join(allowed)}"
        )
    return text


def _validate_outcome(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ScoreValidationError("`outcome_signal` obyekt bo'lishi kerak")
    outcome_type = _validate_choice(
        raw.get("type"), VALID_OUTCOMES, "`outcome_signal.type`"
    )
    products = raw.get("products_mentioned") or []
    if not isinstance(products, list):
        products = []

    quantity = raw.get("quantity_mentioned")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        quantity = None
    else:
        quantity = int(quantity)

    return {
        "type": outcome_type,
        "products_mentioned": [str(p) for p in products][:10],
        "quantity_mentioned": quantity,
        "confidence": _validate_confidence(raw.get("confidence", 0.5)),
        "evidence": str(raw.get("evidence") or "").strip() or None,
    }
