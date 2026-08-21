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

    IKKITA tur bor, boshqasi yo'q:

      · `INTERNAL` — ikkala tomon ham BIZNING xodimimiz. Transkript
        olinadi (suhbat o'qiladi), lekin savdo rubrikasi qo'llanmaydi.
      · `SALES`    — qolgan HAMMASI, ya'ni tashqariga chiqqan suhbat.
        Baholanadi.

    ⚠️ NEGA MAZMUN BO'YICHA TASNIF OLIB TASHLANDI. Ilgari AI transkriptni
    o'qib «savdo / xizmat / ichki / shaxsiy» deb ajratardi va ARALASHTIRIB
    yuborardi: mijozlarning aksariyati ESKI mijoz bo'lgani uchun ular ham
    «sklad qoldig'i qancha», «narx qanday» deb qisqa gaplashadi — bu esa
    hamkasb suhbatidan matn jihatidan farq qilmaydi. O'lchandi: tasniflangan
    98 qo'ng'iroqning 82 tasi «ichki» deb belgilangan, savdo esa atigi 9 ta.
    Ya'ni haqiqiy savdo suhbatlari baholanmay qolgan.

    Endi tur MAZMUNDAN emas, RAQAMDAN aniqlanadi: suhbatdoshning raqami
    kompaniyaning o'z liniyalari ro'yxatida bo'lsa — ichki, aks holda
    savdo. Bu qaror taxminga tayanmaydi va LLM chaqiruvi TALAB QILMAYDI.
    """

    SALES = "sales"  # tashqi suhbat — baholanadi
    INTERNAL = "internal"  # ikki xodim o'rtasida — baholanmaydi


class CallOutcome(StrEnum):
    """Transkriptdan aniqlangan natija signali.

    Diqqat: bu FAKT emas, SIGNAL. Ballga qo'shilmaydi (PLAN.md, Blok D).
    """

    ORDER_AGREED = "order_agreed"
    FOLLOW_UP = "follow_up"
    REJECTED = "rejected"
    INFO_ONLY = "info_only"
    UNCLEAR = "unclear"
