"""Qo'ng'iroq turini aniqlash — quvurdagi ENG ARZON bosqich.

Bitta savol: suhbatdosh bizning xodimimizmi? Javob RAQAMDAN olinadi,
transkriptdan emas, ya'ni:

  · LLM chaqiruvi YO'Q — bir tiyin ham turmaydi;
  · audio ham, transkript ham kerak emas — shuning uchun bosqich
    transkripsiyadan OLDIN turadi va javobsiz qo'ng'iroqda ham ishlaydi;
  · natija barqaror: bir xil raqam har doim bir xil turni beradi.

⚠️ NEGA AI TASNIFI OLIB TASHLANDI. Ilgari bu yerda transkriptni o'qib
«savdo / xizmat / ichki / shaxsiy» deb ajratadigan LLM chaqiruvi turardi.
U yanglishardi va aynan eng muhim tomonga qarab: mijozlarning aksariyati
ESKI mijoz, ular ham «qoldiq qancha», «narxlar qanaqa» deb qisqa
gaplashadi — matn jihatidan bu hamkasb suhbatidan farq qilmaydi.
O'lchandi: tasniflangan 98 qo'ng'iroqdan 82 tasi «ichki» deb belgilangan,
savdo esa atigi 9 ta. Ya'ni haqiqiy savdo suhbatlarining ko'pi
BAHOLANMAY qolgan va buni hech kim sezmagan.

⚠️ IDEMPOTENTLIK BU YERDA KERAK EMAS va ATAYLAB YO'Q. Boshqa bosqichlar
natijani saqlab qayta hisoblamaydi, chunki ular pul turadi. Bu bosqich
bepul, kompaniya liniyalari ro'yxati esa vaqt o'tib TO'LADI (yangi
xodimning raqami birinchi sinxronizatsiyadan keyin paydo bo'ladi).
Shuning uchun har yurishda qaytadan hisoblanadi — tizim o'zini o'zi
tuzatadi.
"""

from time import perf_counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.calls.application.internal_directory import load_company_lines
from src.modules.calls.domain.entities import CallType
from src.modules.calls.domain.routing import reason_uz, resolve_type
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.domain.entities import (
    DirectoryEmptyError,
    Stage,
    StageOutcome,
    StageResult,
)

log = structlog.get_logger(__name__)


class RouteStage:
    """Raqam bo'yicha tur qo'yadi. Provayderga chiqmaydi."""

    async def run(
        self, session: AsyncSession, call: CallModel
    ) -> tuple[StageOutcome, CallType]:
        started = perf_counter()

        lines = await load_company_lines(session)
        if not lines:
            # ⚠️ TAXMIN QILMAYMIZ. Bo'sh ro'yxatda har qanday raqam
            # «tashqi» bo'lib chiqadi va hamkasblar suhbati ham savdo
            # sifatida baholanib ketardi — pul ketadi, ball asossiz
            # tushadi va qo'ng'iroq boshqa navbatga tushmaydi.
            raise DirectoryEmptyError(
                "Kompaniya liniyalari ro'yxati bo'sh — qo'ng'iroq turini "
                "aniqlab bo'lmaydi. MoyZvonki'dan sinxronizatsiya qiling: "
                "xodimlarning o'z raqamlari o'shanda o'rganiladi.",
                stage=Stage.ROUTE.value,
            )
        tur = resolve_type(call.client_phone, lines)
        sabab = reason_uz(tur, call.client_phone)

        oldingi = call.call_type
        call.call_type = tur.value
        call.call_type_reason = sabab[:300]
        # Taxmin yo'q — qaror raqamdan kelib chiqadi.
        call.call_type_confidence = 1.0

        elapsed_ms = int((perf_counter() - started) * 1000)
        if oldingi != tur.value:
            # Tur O'ZGARGANI muhim hodisa: eski baho o'chirilishi yoki
            # aksincha, qo'ng'iroq birinchi marta baholanishi mumkin.
            log.info(
                "pipeline.routed",
                call_id=str(call.id),
                call_type=tur.value,
                previous=oldingi,
                client_phone=call.client_phone,
            )

        return (
            StageOutcome(
                stage=Stage.ROUTE,
                result=StageResult.DONE,
                detail=sabab[:200],
                provider_calls=0,
                elapsed_ms=elapsed_ms,
            ),
            tur,
        )
