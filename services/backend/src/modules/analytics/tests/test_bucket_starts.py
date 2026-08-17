"""`_bucket_starts()` — grafikdagi bo'sh kunlarni to'ldirish uchun oraliqlar.

Sof unit test: bazasiz, ilovasiz.

NEGA MUHIM: bu funksiya PostgreSQL `date_trunc` bilan AYNAN bir xil
natija berishi shart. Bir belgiga farq qilsa, to'ldirilgan kalitlar
bazadagilarga tushmaydi va haqiqiy qiymatlar «yo'q» bo'lib qoladi —
grafik jimgina bo'sh chiziladi.
"""

from datetime import UTC, datetime

from src.modules.analytics.application.services import AnalyticsService

def _d(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _starts(start: str, end: str, bucket: str = "day"):
    return AnalyticsService._bucket_starts(_d(start), _d(end), bucket)


def test_kunlik_oraliq_ikkala_chegarani_ham_oladi() -> None:
    assert _starts("2026-08-14", "2026-08-16") == [
        "2026-08-14",
        "2026-08-15",
        "2026-08-16",
    ]


def test_bitta_kun_bitta_nuqta_beradi() -> None:
    """Bir kunlik davrda o'q yig'ilib qolmasligi kerak."""
    assert _starts("2026-08-16", "2026-08-16") == ["2026-08-16"]


def test_hafta_dushanbadan_boshlanadi() -> None:
    """Postgres `date_trunc('week')` ISO haftani dushanbadan boshlaydi.

    2026-08-05 — chorshanba, uning haftasi 2026-08-03 (dushanba).
    """
    assert _starts("2026-08-05", "2026-08-16", "week") == [
        "2026-08-03",
        "2026-08-10",
    ]


def test_oy_birinchi_kundan_boshlanadi_va_yil_oshadi() -> None:
    assert _starts("2026-11-20", "2027-02-03", "month") == [
        "2026-11-01",
        "2026-12-01",
        "2027-01-01",
        "2027-02-01",
    ]


def test_teskari_oraliq_bosh_royxat() -> None:
    """`date_from > date_to` — xato emas, shunchaki natija yo'q."""
    assert _starts("2026-08-16", "2026-08-14") == []


def test_juda_uzoq_davr_toldirilmaydi() -> None:
    """Chegaradan oshsa `None` — chaqiruvchi to'ldirishdan voz kechadi.

    5 yil × 365 kun ≈ 1826 nuqta: brauzer ham, ko'z ham ko'tarmaydi.
    """
    assert _starts("2021-01-01", "2026-01-01") is None


def test_chegara_atrofida_toldirish_ishlaydi() -> None:
    """`MAX_BUCKETS` dan bittaga kam — hali to'ldiriladi."""
    from datetime import timedelta

    start = _d("2026-01-01")
    end = start + timedelta(days=AnalyticsService.MAX_BUCKETS - 1)
    periods = AnalyticsService._bucket_starts(start, end, "day")
    assert periods is not None
    assert len(periods) == AnalyticsService.MAX_BUCKETS


def test_sanasiz_toldirilmaydi() -> None:
    assert AnalyticsService._bucket_starts(None, _d("2026-08-16"), "day") is None
    assert AnalyticsService._bucket_starts(_d("2026-08-16"), None, "day") is None


def test_notanish_razrez_toldirilmaydi() -> None:
    """Noma'lum `bucket` da to'ldirish emas, borini qaytarish xavfsizroq."""
    assert _starts("2026-08-14", "2026-08-16", "quarter") is None
