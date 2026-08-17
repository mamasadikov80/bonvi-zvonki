"""Avtomatik so'rovnoma kadansi (Celery beat vazifasi).

MUAMMO. Sozlamalarda «Kadans (kun)» bor edi, lekin uni hech kim
o'qib ishga tushirmasdi: tizimda umuman rejalashtiruvchi yo'q edi.
So'rovnoma faqat admin tugma bosganda yaratilardi.

RESTART XAVFSIZLIGI — ENG MUHIM QISM.
  Vazifa «oxirgi marta qachon ishlaganini» xotirada ham, beat'ning
  jadval faylida ham SAQLAMAYDI. Qaror har safar BAZADAN qayta
  hisoblanadi: guruhning oxirgi so'rovnomasidan `period_days` kun
  o'tganmi?

  Shuning uchun server bir kunda ikki marta o'chib yonsa ham, beat
  jadval faylini yo'qotsa ham, vazifa qo'lda bir necha marta
  chaqirilsa ham — guruh `period_days` ichida IKKINCHI so'rovnomani
  olmaydi. Takrorlanishga qarshi himoya jadvalda emas, ma'lumotda.

  Xuddi shu sababdan vazifa tez-tez (soatiga bir marta) ishlashi
  mumkin: ortiqcha ishga tushish zararsiz. Bu esa server tushib
  qolgan soatni o'zi «quvib yetish» imkonini beradi — ertasi kunga
  qolib ketmaydi.

IKKI KALIT:
  `survey.enabled`   — umuman so'rovnoma yaratilsinmi (bosh kalit)
  `survey.auto_send` — odam aralashmasdan o'zi yaratilsinmi

Ikkalasi ham yoqilmasa vazifa hech narsa qilmaydi va buni logga
yozadi — «nega yubormadi?» degan savol javobsiz qolmasin.
"""

from typing import Any

import structlog
from celery import shared_task

from src.core.database import SessionFactory
from src.modules.groups.application.services import GroupService
from src.modules.pipeline.application.runner import run_async
from src.modules.surveys.application.services import (
    resolve_auto_send,
    resolve_period_days,
    resolve_survey_enabled,
)

log = structlog.get_logger(__name__)


async def _run_cadence() -> dict[str, Any]:
    async with SessionFactory() as session:
        if not await resolve_survey_enabled(session):
            log.info("survey.cadence.skipped", reason="survey.enabled=false")
            return {"status": "disabled", "created": 0}

        if not await resolve_auto_send(session):
            log.info("survey.cadence.skipped", reason="survey.auto_send=false")
            return {"status": "manual_only", "created": 0}

        period_days = await resolve_period_days(session)

        # `force=False` + oyna = `period_days`. Aynan shu ikkitasi
        # takrorlanishga qarshi himoyani beradi: oxirgi so'rovnomadan
        # `period_days` o'tmagan guruh `skipped` ga tushadi.
        report = await GroupService(session).broadcast_surveys(
            force=False, window_days=period_days
        )
        await session.commit()

        log.info(
            "survey.cadence.done",
            period_days=period_days,
            created=report.get("created"),
            reused=report.get("reused"),
            skipped=len(report.get("skipped") or []),
        )
        return {
            "status": "ok",
            "period_days": period_days,
            "created": report.get("created", 0),
            "reused": report.get("reused", 0),
            "skipped": len(report.get("skipped") or []),
        }


@shared_task(name="surveys.cadence")
def survey_cadence_task() -> dict[str, Any]:
    """Kadans bo'yicha yetib kelgan guruhlarga so'rovnoma qo'yadi.

    Guruhga xabar YUBORMAYDI — faqat navbatga yozadi. Yuborishni
    avvalgidek bot bajaradi (`GET /groups/pending-surveys`).
    """
    return run_async(_run_cadence())
