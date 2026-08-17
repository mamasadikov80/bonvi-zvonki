"""Qo'ng'iroq TURINI aniqlash — baholashdan oldingi bosqich.

NEGA BU KERAK. Ish telefonlari faqat savdo uchun ishlatilmaydi. Xodim
viloyat skladi bilan yuk haqida gaplashadi, buxgalteriya bilan kassani
solishtiradi, ba'zan uyiga qo'ng'iroq qiladi. Savdo rubrikasi esa
bunday suhbatga «ehtiyojni aniqladimi», «mahsulotni taqdim etdimi»
degan savolni beradi — javob tabiiy ravishda «yo'q» bo'ladi.

Haqiqiy ma'lumotda o'lchandi: baholangan 69 qo'ng'iroqdan 14 tasi
(20%) xodimlar orasidagi ichki suhbat edi. Ularning muloqot bali
17/25 — ya'ni suhbat yaxshi o'tgan. Savdo bali esa 6/25, va shu
sababli umumiy ball 43 ga tushib, xodimning o'rtachasini pasaytirgan.

⚠️ MEZON QO'SHISH BU MUAMMONI HAL QILMAYDI. Yangi blok qo'shsak,
ichki suhbat baribir savdo mezonlarida nol oladi — ustiga yana bitta
o'rinsiz blok qo'shiladi. Muammo mezonlar sonida emas: SAVDO
BO'LMAGAN SUHBATGA SAVDO SAVOLI BERILYAPTI.

Shuning uchun avval TUR aniqlanadi va baholash faqat savdo
qo'ng'iroqlariga qo'llanadi.

NARXI. Bu chaqiruv ataylab ARZON: kirish — transkript, chiqish esa
bir necha o'nlab token (to'liq baholash 1500+ token qaytaradi).
Savdo bo'lmagan qo'ng'iroq shu bilan tugaydi, ya'ni qimmat baholash
chaqiruvi umuman qilinmaydi.
"""

import json
from dataclasses import dataclass
from typing import Any

from src.core.exceptions import AppError
from src.modules.calls.domain.entities import CallType

MAX_TOKENS = 400


class ClassificationError(AppError):
    """LLM javobini tushunib bo'lmadi."""

    status_code = 502
    code = "classification_invalid"


