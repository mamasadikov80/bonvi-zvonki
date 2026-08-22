"""Rahbarga kunlik Telegram xabari (shartnomaning 7-bo'limi, 3-punkt).

════════════════════════════════════════════════════════════════
 ⚠️ SUKUT BO'YICHA O'CHIQ — VA BU ENG MUHIM QOIDA
════════════════════════════════════════════════════════════════

Bu modul tizimdagi YAGONA tashqariga chiqadigan amalni bajaradi:
begona Telegram chatiga xabar yozadi. Noto'g'ri guruhga tushgan
xabarni qaytarib bo'lmaydi, shuning uchun himoya bir emas, TO'RT
qavat:

  1. `sales.digest_enabled` sukut bo'yicha `false` — kalit yoqilmasa
     kunlik vazifa matnni umuman yig'maydi ham;
  2. `sales.digest_chat_id` bo'sh bo'lsa hech qayerga yuborilmaydi
     (logga ogohlantirish yoziladi — jimgina o'tib ketmaydi);
  3. `telegram.bot_token` bo'lmasa ham to'xtaydi;
  4. sinov xabari FAQAT foydalanuvchi tugmani bosganda ketadi
     (`POST /sales/digest/test`) va hech qanday jadvalga bog'lanmagan.

Testlarda haqiqiy Telegram API CHAQIRILMAYDI: yagona chiqish nuqtasi
`infrastructure/telegram.py` va u almashtiriladi.

════════════════════════════════════════════════════════════════
 XABAR NIMA UCHUN AYNAN SHUNDAY
════════════════════════════════════════════════════════════════

Rahbar telefonda o'qiydi va ro'yxatni to'liq ko'chirib berish
maqsad emas — buning uchun panel bor. Xabarning vazifasi bitta:
**bugun tekshirishga arziydigan narsa bormi?** Shuning uchun:

  · uchala son ham turadi (`ok` / `suspicious` / `not_checkable`) —
    shartnomaning 4-bo'limi: hech narsa yashirilmaydi, «tekshirib
    bo'lmadi» soni ham ko'rinib tursin;
  · xodimlar kesimi eng ko'p shubhalisidan boshlanadi va beshtadan
    keyin «va yana N ta» bilan kesiladi;
  · savdolar ro'yxati eng KATTA summadan — pul qancha ko'p bo'lsa,
    tekshirishning qiymati shuncha yuqori;
  · har qatorda DALIL bor (qaysi qoida, oxirgi suhbat qachon) —
    rahbar xabarning o'ziga qarab «bu nimaga shubhali?» degan
    savolga javob topsin;
  · oxirida ayblov emasligi ochiq yozilgan. Bu bezak emas: ro'yxat
    ayblov sifatida o'qilsa, tizim bir hafta ichida ishonchni
    yo'qotadi (shartnoma, 1-bo'lim).

⚠️ 4096 BELGI — TELEGRAM CHEGARASI. Undan uzun xabar yuborilmaydi
(400 xato), ya'ni «uzun bo'lsa kesilar» degan umid ish bermaydi:
xabar butunlay YO'QOLARDI. Shuning uchun matn bir necha marta,
tobora qisqaroq shaklda yig'iladi va sig'gani yuboriladi.
"""

import html
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as env_settings
from src.core.database import SessionFactory
from src.modules.groups.domain.entities import GONE_STATUSES
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.sales.application.compliance import (
    LOCAL_TZ,
    ComplianceFilter,
    ComplianceRow,
    ComplianceService,
    ComplianceSort,
    ReviewState,
    Verdict,
    resolve_window_days,
)
from src.modules.sales.domain.entities import SaleOpType
from src.modules.sales.infrastructure.models import SaleDigestModel, SaleModel
from src.modules.sales.infrastructure.telegram import (
    TELEGRAM_TEXT_LIMIT,
    send_message,
)
from src.modules.settings.application.services import SettingsService

log = structlog.get_logger(__name__)

# ══════════════════════════════════════════════════════════════
#  Sozlama kalitlari
# ══════════════════════════════════════════════════════════════

ENABLED_KEY = "sales.digest_enabled"
CHAT_ID_KEY = "sales.digest_chat_id"
MIN_AMOUNT_KEY = "sales.digest_min_amount"
BOT_TOKEN_KEY = "telegram.bot_token"

