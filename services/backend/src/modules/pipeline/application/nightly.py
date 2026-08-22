"""Kunlik avtomatik yurish — har kuni yarim tunda.

Bitta vazifa uch ishni ketma-ket bajaradi:

  1. MoyZvonki'dan oxirgi sutkadagi qo'ng'iroqlarni tortadi;
  2. shulardan baholanishi kerak bo'lganlarini navbatga qo'yadi;
  3. rahbarga kunlik Telegram xabarini yuboradi (agar YOQILGAN bo'lsa).

Tartib muhim: avval ma'lumot, keyin baholash. Teskarisida yangi
qo'ng'iroqlar bazaga tushmagan bo'lardi va vazifa bo'sh ishlardi.

⚠️ XABAR ENG OXIRIDA — VA AYNAN SHU VAZIFA ICHIDA. Uni alohida
`beat_schedule` yozuviga chiqarish mumkin edi, lekin o'shanda ikki
vazifaning tartibi vaqtga tayanardi: sinxronizatsiya cho'zilib
ketsa xabar ESKIRGAN ma'lumot bilan chiqib ketardi va rahbar
kechagi qo'ng'iroqlarni ko'rmagan ro'yxatni o'qirdi. Bitta vazifa
ichida esa tartib kod bilan kafolatlangan.

════════════════════════════════════════════════════════════════
 NEGA KECHASI
════════════════════════════════════════════════════════════════

Kunduzi xodimlar ishlaydi va MoyZvonki so'rovlari ularning
qo'ng'iroqlariga xalaqit qilmasligi kerak. Kechasi esa:
  · MoyZvonki bo'sh — sahifalar tez keladi;
  · AI chegaralari (RPM) kun davomida to'lgan bo'lsa tiklangan;
  · natijalar ertalab tayyor bo'ladi.

════════════════════════════════════════════════════════════════
 IDEMPOTENTLIK
════════════════════════════════════════════════════════════════

Vazifa ikki marta ishga tushsa ham zarar yo'q:
  · ingest `external_id` bo'yicha upsert qiladi — nusxa qator yo'q;
  · `select_calls(only_unscored=True)` allaqachon baholanganlarni
    olmaydi, ya'ni AI ga takroriy pul to'lanmaydi;
  · har qo'ng'iroqda Redis qulfi bor — ikki worker bitta qo'ng'iroqni
    baravar ishlay olmaydi.

Shuning uchun server tushib qolgan kunni qo'lda qaytarish xavfsiz.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.database import SessionFactory
from src.modules.moizvonki.application.factory import moizvonki_client
from src.modules.moizvonki.application.ingest import IngestService
from src.modules.pipeline.application.orchestrator import select_calls
from src.modules.pipeline.application.queue import enqueue_calls
from src.modules.sales.application.digest import run_daily_digest

log = structlog.get_logger(__name__)

#: Necha soatlik oraliq olinadi — aniq bir sutka.
#
# Vazifa yarim tunda ishga tushadi, ya'ni oyna to'liq o'tgan kunni
# qamraydi.
#
# ⚠️ Vazifa kechikib ishga tushsa (server band, qayta ishga
# tushirilgan) oynaning boshi ham suriladi va o'sha bir necha
# daqiqadagi qo'ng'iroqlar tushib qolishi mumkin. Amalda bu xavf
# deyarli yo'q: o'lchandi, 00:00–05:00 oralig'ida qo'ng'iroq
# bo'lmaydi (eng erta faollik 06:00 dan boshlanadi). Kerak bo'lsa
# qo'lda sinxronizatsiya har qanday oraliqni qoplaydi.
LOOKBACK_HOURS = 24

#: Bir yurishda ko'pi bilan shuncha qo'ng'iroq navbatga qo'yiladi.
#
# O'lchandi: kuniga ~840 qo'ng'iroq keladi, shundan ~500 tasida audio
# bor. 2000 — kunlik hajmdan ancha yuqori, ya'ni odatda chegara
# ishlamaydi. U faqat bitta holat uchun: MoyZvonki uzoq tushib turib,
# keyin bir necha kunlik ma'lumotni birdan bergan bo'lsa — o'shanda
# navbat bir kechada butun oylik hajmni yutib yubormasin.
MAX_QUEUE = 2000


async def run_nightly(*, now: datetime | None = None) -> dict[str, Any]:
    """Sinxronizatsiya + baholash. Hisobotni qaytaradi.

    Xatolar YUTILMAYDI, lekin sinxronizatsiya yiqilsa ham baholash
    bosqichi baribir ishlaydi: bazada kechagi, hali baholanmagan
    qo'ng'iroqlar qolgan bo'lishi mumkin va ularni MoyZvonki
    nosozligi tufayli qoldirib ketish noto'g'ri bo'lardi.
    """
    until = now or datetime.now(UTC)
    since = until - timedelta(hours=LOOKBACK_HOURS)
    report: dict[str, Any] = {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "fetched": 0,
        "created": 0,
        "updated": 0,
        "queued": 0,
        "sync_error": None,
        "digest": None,
    }

    # ── 1. MoyZvonki'dan tortish ──────────────────────────────
    try:
        async with SessionFactory() as session, moizvonki_client(session) as client:
            ingest = await IngestService(session, client).run(
                since=since, until=until, supervised=True
            )
        report["fetched"] = ingest.fetched
        report["created"] = ingest.created
        report["updated"] = ingest.updated
        log.info(
            "nightly.synced",
            fetched=ingest.fetched,
            created=ingest.created,
            updated=ingest.updated,
            no_agent=ingest.skipped_no_agent,
        )
    except Exception as exc:  # noqa: BLE001 — bosqich yiqilsa ham davom etamiz
        report["sync_error"] = str(exc)
        log.error("nightly.sync_failed", error=str(exc))

    # ── 2. Baholashga qo'yish ─────────────────────────────────
    #
    # Oyna sinxronizatsiyanikidan KENGROQ (48 soat). Sababi: kecha
    # AI chegarasiga urilgan yoki xato bilan tugagan qo'ng'iroqlar
    # bugun qayta urinilishi kerak. `only_unscored` tufayli
    # allaqachon baholanganlar qayta olinmaydi, ya'ni bu qo'shimcha
    # xarajat emas — faqat qoldirilganlarni quvib yetish.
    async with SessionFactory() as session:
        call_ids = await select_calls(
            session,
            date_from=until - timedelta(hours=48),
            date_to=until,
            only_unscored=True,
            limit=MAX_QUEUE,
        )

    if call_ids:
        enqueue_calls(call_ids)
        report["queued"] = len(call_ids)

    # ── 3. Rahbarga kunlik xabar ──────────────────────────────
    #
    # ⚠️ SUKUT BO'YICHA HECH NARSA YUBORILMAYDI. `run_daily_digest()`
    # birinchi navbatda `sales.digest_enabled` ni tekshiradi va u
    # o'chiq bo'lsa (sukut holati) darhol qaytadi — matn ham
    # yig'ilmaydi.
    #
    # Xato YUTILADI: Telegram tushib qolgani uchun butun tungi
    # yurishni «yiqildi» deb belgilash noto'g'ri bo'lardi — qo'ng'iroq
    # va baholash bosqichlari allaqachon bajarilgan. Sabab hisobotda
    # va logda qoladi.
    try:
        report["digest"] = await run_daily_digest()
    except Exception as exc:  # noqa: BLE001 — xabar butun yurishni yiqitmasin
        report["digest"] = {"sent": False, "reason": "error", "error": str(exc)}
        log.error("nightly.digest_failed", error=str(exc))

    log.info("nightly.done", **{k: v for k, v in report.items() if k != "sync_error"})
    return report
