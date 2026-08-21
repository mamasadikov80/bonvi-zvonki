"""Bazadagi qo'ng'iroqlarga turni QAYTA qo'yish — ommaviy, bir so'rovda.

NEGA QUVURDAN TASHQARIDA HAM KERAK. Tur — qo'ng'iroqning XUSUSIYATI,
baholash jarayonining natijasi emas. Quvur esa hamma qatorga tegmaydi:

  · audiosi yo'q qo'ng'iroq (javobsizlar — hajmning ~35% i) umuman
    navbatga tushmaydi;
  · allaqachon baholangan qo'ng'iroq qayta olinmaydi.

Ya'ni faqat quvurga tayanilsa, ro'yxatning katta qismi «tasniflanmagan»
bo'lib qolardi va boshqaruv panelidagi «turlari bo'yicha» qatori
haqiqatni ko'rsatmasdi.

⚠️ RO'YXAT VAQT O'TIB TO'LADI. Kompaniya liniyalari `calls.agent_number`
dan yig'iladi, ya'ni yangi xodimning raqami birinchi sinxronizatsiyadan
keyin paydo bo'ladi. Shuning uchun bu funksiya har sinxronizatsiyadan
keyin ishlaydi va turlarni QAYTA hisoblaydi — kecha «savdo» bo'lgan
qo'ng'iroq bugun «ichki» bo'lib chiqishi mumkin va bu XATO emas, bu
tizimning o'zini tuzatishi.

Shu sababli ichkiga o'tgan qo'ng'iroqning ESKI BAHOSI ham o'chiriladi:
aks holda ekranda «ichki suhbat, baholanmaydi» deb turardi-yu,
analitikada ball hisobga olinaverardi.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import and_, delete, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.calls.application.internal_directory import load_company_lines
from src.modules.calls.domain.entities import CallType
from src.modules.calls.domain.routing import EXTENSION_MAX_DIGITS, PHONE_KEY_DIGITS
from src.modules.calls.infrastructure.models import CallModel

log = structlog.get_logger(__name__)

#: Ustundagi raqamning faqat raqamlari (formatlash belgilarisiz).
#: `ix_calls_phone_tail` indeksi aynan shu ifodaga qo'yilgan.
_DIGITS = func.regexp_replace(func.coalesce(CallModel.client_phone, ""), r"\D", "", "g")
_TAIL = func.right(_DIGITS, PHONE_KEY_DIGITS)


@dataclass(slots=True)
class RetypeReport:
    internal: int = 0
    sales: int = 0
    scores_removed: int = 0

    @property
    def changed(self) -> int:
        return self.internal + self.sales


async def retype_calls(session: AsyncSession, *, commit: bool = True) -> RetypeReport:
    """Barcha qo'ng'iroqlarga turni qayta qo'yadi.

    Faqat O'ZGARADIGAN qatorlar yoziladi (`IS DISTINCT FROM`), ya'ni
    takroriy chaqiruv bazaga tegmaydi va arzon.
    """
    report = RetypeReport()
    lines = await load_company_lines(session)
    if not lines:
        # Ro'yxat bo'sh — hamma raqam «tashqi» bo'lib chiqardi va ichki
        # suhbatlar savdo sifatida baholanib ketardi. Taxmin qilmaymiz.
        log.warning("calls.retype_skipped", reason="company_directory_empty")
        return report

    shartlar = [
        # ATS qisqa raqami — tashqaridan bunday raqamga qo'ng'iroq
        # qilib bo'lmaydi, ya'ni u ta'rifi bo'yicha ichki liniya
        func.length(_DIGITS).between(1, EXTENSION_MAX_DIGITS),
    ]
    if lines.keys:
        shartlar.append(_TAIL.in_(sorted(lines.keys)))
    for suffix in lines.suffixes:
        # Suffiks qoidasi (`*700`) faqat TO'LIQ raqamda tekshiriladi:
        # qisqa ATS raqami yuqoridagi shart bilan allaqachon tutilgan
        shartlar.append(
            and_(
                func.length(_DIGITS) >= PHONE_KEY_DIGITS,
                _DIGITS.like(f"%{suffix}"),
            )
        )
    ichki_sharti = or_(*shartlar)

    ichki_sabab = func.concat(
        func.coalesce(CallModel.client_phone, "raqamsiz"),
        literal(" — kompaniya liniyasi yoki ATS ichki raqami, ikkala tomon ham xodim"),
    )
    tashqi_sabab = func.concat(
        func.coalesce(CallModel.client_phone, "raqamsiz"),
        literal(" — kompaniya liniyalari ro'yxatida yo'q, ya'ni tashqi suhbat"),
    )

    natija = await session.execute(
        update(CallModel)
        .where(ichki_sharti, CallModel.call_type.is_distinct_from(CallType.INTERNAL.value))
        .values(
            call_type=CallType.INTERNAL.value,
            call_type_reason=ichki_sabab,
            call_type_confidence=1.0,
        )
    )
    report.internal = natija.rowcount or 0

    natija = await session.execute(
        update(CallModel)
        .where(~ichki_sharti, CallModel.call_type.is_distinct_from(CallType.SALES.value))
        .values(
            call_type=CallType.SALES.value,
            call_type_reason=tashqi_sabab,
            call_type_confidence=1.0,
        )
    )
    report.sales = natija.rowcount or 0

    # ── Ichkiga o'tgan qo'ng'iroqning eski bahosi ──────────────
    #
    # Baho — hisoblanadigan ma'lumot, uni qayta olish mumkin; yolg'on
    # ko'rsatkichni esa hech kim sezmaydi.
    from src.modules.scoring.infrastructure.models import CallScoreModel

    ichki_idlar = select(CallModel.id).where(
        CallModel.call_type == CallType.INTERNAL.value
    )
    natija = await session.execute(
        delete(CallScoreModel).where(CallScoreModel.call_id.in_(ichki_idlar))
    )
    report.scores_removed = natija.rowcount or 0

    if commit:
        await session.commit()

    if report.changed or report.scores_removed:
        log.info(
            "calls.retyped",
            internal=report.internal,
            sales=report.sales,
            scores_removed=report.scores_removed,
            company_numbers=len(lines.keys),
            suffixes=list(lines.suffixes),
        )
    return report
