"""Kompaniyaning O'Z telefon liniyalari ro'yxati.

Bu ro'yxat bitta savolga javob beradi: «shu raqam bizniki mi?». Undan
qo'ng'iroq turi kelib chiqadi (`routing.resolve_type`): bizniki bo'lsa —
ichki suhbat, aks holda tashqi (savdo).

UCH MANBADAN yig'iladi va uchalasi ham KERAK:

  1. `calls.agent_number` — MoyZvonki har qo'ng'iroqda `src_number`
     beradi: xodim QAYSI o'z raqamimizdan gaplashgani. Bu eng ishonchli
     manba, chunki uni odam kiritmaydi — u ishlash jarayonining o'zidan
     kelib chiqadi va yangi xodim qo'shilganda ro'yxat O'ZI to'ladi.
  2. `agents.phone` — admin kartochkada ko'rsatgan raqam. Xodim hali
     qo'ng'iroq qilmagan bo'lsa ham ro'yxatga tushadi.
  3. `moizvonki.internal_numbers` sozlamasi — qo'lda qo'shiladigan
     raqamlar VA QOIDALAR. Bu manba eng muhimi bo'lib chiqdi: xodimlarning
     bir qismi MoyZvonki'da alohida foydalanuvchi emas (asosiy ombor,
     logistika, rejalashtirish, buxgalteriya, transport bo'limi), ya'ni
     ularning raqami hech qachon `src_number` bo'lib kelmaydi va
     o'z-o'zidan o'rganilmaydi. Bonvi ma'lumotida o'lchandi — bunday
     bo'limlar bilan 908 ta suhbat bor va ularning hammasi bitta raqam
     blokidan (`…700`). Shuning uchun sozlamada `*700` kabi SUFFIKS
     qoidasi ham yozish mumkin.

⚠️ NEGA KESHLANADI. Guruh yurishida minglab qo'ng'iroq ishlanadi va
ro'yxat har biri uchun qayta o'qilsa — minglab bir xil `SELECT`. Ro'yxat
esa soatlab o'zgarmaydi (yangi raqam faqat sinxronizatsiyadan keyin
paydo bo'ladi). Shuning uchun jarayon xotirasida qisqa muddatli kesh
turadi; sozlama o'zgarganda admin `reset()` orqali darhol yangilay
oladi.
"""

import re
from time import monotonic

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.routing import CompanyLines, phone_key
from src.modules.calls.infrastructure.models import CallModel

log = structlog.get_logger(__name__)

#: Sozlama kaliti — admin qo'lda qo'shadigan ichki raqamlar.
SETTING_KEY = "moizvonki.internal_numbers"

#: Kesh qancha yashaydi (soniya). Ro'yxat sinxronizatsiyadan keyin
#: o'zgaradi, ya'ni sutkasiga bir necha marta — 5 daqiqa yetarli va
#: guruh yurishida ro'yxat bir marta o'qiladi.
CACHE_TTL_SEC = 300

#: Raqamlar ajratiladigan belgilar: vergul, nuqta-vergul, yangi qator.
#
# ⚠️ BO'SH JOY AJRATGICH EMAS. Admin raqamni odam o'qiydigan shaklda
# yozadi — «+998 99 793-87-00» — va bo'sh joy bo'yicha bo'lish uni uch
# ma'nosiz bo'lakka aylantirardi. Bir qatorga bir nechta raqam
# yozilgan holat quyida alohida hal qilinadi.
_SEPARATORS = re.compile(r"[,;\n\r]+")

#: Bir bo'lakda bir nechta raqam bo'lsa — bo'sh joy bo'yicha bo'linadi.
_SPACES = re.compile(r"\s+")

#: Xalqaro raqamdagi eng ko'p raqam soni (E.164).
MAX_PHONE_DIGITS = 15

_ONLY_DIGITS = re.compile(r"[^0-9]")


def _digit_count(value: str) -> int:
    return len(_ONLY_DIGITS.sub("", value))

_cache: tuple[float, CompanyLines] | None = None


def reset() -> None:
    """Keshni bo'shatadi — sozlama o'zgarganda va testlarda."""
    global _cache
    _cache = None


#: Suffiks qoidasi shu belgi bilan boshlanadi: `*700`.
SUFFIX_PREFIX = "*"

#: Suffiks eng kamida shuncha raqamdan iborat bo'lishi kerak.
#
# ⚠️ Qisqa suffiks XAVFLI: `*0` deb yozilsa raqamlarning o'ndan biri
# «ichki» bo'lib qolardi va o'sha savdo suhbatlari jimgina
# baholanmasdi. Uch raqam — operator bergan blok belgisi uchun
# odatiy uzunlik (`…700`).
MIN_SUFFIX_DIGITS = 3


