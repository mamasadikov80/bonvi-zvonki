"""`needs_review` — menejerlar tekshiruv navbatining yagona manbai.

Bayroq TASODIFAN qo'yilmaydi. To'rtta aniq sabab bor, har biri
o'zbekcha izoh bilan yoziladi, chunki menejer navbatni ochganda
«nega bu qo'ng'iroq bu yerda?» degan savolga javob ko'rishi kerak.

Chegaralarni bir joyda ushlab turamiz — ular sozlanadi va vaqt o'tib
kalibratsiyadan keyin o'zgaradi (PLAN.md 3.6).
"""

import re
from dataclasses import dataclass, field

# ── Chegaralar ────────────────────────────────────────────────

#: Modelning o'z bahosiga ishonchi shundan past bo'lsa — odam ko'radi
MIN_CONFIDENCE = 0.70

#: Shundan kam so'z — transkript to'liq emas (ASR tushirib qoldirgan
#: yoki qo'ng'iroq juda qisqa). Baho ishonchsiz.
MIN_WORDS = 60

#: Uzun qo'ng'iroqda so'z zichligi: 1 soniyaga shundan kam so'z tushsa,
#: demak matnning katta qismi yo'qolgan (2 daqiqadan uzun qo'ng'iroqlar uchun).
MIN_WORDS_PER_SEC = 0.5
DENSITY_MIN_DURATION_SEC = 120

#: AI bahosi (0..100) va mijoz bahosi (1..5 → ×20) orasidagi farq
#: shundan katta bo'lsa — biri xato. Odam hal qiladi.
MAX_CLIENT_GAP = 25

#: Mijoz bahosini ishonchli deb hisoblash uchun kerakli javoblar soni
MIN_CLIENT_RESPONSES = 3


#: Transkriptdagi XIZMAT belgilari: `[04:12]` va `SPEAKER_1:`.
#
# ⚠️ NEGA ULAR SANALMAYDI. Chegara (`MIN_WORDS`) haqiqiy GAP so'zlari
# uchun qo'yilgan, lekin `str.split()` xizmat belgilarini ham so'z deb
# sanaydi: 17 qatorli transkriptda bu 34 ta soxta «so'z» — ya'ni 60 ta
# haqiqiy so'zli qisqa suhbat 94 so'z bo'lib ko'rinadi va qoida
# ISHLAMAY qoladi.
#
# Bu jimgina xato edi: aynan eng qisqa, ya'ni eng shubhali suhbatlar
# tekshiruv navbatiga tushmasdi.
_TIMESTAMP = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")
_SPEAKER = re.compile(r"(?m)^\s*[A-Za-zА-Яа-яЎўҚқҒғҲҳ_0-9 .'-]{1,32}:\s")


def count_words(transcript_text: str | None) -> int:
    """Transkriptdagi haqiqiy so'zlar soni (xizmat belgilarisiz)."""
    text = _TIMESTAMP.sub(" ", transcript_text or "")
    text = _SPEAKER.sub(" ", text)
    return len(text.split())


class ReviewReason:
    LOW_CONFIDENCE = "low_confidence"
    SHORT_TRANSCRIPT = "short_transcript"
    RED_FLAG = "red_flag"
    CLIENT_GAP = "client_gap"
    NA_OVER_BUDGET = "na_over_budget"


@dataclass(slots=True)
class ReviewDecision:
    needs_review: bool
    reasons: list[dict[str, str]] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return [r["code"] for r in self.reasons]

    @property
    def summary_uz(self) -> str:
        return "; ".join(r["message"] for r in self.reasons)


def decide(
    *,
    confidence: float,
    transcript_quality: str,
    transcript_text: str,
    duration_sec: int,
    red_flag_types: list[str],
    ai_score: int,
    client_rating: float | None = None,
    client_rating_count: int = 0,
    na_over_budget: bool = False,
) -> ReviewDecision:
    """Qoidalarni ketma-ket tekshiradi."""
    reasons: list[dict[str, str]] = []

    # 1. Past ishonch — model o'zi shubhalanmoqda
    if confidence < MIN_CONFIDENCE:
        reasons.append(
            {
                "code": ReviewReason.LOW_CONFIDENCE,
                "message": (
                    f"AI ishonchi past ({confidence:.2f} < {MIN_CONFIDENCE:.2f})"
                ),
            }
        )
    elif transcript_quality == "low":
        reasons.append(
            {
                "code": ReviewReason.LOW_CONFIDENCE,
                "message": "Transkript sifati past deb belgilangan",
            }
        )

    # 2. G'ayrioddiy qisqa transkript — ASR yo'qotgan bo'lishi mumkin
    words = count_words(transcript_text)
    if words < MIN_WORDS:
        reasons.append(
            {
                "code": ReviewReason.SHORT_TRANSCRIPT,
                "message": (
                    f"Transkript juda qisqa — {words} so'z ({MIN_WORDS} dan kam)"
                ),
            }
        )
    elif (
        duration_sec >= DENSITY_MIN_DURATION_SEC
        and words < duration_sec * MIN_WORDS_PER_SEC
    ):
        reasons.append(
            {
                "code": ReviewReason.SHORT_TRANSCRIPT,
                "message": (
                    f"{duration_sec // 60} daqiqalik suhbatda atigi {words} so'z — "
                    "matnning katta qismi yo'qolgan"
                ),
            }
        )

    # 3. Uzun suhbatda haddan ortiq mezon «taalluqli emas» deb
    #    belgilangan. Baho qabul qilingan (urinishlar tugagan), lekin
    #    ehtimol xodim bosqichlarni o'tkazib yuborgan-u, model buni
    #    «talab qilinmadi» deb o'qigan — buni ODAM hal qilishi kerak.
    if na_over_budget:
        reasons.append(
            {
                "code": ReviewReason.NA_OVER_BUDGET,
                "message": (
                    "Uzun suhbatda mezonlarning katta qismi «taalluqli emas» "
                    "deb belgilangan — ball asossiz yuqori bo'lishi mumkin"
                ),
            }
        )

    # 4. Red flag — jiddiy ayblov, odam tasdiqlashi shart
    if red_flag_types:
        reasons.append(
            {
                "code": ReviewReason.RED_FLAG,
                "message": "Red flag topildi: " + ", ".join(sorted(set(red_flag_types))),
            }
        )

    # 5. Mijoz bahosi bilan katta tafovut
    if client_rating is not None and client_rating_count >= MIN_CLIENT_RESPONSES:
        client_scaled = client_rating * 20.0
        gap = abs(ai_score - client_scaled)
        if gap > MAX_CLIENT_GAP:
            direction = "yuqori" if ai_score > client_scaled else "past"
            reasons.append(
                {
                    "code": ReviewReason.CLIENT_GAP,
                    "message": (
                        f"AI bahosi ({ai_score}) mijoz bahosidan "
                        f"({client_rating:.1f}/5 ≈ {client_scaled:.0f}) "
                        f"{gap:.0f} ball {direction}"
                    ),
                }
            )

    return ReviewDecision(needs_review=bool(reasons), reasons=reasons)
