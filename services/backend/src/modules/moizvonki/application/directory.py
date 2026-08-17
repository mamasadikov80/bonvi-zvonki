"""MoyZvonki xodimlarini bizning `agents` ga ko'chirish uchun ma'lumot.

NEGA BU KERAK. Qo'ng'iroqlarni xodimga bog'lash `agents.external_id`
orqali ketadi, u esa MoyZvonki'dagi `user_id` yoki `user_account`.
Admin ularni qo'lda ko'chirsa — o'nlab xodimda bu zerikarli va bitta
xato harf butun bir xodimning qo'ng'iroqlarini «egasiz» qoldiradi.

TELEFON RAQAMI QAYERDAN. `company.list_employee` raqam qaytarmaydi
(faqat `id`, `email`, `display_name`, guruh). Lekin har qo'ng'iroqda
`src_number` — qaysi SIM'dan qilingani — bor. Shuning uchun oxirgi
kunlarning qo'ng'iroqlari o'qib chiqiladi va har xodim uchun ENG
KO'P uchragan raqam olinadi.

  · Eng ko'p uchragani olinadi, oxirgisi emas: xodim bir marta
    boshqa telefondan qo'ng'iroq qilgan bo'lsa, o'sha tasodifiy
    raqam butun kartochkaga yozilib qolmasin.
  · Raqam topilmasligi ODDIY holat: Android'da SIM o'z raqamini
    ko'pincha bermaydi (operator uni SIM'ga yozmaydi). Bunda maydon
    bo'sh qoladi va admin uni qo'lda to'ldiradi.

Raqam faqat TELEGRAM uchun kerak — xodim botga kontaktini yuborganda
tanish uchun. Qo'ng'iroqlarni bog'lashda u umuman ishlatilmaydi.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.modules.moizvonki.domain.entities import MoizvonkiEmployee
from src.modules.moizvonki.infrastructure.client import MoizvonkiClient

#: Raqamni aniqlash uchun necha kunlik qo'ng'iroq o'qiladi.
#: Ko'proq olish aniqlikni oshirmaydi — xodim raqamini har hafta
#: almashtirmaydi — lekin so'rovni sekinlashtiradi.
PHONE_LOOKBACK_DAYS = 7

#: Ko'riladigan qo'ng'iroqlar chegarasi. Haqiqiy hajmga qarab
#: tanlangan: 41 xodimda haftasiga ~2000 qo'ng'iroq, shuning uchun
#: 6000 bir haftani to'liq qamraydi va sanoq kesilmaydi.
PHONE_SCAN_LIMIT = 6_000


@dataclass(slots=True)
class DirectoryEntry:
    """Import oynasidagi bitta qator."""

    external_id: str
    """`agents.external_id` ga tushadigan qiymat — MoyZvonki `id`."""

    email: str | None
    display_name: str | None
    group_name: str | None
    role: int | None

    detected_phone: str | None
    """Qo'ng'iroqlardan aniqlangan raqam. `None` — topilmadi."""

    call_count: int
    """Oxirgi davrda nechta qo'ng'iroq qilgani — «bu odam savdo
    qiladimi yoki umuman qo'ng'iroq qilmaydimi» degan savolga javob."""

    truncated: bool = False
    """Skanerlash chegarasiga yetildi — `call_count` TO'LIQ EMAS.
    UI buni «kamida N ta» deb ko'rsatishi kerak."""

    linked_agent_id: str | None = None
    """Bizda allaqachon shu `external_id` bilan xodim bo'lsa — uning id si."""


async def load_directory(
    client: MoizvonkiClient,
    *,
    lookback_days: int = PHONE_LOOKBACK_DAYS,
) -> list[DirectoryEntry]:
    """MoyZvonki xodimlari + har biriga aniqlangan raqam va qo'ng'iroq soni.

    Ikkita so'rov guruhi: xodimlar ro'yxati va oxirgi qo'ng'iroqlar.
    Qo'ng'iroqlar sahifalab o'qiladi, `PHONE_SCAN_LIMIT` da to'xtaydi.
    """
    employees = await client.list_employees()

    phones: dict[str, Counter[str]] = {}
    #: marker -> qo'ng'iroq id lari. SANOQ EMAS, TO'PLAM.
    #
    # ⚠️ Sabab: bitta qo'ng'iroqda `user_id` ham, `user_account` ham
    # bo'lishi mumkin va biz ikkalasi bo'yicha ham indekslaymiz (qaysi
    # biri xodimga mos kelishini oldindan bilmaymiz). Oddiy sanoqda
    # o'sha qo'ng'iroq IKKI MARTA sanalardi va ekranda haqiqiy sondan
    # ikki barobar katta raqam chiqardi.
    calls: dict[str, set[str]] = {}

    now = datetime.now(UTC)
    since = now - timedelta(days=lookback_days)
    scanned = 0
    truncated = False

    # `iter_calls` SAHIFA qaytaradi, bitta qo'ng'iroq emas
    async for _page_number, page in client.iter_calls(since=since, until=now):
        for call in page.calls:
            for key in (call.user_id, call.user_account):
                if not key:
                    continue
                marker = key.strip().lower()
                calls.setdefault(marker, set()).add(call.db_call_id)
                if call.src_number:
                    phones.setdefault(marker, Counter())[call.src_number.strip()] += 1

        scanned += len(page.calls)
        if scanned >= PHONE_SCAN_LIMIT:
            truncated = True
            break

    return [_entry(employee, phones, calls, truncated) for employee in employees]


def _entry(
    employee: MoizvonkiEmployee,
    phones: dict[str, Counter[str]],
    calls: dict[str, set[str]],
    truncated: bool = False,
) -> DirectoryEntry:
    keys = [k for k in (employee.id, employee.email) if k]
    markers = [k.strip().lower() for k in keys]

    counter: Counter[str] = Counter()
    # BIRLASHMA — bir xil qo'ng'iroq ikkala marker ostida bo'lsa ham
    # bir marta sanaladi
    seen: set[str] = set()
    for marker in markers:
        counter.update(phones.get(marker, Counter()))
        seen |= calls.get(marker, set())
    total = len(seen)

    detected = counter.most_common(1)[0][0] if counter else None

    return DirectoryEntry(
        external_id=employee.id,
        email=employee.email,
        display_name=employee.display_name,
        group_name=employee.group_name,
        role=employee.role,
        detected_phone=detected,
        call_count=total,
        truncated=truncated,
    )