#: Xabar bir kunlik savdolar ustidan yig'iladi va ular Python'da
#: sanaladi. Kunlik hajm o'lchandi: 11 kunda 1 039 savdo, ya'ni
#: ~95 ta. 5 000 — undan o'n barobar ko'p, lekin chegara BOR
#: bo'lishi shart: bir yillik eksport bir kunga yuklab yuborilsa
#: (import faylni sana bo'yicha ajratmaydi) butun jadval xotiraga
#: tortilardi.
MAX_ROWS = 5_000

#: Xodimlar kesimida ko'pi bilan shuncha qator, qolgani «va yana N ta».
TOP_AGENTS = 5

#: Eng katta shubhali savdolardan ko'pi bilan shuncha qator.
TOP_SALES = 5

#: Chegaraga sig'masa shuncha qatorgacha tushiriladi (shartnoma: 3–5).
MIN_TOP_SALES = 3

#: Mijoz nomi shundan uzun bo'lsa qisqartiriladi. SAP da nom ba'zan
#: butun bir manzil bo'lib keladi va bitta qator butun xabarni yeb
#: qo'yardi.
MAX_PARTNER_NAME = 38

TASHKENT = ZoneInfo(LOCAL_TZ)


# ══════════════════════════════════════════════════════════════
#  Yig'ilgan ma'lumot
# ══════════════════════════════════════════════════════════════


@dataclass(slots=True)
class AgentLine:
    name: str | None
    """`None` — filiali xodimga biriktirilmagan savdolar."""

    sales: int
    suspicious: int


@dataclass(slots=True)
class DigestData:
    """Xabarga kiradigan hamma narsa — matndan ALOHIDA.

    Ajratilgani ataylab: sonlarni tekshiradigan test matn shaklidan
    mustaqil bo'lsin, matnni tekshiradigan test esa bazaga
    bog'lanmasin.
    """

    day: date
    window_days: int
    min_amount: float
    total: int
    ok: int
    suspicious: int
    not_checkable: int
    agents: list[AgentLine] = field(default_factory=list)
    """Faqat shubhalisi BOR xodimlar — ko'pidan kamiga."""

    top: list[ComplianceRow] = field(default_factory=list)
    """Eng katta shubhali savdolar — summasi bo'yicha."""

    skipped_by_amount: int = 0
    """Summa chegarasi tufayli xabarga kirmagan savdolar soni."""

    truncated: bool = False
    """`True` — kunlik savdo `MAX_ROWS` dan oshdi, sonlar to'liq emas."""


@dataclass(slots=True)
class DigestOutcome:
    """Nima bo'ldi — chaqiruvchi (vazifa ham, endpoint ham) shunga qaraydi."""

    sent: bool
    reason: str | None = None
    """Nega yuborilmadi: `disabled` | `no_chat` | `no_token` |
    `no_sales` | `no_new_import` | `bot_not_in_chat` | `send_failed`."""

    text: str = ""
    """Yig'ilgan matn. Yuborilmagan bo'lsa ham qaytariladi — sinov
    tugmasi bosgan odam nimani yuborayotganini KO'RIB tursin."""

    day: date | None = None
    chat_id: str | None = None
    error: str | None = None
    counts: dict[str, int] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════
#  Sozlamalarni o'qish
# ══════════════════════════════════════════════════════════════


def _as_bool(value: Any) -> bool:
    """Sozlama qiymatini mantiqiy turga keltiradi.

    ⚠️ Bo'sh yoki tushunarsiz qiymat — `False`. Bu bo'lim uchun
    «bilmasam yubormayman» yagona to'g'ri sukut: teskarisida buzuq
    sozlama guruhga xabar yuborib qo'yardi.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "ha"}
    return bool(value)


def _as_amount(value: Any) -> float:
    """`sales.digest_min_amount` — buzuq qiymatda 0 (hammasi kiradi)."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    return amount if amount > 0 else 0.0


# ══════════════════════════════════════════════════════════════
#  Ma'lumot yig'ish
# ══════════════════════════════════════════════════════════════


async def latest_sale_day(session: AsyncSession) -> date | None:
    """Xabar QAYSI KUN uchun yig'iladi.

    ⚠️ «Kecha» EMAS, «oxirgi import qilingan kun». SAP eksporti qo'lda
    yuklanadi va odatda bir-ikki kun kechikadi: qat'iy «kecha» desak,
    xabar muntazam ravishda BO'SH kun ustidan chiqardi va rahbar uni
    o'qishni tashlab qo'yardi. Sana xabarning sarlavhasida ochiq
    yozilgani uchun chalkashlik ham bo'lmaydi.
    """
    return (
        await session.execute(
            select(func.max(SaleModel.occurred_on)).where(
                SaleModel.op_type == SaleOpType.SALE.value
            )
        )
    ).scalar_one_or_none()


