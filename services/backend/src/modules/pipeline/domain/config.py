"""Quvur sozlamalari — muhit o'zgaruvchilaridan.

Nega `SETTINGS_REGISTRY` da emas: bular vendor chegaralari va server
imkoniyati (parallel oqim soni, daqiqadagi so'rov), admin uchun emas —
DevOps uchun. Ular `docker-compose.yml` da ko'rinadi va konteynerni
qayta ishga tushirmasdan o'zgarmaydi.

Har biri EHTIYOTKOR standart qiymat bilan: sozlanmagan tizim ham
vendorni 429 ga urib qo'ymaydi.
"""

import os
from dataclasses import dataclass


def _int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return max(minimum, value)


def _float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return max(minimum, value)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    #: Bir vaqtda nechta qo'ng'iroq qayta ishlanadi (bitta jarayonda)
    concurrency: int
    #: ASR provayderiga daqiqada nechta so'rov (0 = cheklovsiz)
    asr_rpm: int
    #: LLM provayderiga daqiqada nechta so'rov (0 = cheklovsiz)
    llm_rpm: int
    #: 429 dan keyin nechta marta qayta urinamiz
    max_retries: int
    #: Birinchi kutish (soniya); keyingilari 2× o'sadi + jitter
    backoff_base_sec: float
    #: Kutishning yuqori chegarasi
    backoff_max_sec: float
    #: LLM javobi rubrikaga mos kelmasa nechta marta qayta so'raymiz
    invalid_retries: int
    #: Baholanmaydigan qisqa qo'ng'iroqlar (soniya)
    min_duration_sec: int
    #: Bitta qo'ng'iroqni qayta ishlash uchun umumiy vaqt chegarasi
    call_timeout_sec: float
    #: Ikki worker bitta qo'ng'iroqni baholab, ikki marta to'lamasligi uchun
    lock_ttl_sec: int
    #: Loglarda «... tirikmi?» degan savol tug'ilmasligi uchun
    progress_every: int

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            concurrency=_int("PIPELINE_CONCURRENCY", 4, minimum=1),
            asr_rpm=_int("PIPELINE_ASR_RPM", 60),
            llm_rpm=_int("PIPELINE_LLM_RPM", 120),
            max_retries=_int("PIPELINE_MAX_RETRIES", 4),
            backoff_base_sec=_float("PIPELINE_BACKOFF_BASE_SEC", 2.0, minimum=0.0),
            backoff_max_sec=_float("PIPELINE_BACKOFF_MAX_SEC", 60.0, minimum=0.1),
            # ⚠️ 1 EMAS, 2. Arzon modellar (`gemini-3.1-flash-lite`)
            # rubrika arifmetikasida ba'zan adashadi: blok bali
            # kriteriyalar yig'indisiga to'g'ri kelmaydi yoki manfiy
            # ball yozadi. Validator buni tutadi va XATO MATNINI keyingi
            # so'rovga qo'shib yuboradi — model odatda o'sha zahoti
            # tuzatadi. Sinovda 5 ta qo'ng'iroqdan 1 tasi aynan shu
            # sababdan yiqildi, qayta yurishda esa 2-urinishda o'tdi.
            # Narxi — yiqilgan qo'ng'iroqqa bitta qo'shimcha so'rov;
            # muqobili — butunlay bahosiz qolgan qo'ng'iroq.
            invalid_retries=_int("PIPELINE_INVALID_RETRIES", 2),
            min_duration_sec=_int("PIPELINE_MIN_DURATION_SEC", 30),
            call_timeout_sec=_float("PIPELINE_CALL_TIMEOUT_SEC", 900.0, minimum=30.0),
            lock_ttl_sec=_int("PIPELINE_LOCK_TTL_SEC", 1800, minimum=60),
            progress_every=_int("PIPELINE_PROGRESS_EVERY", 10, minimum=1),
        )


def load_config() -> PipelineConfig:
    """Har chaqiruvda o'qiydi — testda `monkeypatch.setenv` ishlashi uchun."""
    return PipelineConfig.from_env()
