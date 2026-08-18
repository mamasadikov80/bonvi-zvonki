"""Celery worker — fon vazifalari (ASR + LLM baholash).

Ishga tushirish (docker-compose'dagi `worker` xizmati shuni qiladi):

    celery -A src.worker.celery_app worker --loglevel=INFO -Q pipeline

Nega alohida xizmat: bitta qo'ng'iroqni baholash — bir necha o'n
soniya (audio oqimi + LLM). Buni HTTP so'rovi ichida bajarish
brauzerni ushlab turadi va uzilishda ish yo'qoladi. Navbat esa
qayta urinishni, cheklangan parallellikni va ko'rinadigan holatni
beradi.

Redis bazalari bo'lingan: `/0` — ilova keshi, `/1` — bot FSM,
`/2` — Celery broker, `/3` — natijalar. Bir bazada aralashtirish
`FLUSHDB` da hammasini yo'q qiladi.
"""

import os

import structlog
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown

from src.core.config import settings

# ⚠️ Import SHART, garchi bu yerda ishlatilmasa ham. Worker jarayoni
# FastAPI ilovasini ko'tarmaydi, ya'ni modellar o'z-o'zidan metadata'ga
# tushmaydi. Vazifa `flush` qilganda SQLAlchemy jadvallarni bog'liqlik
# tartibida saralaydi va yetishmagan jadvalda `NoReferencedTableError`
# bilan uziladi — ish paytida, importda emas.
# Batafsil: `src/core/models.py`.
from src.core import models as _models  # noqa: F401
from src.modules.pipeline.application.runner import get_loop, reset_loop

log = structlog.get_logger(__name__)


def _redis_db(index: int) -> str:
    """`REDIS_URL` ning baza raqamini almashtiradi."""
    base = settings.REDIS_URL.rstrip("/")
    head, _, tail = base.rpartition("/")
    if head and tail.isdigit():
        return f"{head}/{index}"
    return f"{base}/{index}"


BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip() or _redis_db(2)
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "").strip() or _redis_db(3)

PIPELINE_QUEUE = "pipeline"

celery_app = Celery(
    "zvonki",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "src.modules.pipeline.application.tasks",
        "src.modules.surveys.application.tasks",
    ],
)

celery_app.conf.update(
    task_default_queue=PIPELINE_QUEUE,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tashkent",
    enable_utc=True,
    # Vazifa BAJARILGACH tasdiqlanadi: worker o'lsa ish yo'qolmaydi
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Natijalar bir kundan ortiq turmasin — Redis shishib ketmasin
    result_expires=86_400,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Bitta qo'ng'iroq 15 daqiqadan oshsa — nimadir qotgan
    task_soft_time_limit=900,
    task_time_limit=1_020,
    worker_send_task_events=True,
    task_send_sent_event=True,
    # structlog stdout'ga yozadi; Celery uni ushlab oladi. Standart
    # daraja WARNING — u holda oddiy `info` xabarlari ogohlantirishga
    # o'xshab ko'rinadi va haqiqiy muammo ko'zdan qochadi.
    worker_redirect_stdouts_level="INFO",
)

# ══════════════════════════════════════════════════════════════
#  DAVRIY VAZIFALAR (celery beat)
#
#  ⚠️ JADVAL — KAFOLAT EMAS. Beat oxirgi ishga tushish vaqtini
#  konteyner ichidagi faylda saqlaydi; konteyner qayta yaratilsa
#  fayl yo'qoladi va beat vazifani darhol qayta yuborishi mumkin.
#  Server kunda ikki marta o'chib yonsa ham shu holat.
#
#  Shuning uchun takrorlanishga qarshi himoya JADVALDA EMAS:
#  `surveys.cadence` har safar bazadan «bu guruhga oxirgi marta
#  qachon yuborilgan?» deb so'raydi va `period_days` o'tmagan
#  bo'lsa hech narsa yaratmaydi. Vazifa kuniga 100 marta ishga
#  tushsa ham natija bir xil.
#
#  Soatiga bir marta, 10:00–18:00 (Toshkent) oralig'ida:
#    · tunda mijoz guruhiga xabar tushmasin
#    · server bir soat tushib qolsa keyingi soatda quvib yetsin
# ══════════════════════════════════════════════════════════════

celery_app.conf.beat_schedule = {
    "survey-cadence": {
        "task": "surveys.cadence",
        "schedule": crontab(minute="0", hour="10-18"),
        "options": {"queue": PIPELINE_QUEUE},
    },
    # ── Kunlik yurish ─────────────────────────────────────────
    #
    # Har kuni yarim tunda: oxirgi sutkadagi qo'ng'iroqlarni
    # MoyZvonki'dan tortadi va baholashga qo'yadi.
    #
    # Vaqt mintaqasi yuqorida `Asia/Tashkent` deb belgilangan, ya'ni
    # `hour=0` aynan Toshkent yarim tuni (UTC 19:00). Buni UTC deb
    # o'ylab qo'yish 5 soatlik siljish berardi — natijalar ertalab
    # emas, kunduzi tayyor bo'lardi.
    #
    # Nega kechasi: kunduzi xodimlar ishlaydi va MoyZvonki so'rovlari
    # ularga xalaqit qilmasligi kerak; AI chegaralari ham tiklangan
    # bo'ladi; natijalar esa ertalabgacha tayyor bo'ladi.
    "nightly-pipeline": {
        "task": "pipeline.nightly",
        "schedule": crontab(minute="0", hour="0"),
        "options": {"queue": PIPELINE_QUEUE},
    },
}


@worker_process_init.connect
def _init_worker_process(**_kwargs: object) -> None:
    """Fork'dan keyin: meros qolgan loop va DB pool'ini tashlaymiz."""
    from src.core.database import engine

    reset_loop()
    loop = get_loop()
    loop.run_until_complete(engine.dispose())
    log.info("worker.process_ready", pid=os.getpid())


@worker_process_shutdown.connect
def _shutdown_worker_process(**_kwargs: object) -> None:
    from src.core.database import engine

    try:
        get_loop().run_until_complete(engine.dispose())
    except Exception:  # noqa: BLE001 — o'chishda xato loglarni ifloslantirmasin
        pass
