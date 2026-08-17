"""MoyZvonki domeni — sof Python, HTTP kutubxonasini bilmaydi.

Manba (rasmiy hujjat): https://www.moizvonki.ru/guide/api/
  · REST bazaviy manzil:  https://<domen>.moizvonki.ru/api/v1
  · Har so'rovda: `user_name` (email), `api_key`, `action`
  · Qo'ng'iroqlar: `action: "calls.list"`
  · Xodimlar:     `action: "company.list_employee"`
  · Yozuv manzili qo'ng'iroq yozuvidagi `recording` maydonida keladi
    (faqat javob berilgan qo'ng'iroqlarda; javobsizda bo'sh satr).

⚠️ Bu yerda audio bilan bog'liq hech qanday fayl yo'li yo'q va bo'lmaydi.
Audio faqat `RecordingStream` orqali — oqim bilan — o'tadi.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import AppError

# ── Xatoliklar ────────────────────────────────────────────────
#
# Har bir nosozlik o'z sinfiga ega: "xatolik" degan umumiy xabar
# integratsiyani tuzatib bo'lmaydigan qiladi. Admin xabarni o'qib
# nima qilishni bilishi kerak.


class MoizvonkiError(AppError):
    """MoyZvonki bilan bog'liq har qanday nosozlik."""

    status_code = 502
    code = "moizvonki_error"


class MoizvonkiNotConfiguredError(MoizvonkiError):
    """Domen / login / API kalit sozlanmagan."""

    status_code = 503
    code = "moizvonki_not_configured"


class MoizvonkiUnreachableError(MoizvonkiError):
    """Domen yechilmadi, ulanish rad etildi yoki vaqt tugadi."""

    status_code = 502
    code = "moizvonki_unreachable"


class MoizvonkiAuthError(MoizvonkiError):
    """Login yoki API kalit noto'g'ri (yoki huquq yetarli emas)."""

    status_code = 502
    code = "moizvonki_auth"


class MoizvonkiBadResponseError(MoizvonkiError):
    """Server javob berdi, lekin javobni tushunib bo'lmadi."""

    status_code = 502
    code = "moizvonki_bad_response"


class RecordingNotFoundError(MoizvonkiError):
    """Yozuv yo'q: qo'ng'iroq javobsiz yoki saqlash muddati o'tgan."""

    status_code = 404
    code = "recording_not_found"


class RangeNotSatisfiableError(MoizvonkiError):
    """`Range` sarlavhasidagi oraliq fayl chegarasidan tashqarida."""

    status_code = 416
    code = "range_not_satisfiable"


# ── Sinxronizatsiya oynasi ────────────────────────────────────

#: Sinxronizatsiyada tanlash mumkin bo'lgan eng uzun davr (kun).
#
# NEGA CHEGARA BOR. Undan oldingi kunlarni tanlash BEFOYDA: MoyZvonki
# qo'ng'iroq metadatasini bir yil oldingisini ham beradi, lekin yozuv
# (audio) o'chirilgan bo'ladi. Audiosiz qo'ng'iroq esa bazaga umuman
# yozilmaydi — ya'ni admin keng oraliq tanlab, uzoq kutib, «0 ta yangi»
# degan javob oladi va nima xato ketganini bilmaydi.
#
# NEGA AYNAN 45. Bu — mijozning qarori. O'lchov shuni ko'rsatdi:
#   · «yozuvlar 30 kun saqlanadi» degan taxmin XATO edi — 76 kunlik
#     yozuv ham bemalol yuklandi;
#   · chegara aylanuvchi oyna ham emas: 2026-05-31 da yozuv yo'q,
#     2026-06-01 da bor, ya'ni QAT'IY SANA (o'sha kuni saqlash
#     siyosati o'zgargan ko'rinadi).
#
# Ya'ni haqiqiy foydali oyna 45 kundan uzun va vaqt o'tishi bilan
# o'sadi. Chegarani MoyZvonki'dan har safar o'lchab olish ham sinaldi
# (ikkilik qidiruv) va u ishladi, lekin tarmoqqa bog'liq bo'lgani
# uchun MoyZvonki sekinlashganda «bilmayman» deb qolardi — o'shanda
# butun sana tanlovi ishonchsiz bo'lib turardi.
#
# Shuning uchun oddiy, oldindan bilinadigan chegara tanlandi. Uni
# o'zgartirish — shu bitta raqamni o'zgartirish.
SYNC_MAX_DAYS = 45


