"""30 kunlik ma'lumotni bo'laklab tortib oladi — ALOHIDA jarayon.

Nega HTTP orqali emas: backend `--reload` rejimida ishlaydi va har
fayl tahririda qayta yuklanib, ketayotgan uzoq so'rovni o'ldiradi.
Bu skript mustaqil jarayon, shuning uchun unga ta'sir qilmaydi.

🔒 MoyZvonki'ga faqat O'QISH so'rovi ketadi (`calls.list`).
"""
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from src.core.database import SessionFactory
from src.modules.moizvonki.application.factory import moizvonki_client
from src.modules.moizvonki.application.ingest import IngestService

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
STEP = 2  # kun


async def main() -> None:
    until = datetime.now(UTC)
    start = until - timedelta(days=DAYS)
    jami = {"fetched": 0, "created": 0, "updated": 0, "no_agent": 0, "no_rec": 0}

    kursor = start
    while kursor < until:
        chegara = min(kursor + timedelta(days=STEP), until)
        try:
            async with SessionFactory() as session, moizvonki_client(session) as client:
                r = await IngestService(session, client).run(
                    since=kursor, until=chegara, supervised=True, max_calls=60000
                )
            jami["fetched"] += r.fetched
            jami["created"] += r.created
            jami["updated"] += r.updated
            jami["no_agent"] += r.skipped_no_agent
            jami["no_rec"] += r.skipped_no_recording
            print(
                f"  {kursor:%d.%m} → {chegara:%d.%m}: ko'rildi {r.fetched:5}  "
                f"yangi {r.created:5}  yangilandi {r.updated:5}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 — bir bo'lak yiqilsa qolgani davom etsin
            print(f"  {kursor:%d.%m} → {chegara:%d.%m}: XATO — {exc}", flush=True)
        kursor = chegara

    print("\nJAMI:", jami, flush=True)

asyncio.run(main())