def _passes_amount(row: ComplianceRow, min_amount: float) -> bool:
    """Summa chegarasidan o'tdimi.

    ⚠️ Summasi NOMA'LUM savdo (`amount_usd is None`) HAR DOIM o'tadi.
    O'lchab bo'lmagan narsani pul chegarasi bilan jimgina o'chirib
    tashlash bu bo'limning ma'nosiga zid: «bilmadim» degan javob
    «kichik» degani emas.
    """
    if min_amount <= 0 or row.amount_usd is None:
        return True
    return row.amount_usd >= min_amount


async def collect(
    session: AsyncSession, *, min_amount: float = 0.0
) -> DigestData | None:
    """Bir kunlik xulosani yig'adi. Savdo umuman bo'lmasa — `None`.

    ⚠️ SONLAR `ComplianceService` DAN KELADI, qaytadan hisoblanmaydi.
    Xabardagi «41 shubhali» paneldagi son bilan BIR XIL bo'lishi
    shart, aks holda rahbar qaysi biriga ishonishni bilmaydi.
    Shuning uchun bu yerda yangi SQL yo'q: o'sha xizmatning bir
    kunlik kesimi olinadi va Python'da sanaladi (kunlik hajm ~95
    qator — bu ish arzon).
    """
    day = await latest_sale_day(session)
    if day is None:
        return None

    window_days = await resolve_window_days(session)
    page = await ComplianceService(session).page(
        ComplianceFilter(
            since=day,
            until=day,
            window_days=window_days,
            # ⚠️ `ALL` — ATAYLAB. Sukut `new` bo'lsa, rahbar kechqurun
            # bir nechta savdoni ko'rib chiqqanda kunlik xabardagi
            # sonlar paneldagidan kam chiqardi va farqni hech kim
            # tushuntira olmasdi.
            review=ReviewState.ALL.value,
        ),
        page=1,
        page_size=MAX_ROWS,
        sort=ComplianceSort.AMOUNT,
        order="desc",
    )

    rows = [row for row in page.items if _passes_amount(row, min_amount)]
    skipped = len(page.items) - len(rows)

    counts = {Verdict.OK: 0, Verdict.SUSPICIOUS: 0, Verdict.NOT_CHECKABLE: 0}
    by_agent: dict[tuple[Any, str | None], AgentLine] = {}
    for row in rows:
        counts[Verdict(row.verdict.verdict)] += 1
        key = (row.agent_id, row.agent_name)
        line = by_agent.get(key)
        if line is None:
            line = by_agent[key] = AgentLine(
                name=row.agent_name, sales=0, suspicious=0
            )
        line.sales += 1
        if row.verdict.verdict == Verdict.SUSPICIOUS.value:
            line.suspicious += 1

    agents = sorted(
        (line for line in by_agent.values() if line.suspicious > 0),
        # Ikkilamchi mezon — tartib barqaror bo'lsin: bir xil sonli
        # ikki xodim har kecha o'rin almashib tursa, xabar
        # o'zgargandek ko'rinardi.
        key=lambda line: (-line.suspicious, line.name or "￿"),
    )

    return DigestData(
        day=day,
        window_days=window_days,
        min_amount=min_amount,
        total=len(rows),
        ok=counts[Verdict.OK],
        suspicious=counts[Verdict.SUSPICIOUS],
        not_checkable=counts[Verdict.NOT_CHECKABLE],
        agents=agents,
        top=[
            row
            for row in rows
            if row.verdict.verdict == Verdict.SUSPICIOUS.value
        ][:TOP_SALES],
        skipped_by_amount=skipped,
        truncated=page.total > len(page.items),
    )


# ══════════════════════════════════════════════════════════════
#  Matn
# ══════════════════════════════════════════════════════════════


def _esc(text: str | None) -> str:
    """Telegram HTML uchun xavfsiz matn.

    Mijoz nomida `&` va `<` uchraydi («ООО "Бонви" & Ко»). Ular
    qochirilmasa Telegram butun xabarni rad etadi — ya'ni bitta
    mijoz nomi tufayli kunlik xabar umuman kelmay qolardi.
    """
    return html.escape(text or "", quote=False)


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _short_day(value: date) -> str:
    return value.strftime("%d.%m")


def _money(value: float | None) -> str:
    """`5 610 $`. Noma'lum summa — ochiq aytiladi."""
    if value is None:
        return "summa noma'lum"
    return f"{value:,.0f}".replace(",", " ") + " $"