# ── Kirish ma'lumotlari ───────────────────────────────────────


def normalise_base_url(domain: str) -> str:
    """Sozlamadagi domenni to'liq bazaviy manzilga aylantiradi.

    Admin nima yozishi mumkin — hammasi qabul qilinadi:
        `bonvi`                      → https://bonvi.moizvonki.ru
        `bonvi.moizvonki.ru`         → https://bonvi.moizvonki.ru
        `https://bonvi.moizvonki.ru/`→ https://bonvi.moizvonki.ru
        `http://stub:9000`           → http://stub:9000  (test stendi)
    """
    raw = (domain or "").strip().rstrip("/")
    if not raw:
        raise MoizvonkiNotConfiguredError(
            "MoyZvonki domeni kiritilmagan — Sozlamalar → MoyZvonki"
        )

    if "://" in raw:
        scheme = raw.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise MoizvonkiNotConfiguredError(
                f"MoyZvonki domeni noto'g'ri: «{scheme}://…» qo'llab-quvvatlanmaydi"
            )
        return raw

    host = raw
    # Nuqtasiz nom — bu subdomen, o'zimiz to'ldiramiz
    if "." not in host.split(":", 1)[0]:
        host = f"{host}.moizvonki.ru"
    return f"https://{host}"


@dataclass(frozen=True, slots=True)
class MoizvonkiCredentials:
    """Sozlamalardan o'qilgan ulanish ma'lumotlari."""

    base_url: str
    user_name: str
    api_key: str

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v1"

    @property
    def host_label(self) -> str:
        """Xato xabarlarida ko'rsatish uchun — kalitsiz, xavfsiz."""
        return self.base_url


# ── Qo'ng'iroq yozuvi ─────────────────────────────────────────
#
# Maydon nomlari rasmiy hujjatdagidek (calls.list javobi).

DIRECTION_INBOUND = 0
DIRECTION_OUTBOUND = 1