def parse_rules(raw: str | None) -> tuple[set[str], tuple[str, ...]]:
    """Sozlamadagi matnni (raqamlar, suffikslar) juftligiga aylantiradi.

    Admin qanday yozsa ham tushuniladi:

        +998 99 793-87-00, 998997928700
        997918700
        990178700 991108700
        *700

    Oxirgi qator — QOIDA: «…700 bilan tugaydigan har qanday raqam
    bizniki». Kompaniya operatordan ketma-ket raqamlar blokini olganda
    aynan shunday belgi paydo bo'ladi.

    Avval vergul/yangi qator bo'yicha bo'linadi (bo'lak ichidagi bo'sh
    joy — formatlash), keyin bo'lakdan kalit chiqmasa u bo'sh joy
    bo'yicha ham bo'linadi.

    Buzuq qiymat butun ro'yxatni yiqitmasligi kerak: kalitga aylanmagan
    bo'lak (masalan «sklad:») jimgina tashlab yuboriladi.
    """
    keys: set[str] = set()
    suffixes: set[str] = set()

    def qabul(bolak: str) -> bool:
        if bolak.startswith(SUFFIX_PREFIX):
            raqamlar = _ONLY_DIGITS.sub("", bolak)
            if len(raqamlar) >= MIN_SUFFIX_DIGITS:
                suffixes.add(raqamlar)
                return True
            return False
        key = phone_key(bolak)
        if key is not None:
            keys.add(key)
            return True
        return False

    for bolak in _SEPARATORS.split(raw or ""):
        bolak = bolak.strip()
        if not bolak:
            continue
        # ⚠️ Uzunlik tekshiruvi MAJBURIY. «990178700 991108700» degan
        # qator raqamlari qo'shilganda 18 ta raqam beradi va oxirgi 9
        # tasi baribir kalitga o'xshaydi — ya'ni birinchi raqam
        # JIMGINA yo'qolardi. Xalqaro raqamda ko'pi bilan 15 ta raqam
        # bo'ladi, undan uzuni — bu bitta raqam emas.
        if _digit_count(bolak) <= MAX_PHONE_DIGITS and qabul(bolak):
            continue
        # Bo'lakda bir nechta raqam bor — bo'sh joy bo'yicha bo'linadi
        for qism in _SPACES.split(bolak):
            qabul(qism)

    return keys, tuple(sorted(suffixes))


async def load_company_lines(
    session: AsyncSession, *, use_cache: bool = True
) -> CompanyLines:
    """Kompaniya liniyalari: aniq raqamlar + suffiks qoidalari."""
    global _cache

    if use_cache and _cache is not None:
        yozilgan, qiymat = _cache
        if monotonic() - yozilgan < CACHE_TTL_SEC:
            return qiymat

    keys: set[str] = set()

    # 1. Qo'ng'iroqlardan o'rganilgan raqamlar (asosiy manba)
    rows = (
        await session.execute(
            select(CallModel.agent_number)
            .where(CallModel.agent_number.is_not(None))
            .distinct()
        )
    ).scalars()
    for raqam in rows:
        key = phone_key(raqam)
        if key is not None:
            keys.add(key)

    # 2. Xodim kartochkasidagi raqam
    rows = (
        await session.execute(
            select(AgentModel.phone).where(AgentModel.phone.is_not(None)).distinct()
        )
    ).scalars()
    for raqam in rows:
        key = phone_key(raqam)
        if key is not None:
            keys.add(key)

    # 3. Admin qo'lda qo'shgan raqamlar va qoidalar
    qol_keys, suffixes = parse_rules(await _setting(session))
    keys |= qol_keys

    natija = CompanyLines(keys=frozenset(keys), suffixes=suffixes)
    _cache = (monotonic(), natija)
    log.info(
        "calls.internal_directory",
        numbers=len(natija.keys),
        suffixes=list(natija.suffixes),
    )
    return natija


async def _setting(session: AsyncSession) -> str | None:
    """Sozlamani o'qiydi. O'qib bo'lmasa — quvur TO'XTAMAYDI.

    Sozlama yo'qligi oddiy hol (ko'pchilikda u bo'sh), shuning uchun
    bu yerdagi nosozlik butun tasniflashni yiqitmasligi kerak: qolgan
    ikki manba baribir ishlaydi.
    """
    from src.modules.settings.application.services import SettingsService

    try:
        qiymat = await SettingsService(session).get_value(SETTING_KEY)
    except Exception:  # noqa: BLE001 — sozlama o'qilmasa ham davom etamiz
        return None
    return qiymat if isinstance(qiymat, str) else None