def _agent_name(name: str | None) -> str:
    return name or "xodim biriktirilmagan"


def _evidence(row: ComplianceRow) -> str:
    """Qoidani TUSHUNTIRADIGAN dalil — «nega shubhali» degan savolga javob.

    Rahbar xabarning o'zidan javob topsin: panelga kirmasdan ham
    «oxirgi suhbat to'qqiz kun oldin bo'lgan» degan fakt ko'rinib
    tursin (shartnoma, 4-bo'lim: har qator tekshiriladigan bo'lsin).
    """
    verdict = row.verdict
    if verdict.last_call_at is None:
        return "suhbat umuman bo'lmagan"

    local = verdict.last_call_at.astimezone(TASHKENT)
    days = verdict.days_before
    if days is None:
        when = _short_day(local.date())
    elif days == 0:
        when = f"{_short_day(local.date())} (o'sha kuni)"
    else:
        when = f"{_short_day(local.date())} ({days} kun oldin)"

    who = verdict.last_call_agent
    tail = f"{when}, {_esc(who)}" if who else when
    return f"oxirgi suhbat: {tail}"


def _partner(row: ComplianceRow) -> str:
    name = (row.partner_name or row.partner_code or "—").strip()
    if len(name) > MAX_PARTNER_NAME:
        name = name[: MAX_PARTNER_NAME - 1].rstrip() + "…"
    return _esc(name)


def _panel_link() -> str | None:
    """«Panelda ochish» havolasi. Manzil noma'lum bo'lsa — havola YO'Q.

    Ishlamaydigan havola («localhost») rahbar telefonida xatolik
    sahifasini ochardi, bu esa butun xabarga bo'lgan ishonchni
    tushirardi. Yo'qligi yomonligidan yaxshiroq.
    """
    base = (env_settings.PUBLIC_WEB_URL or "").strip().rstrip("/")
    return f"{base}/sales" if base else None


def render(data: DigestData, *, top_agents: int, top_sales: int) -> str:
    """Xabar matnini yig'adi. Uzunlikni TEKSHIRMAYDI — `build_text` qiladi."""
    lines: list[str] = [
        f"🔎 <b>Savdo nazorati — {_day(data.day)}</b>",
        "",
        f"✅ Toza: <b>{data.ok}</b>",
        f"⚠️ Shubhali: <b>{data.suspicious}</b>",
        f"❔ Tekshirib bo'lmadi: <b>{data.not_checkable}</b>",
        f"<i>Oyna: savdo kuni + oldingi {data.window_days} kun</i>",
    ]

    if data.min_amount > 0:
        lines.append(
            f"<i>Chegara: {_money(data.min_amount)} dan past savdolar "
            f"kirmadi ({data.skipped_by_amount} ta)</i>"
        )
    if data.truncated:
        lines.append("<i>⚠️ Savdo juda ko'p — sonlar to'liq emas</i>")

    if data.suspicious == 0:
        lines += ["", "Shubhali savdo yo'q — bu kun bo'yicha savol qolmadi."]

    # ── Xodimlar kesimi ───────────────────────────────────────
    if data.agents and top_agents > 0:
        lines += ["", "<b>Xodimlar kesimi</b>"]
        for line in data.agents[:top_agents]:
            lines.append(
                f"• {_esc(_agent_name(line.name))} — "
                f"<b>{line.suspicious}</b> shubhali / {line.sales} savdo"
            )
        rest = len(data.agents) - top_agents
        if rest > 0:
            lines.append(f"<i>…va yana {rest} ta xodim</i>")

    # ── Eng katta shubhali savdolar ───────────────────────────
    if data.top and top_sales > 0:
        lines += ["", "<b>Eng katta shubhali savdolar</b>"]
        for index, row in enumerate(data.top[:top_sales], start=1):
            rules = ", ".join(row.verdict.broken_rules) or "—"
            lines.append(
                f"{index}. {_short_day(row.occurred_on)} · {_partner(row)} · "
                f"<b>{_money(row.amount_usd)}</b>"
            )
            lines.append(
                f"    {_esc(_agent_name(row.agent_name))} · {rules} · "
                f"{_evidence(row)}"
            )

    # ── Yakun ─────────────────────────────────────────────────
    lines.append("")
    link = _panel_link()
    if link:
        lines.append(f'<a href="{_esc(link)}">Panelda ochish</a>')
    lines.append(
        "<i>Bu ro'yxat hech kimni AYBLAMAYDI — u tekshirish uchun "
        "tayyorlangan. Qaror sizniki.</i>"
    )
    return "\n".join(lines)