def _timestamp(value: Any) -> datetime | None:
    """UTC timestamp (soniya) → datetime. 0 va bo'sh qiymat → None."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return datetime.fromtimestamp(number, tz=UTC)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


#: `recording` maydonida «yozuv yo'q» ma'nosida kelishi mumkin bo'lgan
#: qiymatlar. Hujjatda javobsiz qo'ng'iroqda bo'sh satr keladi deyilgan,
#: ammo amalda o'rnatmaga qarab `0`, `null` yoki chiziqcha ham uchraydi.
#: Ular matn sifatida saqlansa, `has_recording` «yozuv bor» deb yolg'on
#: aytadi va quvur o'sha qo'ng'iroqni baholashga urinib xato beradi.
_NO_RECORDING = frozenset(
    {"0", "-", "—", "null", "none", "nil", "false", "no", "n/a", "undefined"}
)


def _flag(value: Any) -> bool:
    """`0/1`, `"0"/"1"`, `true/false`, `"true"/"false"` → bool.

    `bool(int(value))` yozib bo'lmaydi: MoyZvonki bu maydonni ba'zi
    o'rnatmalarda satr sifatida qaytaradi va `int("true")` butun
    sahifani `ValueError` bilan yiqitadi — ya'ni bitta g'alati qator
    tufayli sinxronizatsiya to'xtaydi.
    """
    if isinstance(value, bool):
        return value
    text = _text(value)
    if text is None:
        return False
    return text.lower() not in {"0", "false", "no", "null", "none"}


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _client_name(value: Any, number: str | None) -> str | None:
    """Mijoz nomi. Raqamning o'zi «nom» sifatida saqlanmaydi.

    MoyZvonki'da kontakt katalogda bo'lmasa `client_name` ko'pincha
    raqamning nusxasi bo'ladi (ba'zan boshqacha formatlangan). Uni nom
    deb saqlash ikki marta zarar qiladi: jadvalda foydasiz takror
    ko'rinadi va «nomi bor» degan yolg'on belgi beradi. Raqam alohida
    ustunda turadi va nom bo'lmaganda o'sha ko'rsatiladi.
    """
    text = _text(value)
    if text is None:
        return None
    digits = _digits(text)
    # Faqat raqamlardan iborat (formatlash belgilaridan tashqari) va
    # qo'ng'iroq raqami bilan bir xil tugaydi — bu nom emas
    if digits and not any(ch.isalpha() for ch in text):
        tail = _digits(number)
        if not tail or digits.endswith(tail[-9:]) or tail.endswith(digits[-9:]):
            return None
    return text


def _recording_link(value: Any) -> str | None:
    """`recording` maydonini ISHONCHLI havolaga aylantiradi.

    `None` qaytishi «bu qo'ng'iroqning audiosi yo'q» degani — ya'ni
    qo'ng'iroq umuman ko'chirilmaydi. Shuning uchun bu yerda ikki xato
    ham qimmat:

      · yolg'on «bor» — quvur audio kutadi, MoyZvonki 404 beradi;
      · yolg'on «yo'q» — haqiqiy suhbat jimgina yo'qoladi.

    Shu sababli faqat ANIQ bilingan ikki holat rad etiladi: joy egallab
    turuvchi qiymatlar va http(s) bo'lmagan sxema (`javascript:`,
    `data:` va shunga o'xshash — ular audio emas). Qolgan hamma narsa
    — nisbiy yo'l ham, to'liq manzil ham — o'tkaziladi.
    """
    text = _text(value)
    if text is None or text.lower() in _NO_RECORDING:
        return None
    if "://" in text:
        scheme = text.split("://", 1)[0].lower()
        return text if scheme in ("http", "https") else None
    # Sxemasiz, lekin `foo:bar` ko'rinishidagi qiymat — yo'l emas
    head = text.split("/", 1)[0]
    if ":" in head:
        return None
    return text


@dataclass(frozen=True, slots=True)
class MoizvonkiCall:
    """`calls.list` javobidagi bitta qo'ng'iroq."""

    db_call_id: str
    direction: int
    client_number: str | None
    client_name: str | None
    start_time: datetime
    answer_time: datetime | None
    end_time: datetime | None
    upload_time: datetime | None
    duration_sec: int
    answered: bool
    recording: str | None
    user_id: str | None
    user_account: str | None
    src_number: str | None
    event_pbx_call_id: str | None

    @property
    def is_outbound(self) -> bool:
        return self.direction == DIRECTION_OUTBOUND

    @property
    def has_recording(self) -> bool:
        return bool(self.recording)

    @property
    def client_label(self) -> str | None:
        """Mijozning ko'rsatiladigan nomi.

        Nomi bo'lmasa RAQAM qaytadi: «—» dan ko'ra raqam foydaliroq —
        menejer uni CRM'da qidira oladi. Ikkalasi ham bo'lmasa `None`.
        """
        return self.client_name or self.client_number

    @property
    def owner_label(self) -> str:
        """Xodimni odam o'qiy oladigan ko'rinishi (hisobot uchun)."""
        parts = [p for p in (self.user_account, self.user_id) if p]
        return " / ".join(parts) or "noma'lum"

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "MoizvonkiCall":
        call_id = _text(payload.get("db_call_id"))
        if not call_id:
            raise MoizvonkiBadResponseError(
                "MoyZvonki javobida `db_call_id` yo'q — qo'ng'iroqni "
                "aniqlab bo'lmaydi"
            )

        start = _timestamp(payload.get("start_time"))
        if start is None:
            raise MoizvonkiBadResponseError(
                f"Qo'ng'iroq {call_id}: `start_time` yo'q yoki noto'g'ri"
            )

        try:
            duration = int(payload.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0

        try:
            direction = int(payload.get("direction", DIRECTION_OUTBOUND))
        except (TypeError, ValueError):
            direction = DIRECTION_OUTBOUND

        number = _text(payload.get("client_number"))

        return cls(
            db_call_id=call_id,
            direction=direction,
            client_number=number,
            client_name=_client_name(payload.get("client_name"), number),
            start_time=start,
            answer_time=_timestamp(payload.get("answer_time")),
            end_time=_timestamp(payload.get("end_time")),
            upload_time=_timestamp(payload.get("upload_time")),
            duration_sec=max(duration, 0),
            answered=_flag(payload.get("answered")),
            recording=_recording_link(payload.get("recording")),
            user_id=_text(payload.get("user_id")),
            user_account=_text(payload.get("user_account")),
            src_number=_text(payload.get("src_number")),
            event_pbx_call_id=_text(payload.get("event_pbx_call_id")),
        )


@dataclass(frozen=True, slots=True)
class CallPage:
    """`calls.list` ning bir sahifasi.

    `next_offset` — hujjatdagi `results_next_offset`: keyingi so'rovda
    `from_offset` sifatida yuboriladi. `remains` 0 bo'lsa ro'yxat tugadi.
    """

    calls: tuple[MoizvonkiCall, ...]
    next_offset: int
    remains: int
    total_in_page: int

    @property
    def has_more(self) -> bool:
        # Ba'zi o'rnatmalar `results_remains` ni qaytarmaydi — u holda
        # `results_next_offset` > 0 bo'lishi davom belgisi bo'ladi.
        return self.remains > 0 or self.next_offset > 0


@dataclass(frozen=True, slots=True)
class MoizvonkiEmployee:
    """`company.list_employee` javobidagi xodim."""

    id: str
    email: str | None
    display_name: str | None
    group_name: str | None
    group_id: str | None
    role: int | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "MoizvonkiEmployee":
        try:
            role = int(payload["role"])
        except (KeyError, TypeError, ValueError):
            role = None
        return cls(
            id=_text(payload.get("id")) or "",
            email=_text(payload.get("email")),
            display_name=_text(payload.get("display_name")),
            group_name=_text(payload.get("group_name")),
            group_id=_text(payload.get("group_id")),
            role=role,
        )


# ── Audio oqimi ───────────────────────────────────────────────


@dataclass(slots=True)
class RecordingStream:
    """Ochilgan audio oqimi.

    `chunks` — `AsyncIterator[bytes]`. Butun tana HECH QACHON xotiraga
    yig'ilmaydi va diskka yozilmaydi: baytlar MoyZvonki'dan brauzerga
    to'g'ridan-to'g'ri o'tadi.
    """

    status_code: int
    content_type: str
    chunks: AsyncIterator[bytes]
    content_length: int | None = None
    content_range: str | None = None
    accept_ranges: str | None = None

    @property
    def is_partial(self) -> bool:
        return self.status_code == 206


# ── Ingest hisoboti ───────────────────────────────────────────


@dataclass(slots=True)
class UnmatchedOwner:
    """Bizda mos xodimi topilmagan MoyZvonki foydalanuvchisi.

    Bunday qo'ng'iroq JIMGINA tashlanmaydi — admin shu ro'yxatni ko'rib
    `agents.external_id` ni to'ldiradi va sinxronizatsiyani qayta ishga
    tushiradi (ikkinchi yurishda ular qo'shiladi).
    """

    user_id: str | None
    user_account: str | None
    call_count: int = 0

    @property
    def label(self) -> str:
        parts = [p for p in (self.user_account, self.user_id) if p]
        return " / ".join(parts) or "noma'lum"


@dataclass(slots=True)
class IngestReport:
    """Sinxronizatsiya natijasi — idempotentlikni ko'rsatadi."""

    since: datetime
    until: datetime | None
    pages: int = 0
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped_no_agent: int = 0

    skipped_not_selected: int = 0
    """Admin tanlamagan xodimga tegishli — bu XATO EMAS.

    `skipped_no_agent` dan ataylab ajratilgan: u «bu odam bizning
    tizimda umuman yo'q» degani va tuzatish talab qiladi, bu esa
    oddiy filtr natijasi. Ikkalasi bitta songa qo'shilsa, admin
    haqiqiy muammoni filtr shovqini ichida ko'rmay qolardi."""

    skipped_no_recording: int = 0
    """Audiosi yo'q — bazaga UMUMAN yozilmagan.

    Javobsiz qo'ng'iroq, muddati o'tgan yozuv yoki xizmat
    qo'ng'irog'i. Ilgari bunday qatorlar `status='skipped'` bilan
    saqlanardi va ro'yxatning katta qismini 0:00 li, bahosiz, mijozsiz
    qatorlar egallab olardi — ular hech qachon baholanmasa ham. Endi
    ular faqat SHU sonda ko'rinadi."""

    unmatched: list[UnmatchedOwner] = field(default_factory=list)
    truncated: bool = False

    def note_unmatched(self, call: MoizvonkiCall) -> None:
        for row in self.unmatched:
            if row.user_id == call.user_id and row.user_account == call.user_account:
                row.call_count += 1
                return
        self.unmatched.append(
            UnmatchedOwner(
                user_id=call.user_id,
                user_account=call.user_account,
                call_count=1,
            )
        )
