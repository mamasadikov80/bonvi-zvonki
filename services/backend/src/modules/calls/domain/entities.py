"""Qo'ng'iroq domeni."""

from enum import StrEnum


class CallDirection(StrEnum):
    OUTBOUND = "outbound"  # xodim qo'ng'iroq qilgan
    INBOUND = "inbound"  # client qo'ng'iroq qilgan


class CallStatus(StrEnum):
    """Qayta ishlash quvuridagi holat."""

    PENDING = "pending"  # yangi kelgan, hali qayta ishlanmagan
    TRANSCRIBING = "transcribing"  # ASR jarayonida
    SCORING = "scoring"  # LLM baholamoqda
    COMPLETED = "completed"  # tayyor
    FAILED = "failed"  # xatolik
    SKIPPED = "skipped"  # juda qisqa / javobsiz — baholanmaydi


class CallType(StrEnum):
    """Qo'ng'iroq turi — BAHOLANADIMI yoki yo'qmi shu bilan hal bo'ladi.

    Ish telefoni faqat savdo uchun ishlatilmaydi: xodim viloyat skladi
    bilan yuk haqida, buxgalteriya bilan kassa haqida gaplashadi, ba'zan
    uyiga qo'ng'iroq qiladi. Savdo rubrikasi bunday suhbatga nol beradi
    va xodimning o'rtachasini asossiz pasaytiradi.

    Shuning uchun FAQAT `SALES` baholanadi. Qolganlari sanaladi va
    ko'rinadi, lekin ballari ham, savdo KPI'siga ta'siri ham yo'q.
    """

    SALES = "sales"  # mijoz bilan savdo — YAGONA baholanadigan tur
    SERVICE = "service"  # mavjud mijozga xizmat: yetkazish, shikoyat
    INTERNAL = "internal"  # kompaniya ichida: sklad, buxgalteriya, hamkasb
    PERSONAL = "personal"  # ishga aloqasi yo'q shaxsiy suhbat
    UNCLEAR = "unclear"  # aniqlab bo'lmadi — taxminga ball qo'yilmaydi


class CallOutcome(StrEnum):
    """Transkriptdan aniqlangan natija signali.

    Diqqat: bu FAKT emas, SIGNAL. Ballga qo'shilmaydi (PLAN.md, Blok D).
    """

    ORDER_AGREED = "order_agreed"
    FOLLOW_UP = "follow_up"
    REJECTED = "rejected"
    INFO_ONLY = "info_only"
    UNCLEAR = "unclear"