def _clamp(text: str) -> str:
    """Oxirgi chora: chegaraga sig'maganini QATOR bo'yicha kesadi.

    ⚠️ Kesish faqat qator chegarasida bo'ladi. Belgi bo'yicha kessak
    ochiq qolgan `<b>` teg xabarni butunlay yaroqsiz qilardi va
    Telegram uni rad etardi — ya'ni «qisqartirish» xabarni yo'qotish
    bilan tugardi.
    """
    if len(text) <= TELEGRAM_TEXT_LIMIT:
        return text
    tail = "\n…"
    cut = text[: TELEGRAM_TEXT_LIMIT - len(tail)]
    edge = cut.rfind("\n")
    return (cut[:edge] if edge > 0 else cut) + tail


def build_text(data: DigestData) -> str:
    """Telegram chegarasiga SIG'ADIGAN matn.

    Qisqartirish tartibi tasodifiy emas — eng kam foydali narsa
    birinchi ketadi:

      1. savdolar ro'yxati 5 dan 3 gacha (shartnomadagi eng kam son);
      2. xodimlar kesimi 5 → 3 → 1 → butunlay olib tashlanadi;
      3. shundan keyin ham sig'masa — qator bo'yicha kesiladi.

    Sonlar va yakundagi jumla HECH QACHON tushib qolmaydi: xabarning
    ma'nosi ularda.
    """
    plans = (
        (TOP_AGENTS, TOP_SALES),
        (TOP_AGENTS, 4),
        (TOP_AGENTS, MIN_TOP_SALES),
        (3, MIN_TOP_SALES),
        (1, MIN_TOP_SALES),
        (0, MIN_TOP_SALES),
    )
    text = ""
    for top_agents, top_sales in plans:
        text = render(data, top_agents=top_agents, top_sales=top_sales)
        if len(text) <= TELEGRAM_TEXT_LIMIT:
            return text
    return _clamp(text)


# ══════════════════════════════════════════════════════════════
#  Takrorlanmaslik
# ══════════════════════════════════════════════════════════════


async def import_watermark(session: AsyncSession) -> datetime | None:
    """Bazadagi eng oxirgi savdo importi vaqti."""
    return (
        await session.execute(select(func.max(SaleModel.imported_at)))
    ).scalar_one_or_none()


async def last_sent_watermark(session: AsyncSession) -> datetime | None:
    """Oxirgi MUVAFFAQIYATLI kunlik xabar qaysi importgacha bo'lgan.

    ⚠️ Faqat `daily` va faqat `ok`. Sinov xabari hisobga olinmaydi
    (aks holda bir marta sinab ko'rish o'sha kechaning haqiqiy
    xabarini o'chirib qo'yardi), muvaffaqiyatsiz urinish ham
    hisobga olinmaydi (aks holda Telegram bir marta yiqilganda
    xabar butunlay yo'qolardi).
    """
    return (
        await session.execute(
            select(func.max(SaleDigestModel.watermark))
            .where(SaleDigestModel.kind == "daily")
            .where(SaleDigestModel.ok.is_(True))
        )
    ).scalar_one_or_none()


# ══════════════════════════════════════════════════════════════
#  Bosh oqim
# ══════════════════════════════════════════════════════════════


async def _bot_is_gone(session: AsyncSession, chat_id: str) -> bool:
    """Bot o'sha guruhdan chiqarilganmi (bilsak).

    `telegram_groups` — botning o'z reyestri. Chat u yerda bo'lmasa
    (masalan rahbar bilan shaxsiy yozishma) tekshiruv o'tkazib
    yuboriladi: bilmaslik — rad etish uchun asos emas.
    """
    try:
        numeric = int(chat_id)
    except ValueError:
        return False

    status = (
        await session.execute(
            select(TelegramGroupModel.bot_status).where(
                TelegramGroupModel.chat_id == numeric
            )
        )
    ).scalar_one_or_none()
    return status is not None and status in GONE_STATUSES