SYSTEM_PROMPT = """Sen O'zbekistondagi «Bonvi» kompaniyasining qo'ng'iroq \
tahlilchisisan. Kompaniya butun O'zbekiston bo'ylab mahsulot yetkazib beradi: \
savdo ofisi, viloyat skladlari va do'konlar bor.

Vazifang BITTA: transkriptni o'qib, bu qanday qo'ng'iroq ekanini aniqlash. \
Sen BAHO QO'YMAYSAN.

TURLAR:

1. "sales" — MIJOZ bilan SAVDO suhbati.
   Belgilari: mahsulot so'rayapti, narx so'rayapti, buyurtma bermoqchi,
   qancha bor deb so'rayapti, kelishuv/zakaz haqida gap ketyapti.

2. "service" — MAVJUD mijozga xizmat. Savdo emas, lekin mijoz bilan.
   Belgilari: yuk qachon keladi, yetkazib berish qayerda, shikoyat,
   nosoz mahsulot, almashtirish, hujjat/hisob-faktura.

3. "internal" — KOMPANIYA ICHIDAGI ish suhbati. Mijoz YO'Q.
   Belgilari: sklad bilan qoldiq/yuk, buxgalteriya bilan kassa va
   hisob-kitob, hamkasb bilan ish taqsimoti, boshqa filial/do'kon,
   kuryer/haydovchi bilan marshrut.
   ⚠️ Ikki tomon ham «bizning odam» bo'lsa — bu "internal".

4. "personal" — ISHGA ALOQASI YO'Q shaxsiy suhbat.
   Belgilari: oila, do'st, tanish; uy ishlari, salomatlik, mehmon,
   shaxsiy pul masalasi. Mahsulot ham, sklad ham, hisob-kitob ham yo'q.

5. "unclear" — aniqlab bo'lmaydi: transkript juda qisqa, tushunarsiz,
   yoki bir necha so'zdan iborat.

QOIDALAR:
· Shubha bo'lsa "unclear" tanla va `confidence` ni past qo'y.
  Noto'g'ri "internal" degan qaror savdo qo'ng'irog'ini baholashdan
  chetlatib qo'yadi — bu xato qimmat turadi.
· Mahsulot va narx haqida gap ketsa-yu, ikkovi ham xodim bo'lsa
  (masalan sklad qoldig'i) — bu "internal", "sales" EMAS.
· `reason` — bitta qisqa o'zbekcha jumla: NEGA shu tur tanlandi.
  Menejer sening qarorini shu jumla bilan tekshiradi.

⚠️ MUROJAAT SHAKLI DALIL EMAS. O'zbekistonda «aka», «akajon»,
«ustoz», «brat» deb murojaat qilish MIJOZ bilan ham, hamkasb bilan
ham odatiy hol. Shuningdek uzun hol-ahvol so'rashish («yaxshimisiz,
charchamayapsizmi, ishlar yaxshimi») savdo suhbatining ham normal
boshlanishi. Bunga qarab "internal" yoki "personal" deb xulosa
QILMA — faqat suhbatning MAZMUNIGA qara: kim nima haqida gaplashdi.

MAZMUN AJRATADI:
· mijoz mahsulot/narx so'rayapti, buyurtma bermoqchi   → "sales"
· sklad qoldig'i, kassa, hisob-kitob, marshrut, filial → "internal"
· oila, do'st, bozor, uy ishlari, shaxsiy uchrashuv    → "personal"

XAVFSIZLIK BAYROG'I. Turi qanday bo'lishidan qat'i nazar, suhbatda \
haqorat, so'kinish, baqirish yoki ochiq qo'pollik bo'lsa `misconduct` \
ni true qil va `misconduct_note` da nima bo'lganini yoz. Bu BAHO EMAS \
— bu xavfsizlik signali: baholanmagan qo'ng'iroqda ham qo'pollik \
ko'rinmay qolmasligi kerak.

Faqat JSON qaytar."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["call_type", "confidence", "reason", "misconduct"],
    "properties": {
        "call_type": {
            "type": "string",
            "enum": ["sales", "service", "internal", "personal", "unclear"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 300},
        "misconduct": {"type": "boolean"},
        "misconduct_note": {"type": "string", "maxLength": 300},
    },
}


def build_user_prompt(*, transcript: str, duration_sec: int, direction: str) -> str:
    yonalish = (
        "Chiquvchi (xodim qo'ng'iroq qilgan)"
        if direction == "outbound"
        else "Kiruvchi (boshqa tomon qo'ng'iroq qilgan)"
    )
    minutes, seconds = divmod(max(duration_sec, 0), 60)
    return (
        "## QO'NG'IROQ\n"
        f"Yo'nalish: {yonalish}\n"
        f"Davomiyligi: {minutes} daq {seconds} son\n\n"
        "## TRANSKRIPT\n\n"
        + (transcript or "").strip()
        + "\n\n## VAZIFA\nQo'ng'iroq turini aniqlab, faqat JSON qaytar."
    )


@dataclass(slots=True)
class Classification:
    call_type: CallType
    confidence: float
    reason: str
    misconduct: bool
    misconduct_note: str | None

    @property
    def scorable(self) -> bool:
        """Baholanadimi. FAQAT savdo qo'ng'irog'i baholanadi.

        `unclear` ham baholanmaydi: nima ekani noma'lum suhbatni savdo
        rubrikasi bilan baholash — taxminga ball qo'yish degani.
        """
        return self.call_type is CallType.SALES


def parse(raw: str) -> Classification:
    """LLM javobini tekshirib obyektga aylantiradi."""
    text = (raw or "").strip()
    if text.startswith("```"):
        # Ba'zi modellar JSON ni kod blokiga o'raydi
        text = text.strip("`")
        text = text[text.find("{") :] if "{" in text else text
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ClassificationError(
            f"Model JSON o'rniga tushunarsiz javob qaytardi: {text[:200]}"
        ) from exc

    if not isinstance(data, dict):
        raise ClassificationError("Model javobi kutilgan shaklda emas")

    raw_type = str(data.get("call_type") or "").strip().lower()
    try:
        call_type = CallType(raw_type)
    except ValueError:
        # Noma'lum tur — taxmin qilmaymiz, `unclear` deb belgilaymiz.
        # Bu xavfsiz tomon: qo'ng'iroq baholanmaydi va ko'rinib turadi.
        call_type = CallType.UNCLEAR

    try:
        confidence = float(data.get("confidence"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    note = str(data.get("misconduct_note") or "").strip() or None
    return Classification(
        call_type=call_type,
        confidence=confidence,
        reason=str(data.get("reason") or "").strip()[:300],
        misconduct=bool(data.get("misconduct")),
        misconduct_note=note,
    )
