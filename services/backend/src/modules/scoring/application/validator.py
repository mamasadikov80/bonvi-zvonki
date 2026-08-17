"""LLM javobini tekshirish — ishonmaymiz, HISOBLAYMIZ.

Nega bu fayl bor: model «bloklar 84, umumiy 96» deb qaytarishi mumkin,
va bu yolg'on ball bazaga tushsa uni hech kim sezmaydi — xodim esa
noto'g'ri baholanadi. Shuning uchun:

  · arifmetika QAYTA hisoblanadi (kriteriya → blok → umumiy),
  · red flag kalitlari rubrikaga solishtiriladi,
  · o'ylab topilgan blok/kriteriya/flag kalitlari rad etiladi.

Rad etilgan javob SAQLANMAYDI: qo'ng'iroq «xato» holatida qoladi va
sabab o'zbekcha yoziladi, admin uni ko'radi.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.exceptions import AppError

#: Modellar ba'zan JSON'ni ```json ... ``` ichida qaytaradi
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

VALID_SENTIMENTS = ("positive", "neutral", "negative")
VALID_OUTCOMES = ("order_agreed", "follow_up", "rejected", "info_only", "unclear")
VALID_QUALITY = ("high", "medium", "low")


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
    red_flags: list[dict[str, Any]]
    penalty_total: int
    outcome_signal: dict[str, Any]
    sentiment: str
    coaching_note: str
    confidence: float
    language_detected: str
    transcript_quality: str
    zeroed: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def blocks_total(self) -> int:
        return sum(self.block_scores.values())


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
) -> ScoreDraft:
    """Javobni rubrikaga solishtirib tekshiradi va qayta hisoblaydi."""
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

    block_scores: dict[str, int] = {}
    blocks_clean: dict[str, Any] = {}

    for spec in rubric_blocks:
        key = spec["key"]
        label = spec.get("label", key)
        block_max = int(spec.get("max", 0))
        payload = blocks_raw[key]
        if not isinstance(payload, dict):
            raise ScoreValidationError(f"«{label}» bloki obyekt emas")

        score = _as_int(payload.get("score"), where=f"«{label}» bloki")
        if not 0 <= score <= block_max:
            raise ScoreValidationError(
                f"«{label}» bloki: {score} ball qo'yilgan, ruxsat etilgani "
                f"0..{block_max}"
            )

        criteria_clean = _validate_criteria(
            payload.get("criteria"), spec=spec, label=label, block_score=score
        )

        block_scores[key] = score
        blocks_clean[key] = {
            "score": score,
            "max": block_max,
            "label": label,
            "criteria": criteria_clean,
        }

    red_flags, penalty_total, zeroed = _validate_red_flags(
        data.get("red_flags"), rubric_red_flags=rubric_red_flags
    )

    blocks_total = sum(block_scores.values())
    expected_overall = 0 if zeroed else max(0, min(100, blocks_total + penalty_total))

    reported = _as_int(data.get("overall_score"), where="`overall_score`")
    if reported != expected_overall:
        detail = ", ".join(f"{k}={v}" for k, v in block_scores.items())
        raise ScoreValidationError(
            f"AI arifmetikasi noto'g'ri: `overall_score` = {reported}, lekin "
            f"bloklar yig'indisi {blocks_total} ({detail})"
            + (f", red flag jarimasi {penalty_total}" if penalty_total else "")
            + (" va `profanity` red flag'i umumiy ballni 0 qiladi" if zeroed else "")
            + f" — to'g'ri qiymat {expected_overall}. Baho saqlanmadi."
        )

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
        zeroed=zeroed,
    )


def _validate_criteria(
    raw: Any, *, spec: dict[str, Any], label: str, block_score: int
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ScoreValidationError(
            f"«{label}» bloki uchun kriteriyalar berilmadi — har ball dalil "
            "bilan asoslanishi kerak"
        )

    known = {c["id"]: int(c.get("points", 0)) for c in spec.get("criteria", [])}
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    total = 0

    for item in raw:
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

        score = _as_int(item.get("score"), where=f"«{label}» / {cid}")
        if not 0 <= score <= known[cid]:
            raise ScoreValidationError(
                f"«{label}» / {cid}: {score} ball, ruxsat etilgani 0..{known[cid]}"
            )
        total += score

        clean.append(
            {
                "id": cid,
                "score": score,
                "max": known[cid],
                "verdict": str(item.get("verdict") or "").strip() or "partial",
                "evidence": str(item.get("evidence") or "").strip(),
                "improvement": str(item.get("improvement") or "").strip() or None,
            }
        )

    absent = sorted(set(known) - seen)
    if absent:
        raise ScoreValidationError(
            f"«{label}» bloki: {', '.join(absent)} kriteriyalari baholanmagan"
        )

    if total != block_score:
        raise ScoreValidationError(
            f"«{label}» bloki: kriteriyalar yig'indisi {total}, lekin blok bali "
            f"{block_score} deb yozilgan. Baho saqlanmadi."
        )
    return clean


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