async def run_digest(
    session: AsyncSession, *, manual: bool = False
) -> DigestOutcome:
    """Kunlik xabarni yig'adi va (ruxsat bo'lsa) yuboradi.

    `manual=False` — kechasi, avtomatik. HAMMA himoya ishlaydi.
    `manual=True` — foydalanuvchi «Sinov xabari» tugmasini bosdi:
        · `sales.digest_enabled` TEKSHIRILMAYDI — tugmaning butun
          ma'nosi shu: kalitni yoqishdan OLDIN matnni ko'rish;
        · «yangi import bo'lmadi» ham tekshirilmaydi — odam ataylab
          so'radi, takror emas;
        · lekin chat va token baribir SHART — manzilsiz xabar
          yuborib bo'lmaydi;
        · yozuv `kind='test'` bo'lib tushadi va kechasi keladigan
          haqiqiy xabarga TA'SIR QILMAYDI.
    """
    values = await SettingsService(session).get_all_values()

    if not manual and not _as_bool(values.get(ENABLED_KEY)):
        # ⚠️ Sukut holati. Ogohlantirish YOZILMAYDI: har kecha
        # takrorlanadigan «warning» loglarni ifloslantirardi va
        # haqiqiy nosozlik ko'zdan qochardi.
        log.info("sales.digest.disabled")
        return DigestOutcome(sent=False, reason="disabled")

    min_amount = _as_amount(values.get(MIN_AMOUNT_KEY))
    data = await collect(session, min_amount=min_amount)
    if data is None:
        log.info("sales.digest.no_sales")
        return DigestOutcome(sent=False, reason="no_sales")

    counts = {
        "total": data.total,
        "ok": data.ok,
        "suspicious": data.suspicious,
        "not_checkable": data.not_checkable,
    }

    watermark = await import_watermark(session)
    if not manual:
        last = await last_sent_watermark(session)
        if last is not None and watermark is not None and watermark <= last:
            # Yangi savdo importi bo'lmagan — xabar kechagining aynan
            # o'zi bo'lardi. Takroriy xabar shovqin, shovqin esa
            # xabarni o'qimaslikka olib keladi.
            log.info("sales.digest.no_new_import", day=str(data.day))
            return DigestOutcome(
                sent=False, reason="no_new_import", day=data.day, counts=counts
            )

    text = build_text(data)

    chat_id = str(values.get(CHAT_ID_KEY) or "").strip()
    if not chat_id:
        log.warning(
            "sales.digest.no_chat",
            hint=(
                "Sozlamalar → «Savdo nazorati» → «Qaysi Telegram chatga "
                "yuborilsin» to'ldirilmagan — xabar yuborilmadi"
            ),
        )
        return DigestOutcome(
            sent=False, reason="no_chat", text=text, day=data.day, counts=counts
        )

    token = str(values.get(BOT_TOKEN_KEY) or "").strip()
    if not token:
        log.warning(
            "sales.digest.no_token",
            hint="Sozlamalar → «Telegram bot» → «Bot tokeni» to'ldirilmagan",
        )
        return DigestOutcome(
            sent=False,
            reason="no_token",
            text=text,
            day=data.day,
            chat_id=chat_id,
            counts=counts,
        )

    if await _bot_is_gone(session, chat_id):
        log.warning("sales.digest.bot_not_in_chat", chat_id=chat_id)
        return DigestOutcome(
            sent=False,
            reason="bot_not_in_chat",
            text=text,
            day=data.day,
            chat_id=chat_id,
            counts=counts,
        )

    result = await send_message(token=token, chat_id=chat_id, text=text)

    session.add(
        SaleDigestModel(
            kind="test" if manual else "daily",
            covered_on=data.day,
            watermark=watermark,
            chat_id=chat_id[:32],
            ok=result.ok,
            error=result.error,
        )
    )
    await session.commit()

    if not result.ok:
        return DigestOutcome(
            sent=False,
            reason="send_failed",
            text=text,
            day=data.day,
            chat_id=chat_id,
            error=result.error,
            counts=counts,
        )

    log.info(
        "sales.digest.sent",
        kind="test" if manual else "daily",
        day=str(data.day),
        chat_id=chat_id,
        chars=len(text),
        **counts,
    )
    return DigestOutcome(
        sent=True, text=text, day=data.day, chat_id=chat_id, counts=counts
    )


async def run_daily_digest() -> dict[str, Any]:
    """Kunlik vazifa uchun o'ram — o'z sessiyasini ochadi.

    Hisobot `run_nightly` ga qaytadi va u yerdan logga tushadi.
    """
    async with SessionFactory() as session:
        outcome = await run_digest(session, manual=False)

    return {
        "sent": outcome.sent,
        "reason": outcome.reason,
        "day": outcome.day.isoformat() if outcome.day else None,
        "chars": len(outcome.text),
        **outcome.counts,
    }
