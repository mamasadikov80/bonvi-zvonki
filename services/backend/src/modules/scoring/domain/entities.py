"""Baholash domeni — rubrika strukturasi.

Rubrika PLAN.md 3.4-bo'limidan olingan. Versiyalanadi, chunki
o'zgargan rubrika bilan eski ballarni solishtirib bo'lmaydi.
"""

from dataclasses import dataclass
from enum import StrEnum

from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

RUBRIC_VERSION = "v1"


class ScoreBlock(StrEnum):
    SCRIPT = "script"  # A — Skript va struktura
    COMMUNICATION = "communication"  # B — Muloqot madaniyati
    RESOLUTION = "resolution"  # C — Muammoni hal qilish
    SALES_SKILL = "sales_skill"  # D — Savdo qobiliyati


#: Blok maksimumlari RUBRIKADAN olinadi — kodda qotirilmaydi.
#: Ilgari bu qiymatlar qo'lda yozilgan edi va rubrika o'zgargach
#: ikkiga ayrilgan: `sales_skill` kodda 15, rubrikada 25 bo'lib qolgan.
#: Natijada razrez foizi 25/15 = 167% chiqib, grafik shkaladan chiqib
#: ketardi. Manba bitta bo'lishi shart.
BLOCK_MAX: dict[ScoreBlock, int] = {
    ScoreBlock(block["key"]): int(block["max"]) for block in DEFAULT_RUBRIC["blocks"]
}

BLOCK_LABEL_UZ: dict[ScoreBlock, str] = {
    ScoreBlock.SCRIPT: "Skript va struktura",
    ScoreBlock.COMMUNICATION: "Muloqot madaniyati",
    ScoreBlock.RESOLUTION: "Muammoni hal qilish",
    ScoreBlock.SALES_SKILL: "Savdo qobiliyati",
}


class RedFlagType(StrEnum):
    """Jiddiy qoidabuzarliklar. Jarima ball ayiradi."""

    PROFANITY = "profanity"  # haqorat/so'kinish → ball 0
    SHOUTING = "shouting"  # baqirish → −20
    UNREALISTIC_PROMISE = "unrealistic_promise"  # bajarilmas va'da → −15
    BADMOUTHING = "badmouthing"  # kompaniya/hamkasb haqida salbiy → −15
    OFF_POLICY_DEAL = "off_policy_deal"  # rasmiy narxdan tashqari → −25
    IGNORED_COMPLAINT = "ignored_complaint"  # shikoyatni e'tiborsiz → −10


RED_FLAG_PENALTY: dict[RedFlagType, int] = {
    RedFlagType.PROFANITY: -100,  # amalda umumiy ballni 0 ga tushiradi
    RedFlagType.SHOUTING: -20,
    RedFlagType.UNREALISTIC_PROMISE: -15,
    RedFlagType.BADMOUTHING: -15,
    RedFlagType.OFF_POLICY_DEAL: -25,
    RedFlagType.IGNORED_COMPLAINT: -10,
}

RED_FLAG_LABEL_UZ: dict[RedFlagType, str] = {
    RedFlagType.PROFANITY: "Haqorat / so'kinish",
    RedFlagType.SHOUTING: "Baqirish",
    RedFlagType.UNREALISTIC_PROMISE: "Bajarilmas va'da",
    RedFlagType.BADMOUTHING: "Salbiy gap (kompaniya/hamkasb)",
    RedFlagType.OFF_POLICY_DEAL: "Qoidadan tashqari kelishuv",
    RedFlagType.IGNORED_COMPLAINT: "Shikoyat e'tiborsiz qoldirilgan",
}


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass(slots=True)
class ScoreSummary:
    """Bitta qo'ng'iroqning yakuniy bahosi."""

    overall: int
    blocks: dict[str, int]
    red_flag_count: int
    confidence: float
    needs_review: bool

    @property
    def grade(self) -> str:
        """Ballni harfiy darajaga aylantiradi (UI uchun)."""
        if self.overall >= 85:
            return "excellent"
        if self.overall >= 70:
            return "good"
        if self.overall >= 55:
            return "average"
        return "poor"
