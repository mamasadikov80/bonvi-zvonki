"""Qo'ng'iroq FAOLLIGI hisoboti — sifat emas, HAJM va javobgarlik.

Bu modul baholashdan butunlay mustaqil. Baholash «suhbat qanday
o'tdi?» degan savolga javob beradi, bu yerdagi hisobot esa boshqasiga:
kim kimga qancha qo'ng'iroq qildi, nechtasi javobsiz qoldi va javobsiz
qolganlarga QAYTIB aloqaga chiqildimi.

════════════════════════════════════════════════════════════════
 ATAMALAR — bu farqlar hisobotning butun ma'nosini belgilaydi
════════════════════════════════════════════════════════════════

«Javobsiz» degan yagona son YOZILMAYDI, chunki u ikki butunlay boshqa
narsani bir joyga qo'yardi:

  · KIRUVCHI + javobsiz = «propushenniy». Mijoz qo'ng'iroq qildi,
    kompaniya javob bermadi. Bu — KOMPANIYANING javobgarligi va
    hisobotning asosiy ko'rsatkichi.

  · CHIQUVCHI + javobsiz = mijoz ko'tarmadi. Bu xodimning aybi emas
    (odam band, telefoni o'chiq). Uni «propushenniy» ga qo'shish
    xodimni nohaq ayblardi.

O'lchandi (7 kun, haqiqiy ma'lumot): kiruvchi javobsiz 983, chiquvchi
javobsiz 1047. Ya'ni ularni qo'shib «2030 javobsiz» deb ko'rsatish
raqamni ikki barobar oshirib, ma'nosini yo'q qilardi.

«Qaytib aloqaga chiqish» — javobsiz KIRUVCHI qo'ng'iroqdan KEYIN o'sha
raqamga chiquvchi qo'ng'iroq qilinishi. O'lchandi: 3 kunda 404 javobsiz
kiruvchidan 307 tasiga (76%) qaytilgan, 97 tasiga (24%) UMUMAN
qaytilmagan; median 12 daqiqa.

════════════════════════════════════════════════════════════════
 NEGA `answered IS NOT NULL` SHARTI HAMMA JOYDA BOR
════════════════════════════════════════════════════════════════

`answered` ustuni keyin qo'shildi va eski qatorlarda `NULL`. Ularni
«javobsiz» deb sanash javobsizlar sonini OSHIRIB yuboradi — ya'ni xato
aynan eng yomon tomonga qarab bo'ladi: kompaniya javob bergan
qo'ng'iroqlar «o'tkazib yuborilgan» bo'lib chiqadi. Shuning uchun
noma'lum qatorlar HECH QAYERDA sanalmaydi va ularning soni javobda
alohida ko'rsatiladi (`unknown`), toki raqam nega kichik ekani
ko'rinib turishi kerak.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import Integer, and_, case, func, literal_column, or_, select, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection
from src.modules.calls.infrastructure.models import CallModel

#: Hisobot davrlari (kun). Shef so'ragan to'rt oyna.
PERIODS: tuple[int, ...] = (1, 7, 15, 30)

#: Qaytib aloqaga chiqish shu muddat ichida hisobga olinadi (soat).
#
# NEGA CHEGARA BOR. Chegarasiz har qanday keyingi qo'ng'iroq «javob
# qaytarish» deb hisoblanardi — hatto bir hafta o'tib, butunlay boshqa
# sabab bilan qilingani ham. O'shanda ko'rsatkich 100% ga yaqin bo'lib,
# hech narsani o'lchamaydigan holga kelardi.
#
# 24 soat tanlandi, chunki o'lchov shuni ko'rsatdi: qaytishlarning 71% i
# bir soat ichida, medianasi 12 daqiqa. Ya'ni 24 soat — haqiqiy ish
# amaliyotidan ancha keng, lekin «hech qachon» dan aniq farq qiladi.
CALLBACK_WINDOW_HOURS = 24

#: Telefon raqamini solishtirish uchun oxirgi necha raqam olinadi.
#
# Bir xil mijoz turli formatda kelishi mumkin: «+998 90 123-45-67»,
# «998901234567», «901234567». Oxirgi 9 raqam — O'zbekistonda operator
# kodi bilan birga abonent raqami, ya'ni ishonchli kalit.
PHONE_TAIL = 9

#: Soatlik razrez uchun mahalliy vaqt mintaqasi.
#
# ⚠️ UTC DA HISOBLASH XATO BO'LARDI. Baza vaqtni UTC da saqlaydi,
# rahbar esa mahalliy soatlarda o'ylaydi: «tushlikda javobsizlar ko'p»
# degan xulosa 12:00 da chiqadi, UTC da esa u 07:00 ga tushib, hech
# qanday ma'no bermasdi. O'zbekistonda yozgi vaqt o'zgarishi yo'q,
# ya'ni siljish doim +5.
LOCAL_TZ = "Asia/Tashkent"

#: Soatlik razrez BARCHA 24 soatni qamraydi.
#
# ⚠️ ILGARI 06:00–24:00 bilan cheklangan edi va bu YIG'INDINI BUZARDI:
# soatlik razrez 3135 beradi, kartadagi jami esa 3143 — sakkiz
# qo'ng'iroq «yo'qolgan» ko'rinardi. Prezentatsiyada bunday nomuvofiqlik
# eng yomon savolni tug'diradi: «raqamlaringiz to'g'ri kelmayapti».
#
# Kechasi kam hajmdagi soatning foizi shovqin bo'lishi ROST (ikkita
# qo'ng'iroqdan bittasi javobsiz bo'lsa 50%), lekin bu KO'RSATISH
# masalasi va u interfeysda hal qilinadi: `HourChart` da hajmi 20 dan
# kam soatda foiz chizig'i uzilади, ustun esa ko'rinaveradi. Ya'ni
# ma'lumot yashirilmaydi, faqat yolg'on foiz chizilmaydi.
WORK_HOURS = range(24)


def _phone_tail(column: str = "calls.client_phone"):
    """Ustundan solishtirish kalitini yasaydi (oxirgi 9 raqam).

    ⚠️ Aynan shu ifodaga indeks qo'yilgan (`ix_calls_phone_tail`).
    Bu yerda ifoda o'zgarsa indeks ishlamay qoladi va oyiga ~25 000
    qatorda har hisobot to'liq skanerlashga aylanadi.
    """
    # ⚠️ `literal_column` bilan yozilgan: `func.coalesce(column, "")` da
    # bo'sh satr BIND PARAMETR bo'lib chiqadi ($1) va ifoda ikki joyda
    # (SELECT va GROUP BY) ishlatilsa har birida boshqa raqamli parametr
    # paydo bo'ladi. PostgreSQL ularni BOSHQA ifoda deb qaraydi va
    # «client_phone must appear in the GROUP BY clause» xatosini beradi.
    # Indeks ham aynan shu matnli ifodaga qo'yilgan.
    return literal_column(
        f"right(regexp_replace(coalesce({column}, ''), '\\D', '', 'g'), {PHONE_TAIL})"
    )


@dataclass(slots=True)
class AgentActivity:
    """Bitta xodimning davr ichidagi faolligi."""

    agent_id: UUID
    agent_name: str
    region: str | None

    outbound_total: int = 0
    """Xodim mijozlarga qilgan qo'ng'iroqlar."""
    outbound_answered: int = 0
    outbound_no_answer: int = 0
    """Mijoz ko'tarmadi. ⚠️ Bu «propushenniy» EMAS."""

    inbound_total: int = 0
    """Mijozlar xodimga qilgan qo'ng'iroqlar."""
    inbound_answered: int = 0
    missed: int = 0
    """KIRUVCHI + javobsiz — «propushenniy». Kompaniya javobgarligi."""

    missed_called_back: int = 0
    """Javobsiz HODISALARdan nechtasidan keyin aloqa bo'lgan."""
    missed_addressable: int = 0
    """Raqami BOR javobsiz hodisalar. `missed_open` shundan hisoblanadi:
    raqamsiz javobsiz qo'ng'iroqqa qaytish imkonsiz va uni
    «qaytilmagan» ro'yxatiga qo'shish xodimni nohaq ayblardi."""

    # ── Mijoz darajasi ────────────────────────────────────────
    #
    # ⚠️ ASOSIY KO'RSATKICH SHU YERDA, hodisa darajasida emas.
    #
    # Nega. Mijoz bog'lanolmasa qayta-qayta uriniadi — o'lchandi,
    # o'rtacha 1.8 marta. Hodisalarni sanash bir odamning muammosini
    # bir necha marta hisoblab, raqamni sun'iy kattalashtiradi.
    #
    # Yomonroq holat ham bor: mijoz 4 marta qo'ng'iroq qilib
    # 4-chisida javob olgan bo'lsa, hodisa hisobi «3 javobsiz, 75%»
    # deb ko'rsatadi — holbuki mijoz BOG'LANGAN va kompaniya javob
    # bergan. Ya'ni hodisa darajasidagi foiz shu holatda butunlay
    # yolg'on.
    missed_clients: int = 0
    """Bog'lanolmagan MIJOZLAR soni (takroriy urinishlar bir marta)."""
    clients_reached: int = 0
    """Keyin bog'langanlar: qayta qo'ng'iroq qilib javob olgan YOKI
    o'ziga qaytib qo'ng'iroq qilingan."""

    unknown: int = 0
    """`answered` noma'lum bo'lgan qatorlar — hech qayerda sanalmaydi."""
    unknown_in: int = 0
    unknown_out: int = 0
    """Yo'nalish bo'yicha noma'lumlar. Ular bo'lmasa `outbound_total` va
    `answered + no_answer` orasidagi farqni ekranda tushuntirib
    bo'lmasdi — son o'z-o'ziga zid ko'rinardi."""

    talk_seconds: int = 0

    @property
    def total(self) -> int:
        return self.outbound_total + self.inbound_total

    @property
    def inbound_known(self) -> int:
        """Kiruvchilardan javob holati BILINGANLARI.

        `inbound_total` dan farq qiladi: eski qatorlarda `answered`
        `NULL` va ular bilinmaydi."""
        return self.inbound_answered + self.missed

    @property
    def missed_rate(self) -> float | None:
        """Kiruvchilarning qancha foizi javobsiz qolgan.

        ⚠️ BO'LINUVCHI — `inbound_known`, `inbound_total` EMAS.

        Bu farq o'lchandi va u OLTI BAROBAR: 30 kunlik ma'lumotda
        `inbound_total` bo'yicha 4.6%, bilingan qatorlar bo'yicha
        29.0%. Sababi — eski qatorlarda `answered` `NULL`, ya'ni ular
        javobsiz ham, javobli ham deb sanalmaydi, lekin jamiga kiradi.
        Ularni bo'linuvchida qoldirish foizni SUN'IY pasaytiradi.

        Nega bu eng xavfli xato turi: past raqam XUSHOMAD qiladi.
        Rahbar «javobsizlar 4.6% — yaxshi» degan xulosaga keladi va
        muammoni ko'rmaydi. Ya'ni xato aynan hech kim shubha
        qilmaydigan tomonga qarab bo'ladi."""
        if not self.inbound_known:
            return None
        return round(self.missed / self.inbound_known * 100, 1)

    @property
    def callback_rate(self) -> float | None:
        """Bog'lanolmagan mijozlarning qancha foiziga qaytilgan.

        ⚠️ MIJOZ darajasida hisoblanadi, hodisa darajasida emas.
        Sababi `missed_clients` izohida."""
        if not self.missed_clients:
            return None
        return round(self.clients_reached / self.missed_clients * 100, 1)

    @property
    def clients_unreached(self) -> int:
        """⚠️ HISOBOTNING ASOSIY RAQAMI.

        Bog'lanolmagan va keyin ham bog'lanmagan mijozlar. Bu — yo'qolgan
        savdo imkoniyati va u odamlar soni bilan o'lchanadi, qo'ng'iroq
        soni bilan emas. O'lchandi: 3 kunda 54 mijoz."""
        return self.missed_clients - self.clients_reached

    @property
    def missed_open(self) -> int:
        """Javobsiz HODISALARdan keyin aloqa bo'lmaganlari.

        ⚠️ Bo'linuvchi `missed` EMAS, `missed_addressable`. Raqamsiz
        javobsiz qo'ng'iroqqa qaytish imkonsiz (kimga qaytish
        bilinmaydi), shuning uchun u «qaytilmagan» ro'yxatiga
        tushmasligi kerak — o'lchandi, 7 kunda 971 javobsizdan 8 tasi
        shunday.

        Ikkilamchi son: asosiysi `clients_unreached`."""
        return max(0, self.missed_addressable - self.missed_called_back)


@dataclass(slots=True)
class ActivityDay:
    """Bir kunlik hajm — grafik uchun.

    Faqat HAJM: kiruvchi, chiquvchi, javobsiz. Mijoz darajasidagi hisob
    bu yerda YO'Q va ataylab: u kun chegarasida buziladi (mijoz kechqurun
    qo'ng'iroq qilib, ertalab javob olishi mumkin) va grafikdagi raqam
    kartadagi bilan mos kelmasdi.
    """

    day: date
    inbound: int = 0
    inbound_answered: int = 0
    missed: int = 0
    outbound: int = 0
    outbound_no_answer: int = 0


@dataclass(slots=True)
class ActivityHour:
    """Bir soatlik kesim — kun bo'ylab yuklama va javobsizlar.

    Bu razrez rahbarga ENG AMALIY narsani ko'rsatadi: qaysi soatda
    mijozlar bog'lanolmaydi. O'lchandi — tushlik payti (12:00)
    javobsizlar 35%, ertalab 07:00 da 74%, kechqurun 19:00 da 40%.
    Kunlik o'rtacha esa 29%, ya'ni o'rtacha son bu tafovutni butunlay
    yashirardi va «smenani qayta taqsimlash kerak» degan xulosaga olib
    kelmasdi."""

    hour: int
    inbound: int = 0
    inbound_answered: int = 0
    missed: int = 0
    outbound: int = 0
    outbound_no_answer: int = 0

    @property
    def missed_rate(self) -> float | None:
        """⚠️ Bo'linuvchi — javob holati BILINGAN kiruvchilar.

        `inbound` da noma'lum qatorlar ham bor va ularni bo'linuvchida
        qoldirish foizni sun'iy pasaytirardi — xato aynan xushomad
        qiladigan tomonga qarab bo'lardi."""
        bilingan = self.inbound_answered + self.missed
        if not bilingan:
            return None
        return round(self.missed / bilingan * 100, 1)


@dataclass(slots=True)
class ActivityReport:
    days: int
    date_from: datetime
    date_to: datetime
    agents: list[AgentActivity] = field(default_factory=list)

    #: Kompaniya bo'yicha jami — xodimlar yig'indisidan ALOHIDA
    #: hisoblanadi, chunki xodimga bog'lanmagan qo'ng'iroq bo'lishi
    #: mumkin emas (`agent_id` majburiy), lekin yig'indini qayta
    #: hisoblash o'rniga bir marta o'qish arzonroq.
    total: AgentActivity | None = None

    days_series: list[ActivityDay] = field(default_factory=list)
    """Kunlik dinamika — grafik uchun."""

    hours_series: list[ActivityHour] = field(default_factory=list)
    """Soatlik razrez — qaysi soatda javobsizlar ko'p."""

    callback_median_minutes: float | None = None
    """Javobsizga qaytib chiqishning medianasi. O'rtacha EMAS: bitta
    bir kunlik kechikish o'rtachani buzadi, median esa odatiy holatni
    ko'rsatadi."""


@dataclass(slots=True)
class MissedClient:
    """Bog'lanolmagan bitta mijoz — TEKSHIRISH uchun tafsilot.

    NEGA BU KERAK. Hisobotdagi «100%» yoki «3 mijoz bog'lanmagan» degan
    son ishonchsiz ko'rinishi mumkin: xodimda 15 javobsiz qo'ng'iroq
    bo'lib, qaytish darajasi 100% bo'lishi G'ALATI tuyuladi. Aslida bu
    to'g'ri — 15 hodisa 9 xil mijozdan kelgan va hammasi bilan
    gaplashilgan. Lekin buni ISBOTLAB ko'rsatmasa, raqamga ishonch
    bo'lmaydi. Ayniqsa rahbar oldida.

    Shu sabab har bir mijoz alohida ko'rsatiladi: necha marta urinib
    ko'rgan, oxirgi urinish qachon bo'lgan, keyin kim bilan va qancha
    vaqtdan so'ng gaplashgan.
    """

    phone: str
    client_name: str | None
    attempts: int
    """Necha marta javobsiz qo'ng'iroq qilgan."""
    first_missed_at: datetime
    last_missed_at: datetime
    contacted_at: datetime | None
    """Aloqa payti. `None` — HALI bog'lanilmagan."""
    contacted_by: str | None
    """Kim bilan aloqa bo'lgan. Boshqa xodim bo'lishi mumkin."""
    contact_inbound: bool | None
    """`True` — mijoz o'zi qayta qo'ng'iroq qilib javob olgan;
    `False` — xodim qaytib qo'ng'iroq qilgan."""

    @property
    def minutes_to_contact(self) -> float | None:
        if self.contacted_at is None:
            return None
        delta = self.contacted_at - self.last_missed_at
        return round(delta.total_seconds() / 60, 1)


class ActivityService:
    """Faollik ko'rsatkichlari. Faqat O'QISH."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def report(
        self,
        *,
        days: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        agent_ids: list[UUID] | None = None,
        regions: list[str] | None = None,
    ) -> ActivityReport:
        """Faollik hisoboti.

        Oyna ikki xil berilishi mumkin:
          · `days` — oxirgi N KUN, butun kunlarga tekislangan;
          · `since`/`until` — aniq oraliq, o'zgartirilmasdan.

        ⚠️ `days` OYNANI QAYTA QURISH UCHUN ISHLATILMAYDI. Ilgari
        chaqiruvchi aniq sanani berardi, u kun soniga aylantirilardi va
        oyna shu sondan QAYTA qurilardi. `timedelta.days` pastga
        yaxlitlaganligi uchun boshlanish sanasi 24 soatgacha oldinga
        siljirdi — o'lchandi: «10–16 avgust» so'rovida 853 qo'ng'iroq va
        137 javobsiz JIMGINA tushib qolgan edi. Endi berilgan sana
        o'zgartirilmaydi.

        ⚠️ `days` da oyna BUTUN KUNLARGA tekislanadi. Aylanuvchi
        «hozirdan 7×24 soat oldin» oynasi kunlik grafikni buzardi:
        birinchi ustun kunning faqat bir bo'lagini qamrab, 97% kam
        ko'rsatardi va grafikda soxta «pasayish» paydo bo'lardi.
        Frontenddagi tez tugmachalar ham butun kunlar bilan ishlaydi,
        ya'ni endi ikkalasi bir xil oynani beradi.
        """
        if since is None or until is None:
            kun = days or 7
            hozir = until or datetime.now(UTC)
            mahalliy = hozir.astimezone(ZoneInfo(LOCAL_TZ))
            kun_boshi = mahalliy.replace(hour=0, minute=0, second=0, microsecond=0)
            since = (kun_boshi - timedelta(days=kun - 1)).astimezone(UTC)
            until = hozir

        # Ko'rsatish uchun: oyna necha kunni qamrayadi.
        #
        # ⚠️ MAHALLIY sanada hisoblanadi. UTC da bu yorliq yolg'on
        # chiqardi: «oxirgi 1 kun» so'rovida mahalliy yarim tun UTC da
        # oldingi kunga tushadi va javobda «2 kun» deb yozilardi —
        # grafikda esa bitta ustun turardi, ya'ni javob o'z-o'ziga zid
        # bo'lardi.
        mahalliy_tz = ZoneInfo(LOCAL_TZ)
        kunlar = max(
            1,
            (
                until.astimezone(mahalliy_tz).date()
                - since.astimezone(mahalliy_tz).date()
            ).days
            + 1,
        )
        report = ActivityReport(days=kunlar, date_from=since, date_to=until)
        rows = await self._per_agent(since, until, agent_ids, regions)
        report.agents = rows

        callbacks = await self._callbacks(since, until, agent_ids, regions)
        for row in rows:
            row.missed_clients = callbacks.clients.get(row.agent_id, 0)
            row.clients_reached = callbacks.reached.get(row.agent_id, 0)
            row.missed_called_back = callbacks.events_closed.get(row.agent_id, 0)
            row.missed_addressable = callbacks.addressable.get(row.agent_id, 0)

        report.total = _sum_rows(rows)

        # ⚠️ MIJOZLAR SONI XODIMLAR YIG'INDISIDAN OLINMAYDI.
        #
        # Bitta mijoz ikki xil xodimga qo'ng'iroq qilishi mumkin. Xodim
        # kesimida bu TO'G'RI ikki qator (har birining javobgarligi
        # alohida), lekin kompaniya jamisida u BITTA odam. Yig'indi olish
        # asosiy raqamni shishtiradi — o'lchandi: 2 kunda 151 o'rniga
        # haqiqatda 145 mijoz, ya'ni 4% oshiq.
        #
        # Shef ko'radigan raqam aynan shu bo'lgani uchun jami alohida,
        # takrorlanmaydigan so'rov bilan hisoblanadi.
        company = await self._callbacks(
            since, until, agent_ids, regions, per_agent=False
        )
        report.total.missed_clients = sum(company.clients.values())
        report.total.clients_reached = sum(company.reached.values())

        # ⚠️ MEDIAN HAM KOMPANIYA kesimidan olinadi, xodim kesimidan emas.
        #
        # Xodim kesimida bitta mijoz bir necha xodimga qo'ng'iroq qilgan
        # bo'lsa bir necha marta sanaladi va medianani siljitadi. Kartada
        # esa yonma-yon ikki son turadi: qaytish darajasi (mijoz bo'yicha)
        # va median. Ular boshqa-boshqa birlikdan hisoblansa, son
        # o'z-o'ziga zid bo'lardi — o'lchandi: 15-avgust uchun xodim
        # kesimida 5,1 daqiqa, mijoz bo'yicha 4,1.
        report.callback_median_minutes = company.median_minutes
        report.days_series = await self._series(since, until, agent_ids, regions)
        report.hours_series = await self._hours(since, until, agent_ids, regions)
        return report

    # ── Soatlik razrez ────────────────────────────────────────

    async def _hours(
        self,
        since: datetime,
        until: datetime,
        agent_ids: list[UUID] | None,
        regions: list[str] | None,
    ) -> list[ActivityHour]:
        """Kun soatlari bo'yicha kiruvchi va javobsizlar.

        ⚠️ MAHALLIY vaqtda. UTC da hisoblash xulosani yo'q qilardi:
        «tushlikda javobsizlar ko'p» degan naqsh 12:00 da ko'rinadi,
        UTC da esa u 07:00 ga siljib, ma'nosini yo'qotadi.

        Faqat `answered` BILINGAN qatorlar olinadi — noma'lumlar foizni
        pasaytirib, eng muammoli soatni yashirardi.
        """
        soat = func.extract(
            "hour", func.timezone(LOCAL_TZ, CallModel.started_at)
        ).cast(Integer)
        inbound = CallModel.direction == CallDirection.INBOUND
        outbound = CallModel.direction == CallDirection.OUTBOUND

        # ⚠️ SHAKLI KUNLIK QATOR BILAN AYNAN BIR XIL. Ilgari bu so'rov
        # faqat kiruvchi va faqat `answered IS NOT NULL` qatorlarni
        # olardi — natijada soatlik yig'indi kunlik yig'indiga va
        # kartadagi songa TO'G'RI KELMASDI. Bitta grafik ikki xil
        # kesimni ko'rsatgani uchun ikkalasi bir xil ustunlarni berishi
        # SHART: aks holda foydalanuvchi kesimni almashtirganda sonlar
        # sakrab, tizimga ishonchi qolmaydi.
        stmt = (
            select(
                soat.label("hour"),
                func.count(case((inbound, 1))).label("inbound"),
                func.count(
                    case((and_(inbound, CallModel.answered.is_(True)), 1))
                ).label("inbound_answered"),
                func.count(
                    case((and_(inbound, CallModel.answered.is_(False)), 1))
                ).label("missed"),
                func.count(case((outbound, 1))).label("outbound"),
                func.count(
                    case((and_(outbound, CallModel.answered.is_(False)), 1))
                ).label("outbound_no_answer"),
            )
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .where(
                CallModel.started_at >= since,
                CallModel.started_at <= until,
                AgentModel.archived_at.is_(None),
            )
            .group_by(soat)
        )
        if agent_ids is not None:
            stmt = stmt.where(CallModel.agent_id.in_(agent_ids or [None]))
        if regions:
            stmt = stmt.where(AgentModel.region.in_(regions))

        topilgan = {
            int(row.hour): ActivityHour(
                hour=int(row.hour),
                inbound=int(row.inbound or 0),
                inbound_answered=int(row.inbound_answered or 0),
                missed=int(row.missed or 0),
                outbound=int(row.outbound or 0),
                outbound_no_answer=int(row.outbound_no_answer or 0),
            )
            for row in await self._session.execute(stmt)
        }
        # Bo'sh soatlar ham qaytadi — grafikda uzilish bo'lmasin
        return [topilgan.get(h) or ActivityHour(hour=h) for h in WORK_HOURS]

    # ── Bitta xodim bo'yicha tafsilot (tekshirish uchun) ──────

    async def missed_clients(
        self,
        *,
        agent_id: UUID,
        since: datetime,
        until: datetime,
    ) -> list[MissedClient]:
        """Xodimga bog'lanolmagan mijozlar ro'yxati.

        ⚠️ MANTIQ ASOSIY HISOBOT BILAN AYNAN BIR XIL bo'lishi shart:
        bir xil oyna, bir xil raqam kaliti, bir xil aloqa ta'rifi,
        bir xil sanoq nuqtasi (mijozning OXIRGI javobsiz urinishi).
        Aks holda tafsilot jamiga to'g'ri kelmaydi va tekshirish
        vositasi o'zi ishonchni buzardi — «jadvalda 9, ro'yxatda 8»
        degan holat eng yomon natija.

        Bog'lanmaganlar YUQORIDA turadi: ro'yxat ish uchun, ya'ni
        avval nima qilish kerakligi ko'rinishi kerak.
        """
        tail = _phone_tail()
        missed = (
            select(
                tail.label("tail"),
                func.min(CallModel.client_name).label("client_name"),
                func.count(CallModel.id).label("attempts"),
                func.min(CallModel.started_at).label("first_missed"),
                func.max(CallModel.started_at).label("last_missed"),
            )
            .where(
                CallModel.agent_id == agent_id,
                CallModel.direction == CallDirection.INBOUND,
                CallModel.answered.is_(False),
                CallModel.started_at >= since,
                CallModel.started_at <= until,
                func.length(tail) == PHONE_TAIL,
            )
            .group_by(tail)
            .subquery("m")
        )

        # Oxirgi javobsizdan keyingi eng yaqin aloqa — kim bilan va
        # qaysi yo'nalishda
        agent = aliased(AgentModel)
        contact = (
            select(
                CallModel.started_at.label("at"),
                agent.full_name.label("by_name"),
                CallModel.direction.label("dir"),
            )
            .join(agent, agent.id == CallModel.agent_id)
            .where(
                _phone_tail() == missed.c.tail,
                CallModel.started_at > missed.c.last_missed,
                CallModel.started_at
                <= missed.c.last_missed + timedelta(hours=CALLBACK_WINDOW_HOURS),
                or_(
                    CallModel.direction == CallDirection.OUTBOUND,
                    CallModel.answered.is_(True),
                ),
            )
            .order_by(CallModel.started_at)
            .limit(1)
            .lateral("c")
        )

        at = literal_column("c.at")
        stmt = (
            select(
                missed.c.tail,
                missed.c.client_name,
                missed.c.attempts,
                missed.c.first_missed,
                missed.c.last_missed,
                at.label("contacted_at"),
                literal_column("c.by_name").label("contacted_by"),
                literal_column("c.dir").label("contact_dir"),
            )
            .select_from(missed.outerjoin(contact, text("true")))
            # Bog'lanmaganlar YUQORIDA — ro'yxat ish uchun
            .order_by(at.is_not(None), missed.c.last_missed.desc())
        )

        return [
            MissedClient(
                phone=row.tail,
                client_name=row.client_name,
                attempts=int(row.attempts or 0),
                first_missed_at=row.first_missed,
                last_missed_at=row.last_missed,
                contacted_at=row.contacted_at,
                contacted_by=row.contacted_by,
                contact_inbound=(
                    None
                    if row.contact_dir is None
                    else str(row.contact_dir) == CallDirection.INBOUND.value
                ),
            )
            for row in await self._session.execute(stmt)
        ]

    # ── Kunlik dinamika ───────────────────────────────────────

    async def _series(
        self,
        since: datetime,
        until: datetime,
        agent_ids: list[UUID] | None,
        regions: list[str] | None,
    ) -> list[ActivityDay]:
        """Kun bo'yicha hajm. Bo'sh kunlar ham qaytadi.

        ⚠️ Bo'sh kunlarni tashlab ketish grafikni ALDAYDI: dam olish
        kunlari yo'qolib, chiziq uzluksiz ko'rinadi va «har kuni bir
        xil ishlayapti» degan taassurot beradi.
        """
        # ⚠️ MAHALLIY vaqtda. UTC da kunlar mahalliy 05:00 da kesiladi
        # va yarim tundan keyingi qo'ng'iroqlar OLDINGI kunga yozilardi —
        # grafik yorliqlari nominal ravishda noto'g'ri bo'lardi.
        bucket = func.date_trunc(
            "day", func.timezone(LOCAL_TZ, CallModel.started_at)
        )
        inbound = CallModel.direction == CallDirection.INBOUND
        stmt = (
            select(
                bucket.label("day"),
                func.count(case((inbound, 1))).label("inbound"),
                func.count(
                    case((and_(inbound, CallModel.answered.is_(True)), 1))
                ).label("inbound_answered"),
                func.count(
                    case((CallModel.direction == CallDirection.OUTBOUND, 1))
                ).label("outbound"),
                func.count(
                    case((and_(inbound, CallModel.answered.is_(False)), 1))
                ).label("missed"),
                func.count(
                    case(
                        (
                            and_(
                                CallModel.direction == CallDirection.OUTBOUND,
                                CallModel.answered.is_(False),
                            ),
                            1,
                        )
                    )
                ).label("outbound_no_answer"),
            )
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .where(
                CallModel.started_at >= since,
                CallModel.started_at <= until,
                AgentModel.archived_at.is_(None),
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        if agent_ids is not None:
            stmt = stmt.where(CallModel.agent_id.in_(agent_ids or [None]))
        if regions:
            stmt = stmt.where(AgentModel.region.in_(regions))

        topilgan = {
            (row.day.date() if hasattr(row.day, "date") else row.day): ActivityDay(
                day=(row.day.date() if hasattr(row.day, "date") else row.day),
                inbound=int(row.inbound or 0),
                inbound_answered=int(row.inbound_answered or 0),
                missed=int(row.missed or 0),
                outbound=int(row.outbound or 0),
                outbound_no_answer=int(row.outbound_no_answer or 0),
            )
            for row in await self._session.execute(stmt)
        }

        # Kun ro'yxati ham MAHALLIY sanada — aks holda ro'yxatdagi
        # kalitlar so'rov qaytargan kalitlarga mos kelmasdi va grafikda
        # bo'sh ustunlar paydo bo'lardi
        mahalliy = ZoneInfo(LOCAL_TZ)
        kunlar: list[ActivityDay] = []
        kursor = since.astimezone(mahalliy).date()
        oxiri = until.astimezone(mahalliy).date()
        while kursor <= oxiri:
            kunlar.append(topilgan.get(kursor) or ActivityDay(day=kursor))
            kursor += timedelta(days=1)

        # ⚠️ BO'SH KUNLAR OLIB TASHLANMAYDI — hech qaysi biri.
        #
        # Ilgari chekkadagi bo'sh kunlar qirqilardi: oyna UTC da
        # qurilganda mahalliy kunning bir necha soatini qamrab, bo'sh
        # ustun paydo bo'lardi. Endi oyna `days` bilan MAHALLIY yarim
        # tunga tekislanadi, ya'ni bunday artefakt umuman yo'q.
        #
        # Qirqish esa zarar qila boshlagan edi: ertalab «7 kun»
        # tanlansa va bugun hali qo'ng'iroq bo'lmasa, bugungi ustun
        # yo'qolib, grafik 6 ustun ko'rsatardi — davr esa 7 kun deb
        # yozilardi. Son bilan grafik bir-biriga zid bo'lardi.
        #
        # Bo'sh kun — HAQIQIY ma'lumot: dam olish kuni, ishlamagan kun
        # yoki hali boshlanmagan bugun. Uni ko'rsatish yashirishdan
        # yaxshiroq.
        return kunlar

    # ── Xodim kesimi ──────────────────────────────────────────

    async def _per_agent(
        self,
        since: datetime,
        until: datetime,
        agent_ids: list[UUID] | None,
        regions: list[str] | None,
    ) -> list[AgentActivity]:
        outbound = CallModel.direction == CallDirection.OUTBOUND
        inbound = CallModel.direction == CallDirection.INBOUND
        known = CallModel.answered.is_not(None)
        yes = CallModel.answered.is_(True)
        no = CallModel.answered.is_(False)

        def count(*conditions) -> object:
            return func.count(case((and_(*conditions), 1)))

        stmt = (
            select(
                AgentModel.id,
                AgentModel.full_name,
                AgentModel.region,
                count(outbound).label("outbound_total"),
                count(outbound, known, yes).label("outbound_answered"),
                count(outbound, known, no).label("outbound_no_answer"),
                count(inbound).label("inbound_total"),
                count(inbound, known, yes).label("inbound_answered"),
                count(inbound, known, no).label("missed"),
                # ⚠️ `CallModel.id.is_not(None)` SHARTI MAJBURIY.
                # Pastdagi birlashtirish LEFT OUTER: qo'ng'iroq qilmagan
                # xodim uchun bitta butunlay NULL qator chiqadi va unda
                # `answered IS NULL` ROST bo'ladi. Natijada har bir bo'sh
                # xodim «1 ta noma'lum qo'ng'iroq» beradi — o'lchandi,
                # bir kunlik hisobotda 10 ta soxta qator. Ekranda esa
                # «10 ta qo'ng'iroqda holat noma'lum» degan YOLG'ON
                # ogohlantirish chiqardi.
                count(
                    CallModel.id.is_not(None), CallModel.answered.is_(None)
                ).label("unknown"),
                # ── P2-7: yo'nalish bo'yicha noma'lumlar ──────────
                # Yagona `unknown` bilan chiquvchi qatori yig'ilmasdi:
                # `outbound_total` va `answered + no_answer` orasidagi
                # farqni ekranda tushuntiradigan son yo'q edi.
                count(outbound, CallModel.answered.is_(None)).label("unknown_out"),
                count(inbound, CallModel.answered.is_(None)).label("unknown_in"),
                func.coalesce(func.sum(CallModel.duration_sec), 0).label("talk"),
            )
            .select_from(AgentModel)
            # LEFT JOIN — davr ichida bitta ham qo'ng'iroq qilmagan xodim
            # ham ro'yxatda ko'rinishi kerak. Ichki birlashtirish uni
            # yashirardi va «hech ish qilmagan xodim» ko'rinmay qolardi —
            # aslida bu hisobotning eng muhim natijasi bo'lishi mumkin.
            .outerjoin(
                CallModel,
                and_(
                    CallModel.agent_id == AgentModel.id,
                    CallModel.started_at >= since,
                    CallModel.started_at <= until,
                ),
            )
            .where(AgentModel.archived_at.is_(None))
            .group_by(AgentModel.id, AgentModel.full_name, AgentModel.region)
            .order_by(func.count(CallModel.id).desc(), AgentModel.full_name)
        )
        if agent_ids is not None:
            stmt = stmt.where(AgentModel.id.in_(agent_ids or [None]))
        if regions:
            stmt = stmt.where(AgentModel.region.in_(regions))

        result = await self._session.execute(stmt)
        return [
            AgentActivity(
                agent_id=row.id,
                agent_name=row.full_name,
                region=row.region,
                outbound_total=int(row.outbound_total or 0),
                outbound_answered=int(row.outbound_answered or 0),
                outbound_no_answer=int(row.outbound_no_answer or 0),
                inbound_total=int(row.inbound_total or 0),
                inbound_answered=int(row.inbound_answered or 0),
                missed=int(row.missed or 0),
                unknown=int(row.unknown or 0),
                unknown_in=int(row.unknown_in or 0),
                unknown_out=int(row.unknown_out or 0),
                talk_seconds=int(row.talk or 0),
            )
            for row in result
        ]

    # ── Qaytib aloqaga chiqish ────────────────────────────────

    async def _callbacks(
        self,
        since: datetime,
        until: datetime,
        agent_ids: list[UUID] | None,
        regions: list[str] | None,
        per_agent: bool = True,
    ) -> "_CallbackStats":
        """Bog'lanolmagan MIJOZLARdan nechtasi keyin bog'langan.

        `per_agent=False` — mijozlar XODIMDAN MUSTAQIL guruhlanadi va
        natija bitta yig'ma qatorda qaytadi. Kompaniya jamisi uchun
        shu kerak: bitta mijoz ikki xodimga qo'ng'iroq qilsa, xodim
        kesimida ikki qator (javobgarlik alohida), kompaniya darajasida
        esa BITTA odam.

        ════════════════════════════════════════════════════════
         UCHTA QARORNI SHU YERDA O'QISH KERAK
        ════════════════════════════════════════════════════════

        1. HISOB MIJOZ BO'YICHA, hodisa bo'yicha emas.
           Mijoz bog'lanolmasa qayta-qayta uriniadi (o'lchandi: o'rtacha
           1.8 marta, 384 hodisa = 216 mijoz). Hodisalarni sanash bir
           odamning muammosini bir necha marta hisoblardi.

        2. SANOQ NUQTASI — mijozning OXIRGI javobsiz urinishi.
           Birinchisidan hisoblash xato bo'lardi: mijoz 09:00 va 18:00
           da qo'ng'iroq qilib, 09:20 da javob qaytarilgan bo'lsa,
           birinchisiga qarab «bog'landi» deb yozilardi — holbuki
           18:00 dagi urinish javobsiz qolgan. Oxirgisidan hisoblash
           ikkala holatni ham to'g'ri ajratadi.

        3. ALOQA — ikki xil bo'ladi va IKKALASI ham hisobga olinadi:
             · mijozga qaytib qo'ng'iroq qilingan (chiquvchi);
             · mijoz yana qo'ng'iroq qilib, bu safar JAVOB OLGAN.
           Ikkinchisini hisobga olmaslik eng ko'p uchraydigan haqiqiy
           holatni («mijoz qayta urindi va gaplashdi») «bog'lanmagan»
           deb ko'rsatardi.

           Aloqa kim tomonidan bo'lganini TEKSHIRMAYMIZ: hamkasb
           qaytargan bo'lsa ham mijoz xizmat oldi (o'lchandi: 9% shunday).
           Javobsizlik esa telefoni jiringlagan xodimga yoziladi —
           javobgarlik o'shanda.
        """
        missed = (
            select(
                (
                    CallModel.agent_id
                    if per_agent
                    # Yig'ma rejimda xodim ustuni kerak emas, lekin
                    # keyingi kod bir xil shaklni kutadi — bo'sh UUID
                    else literal_column("'00000000-0000-0000-0000-000000000000'::uuid")
                ).label("agent_id"),
                _phone_tail().label("tail"),
                func.max(CallModel.started_at).label("last_missed"),
                func.count(CallModel.id).label("attempts"),
            )
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .where(
                CallModel.direction == CallDirection.INBOUND,
                CallModel.answered.is_(False),
                CallModel.started_at >= since,
                CallModel.started_at <= until,
                AgentModel.archived_at.is_(None),
                # Raqamsiz javobsiz qo'ng'iroqda kimga qaytish
                # kerakligi BILINMAYDI. Uni «bog'lanmagan» deb sanash
                # xodimni nohaq ayblardi, shuning uchun hisobga
                # olinmaydi (hajm sonida esa ko'rinadi).
                func.length(_phone_tail()) == PHONE_TAIL,
            )
            .group_by(
                *(
                    [CallModel.agent_id, _phone_tail()]
                    if per_agent
                    # Xodim guruhlashdan chiqariladi: bitta raqam bitta
                    # mijoz, qaysi xodimga qo'ng'iroq qilganidan qat'i nazar
                    else [_phone_tail()]
                )
            )
        )
        if agent_ids is not None:
            missed = missed.where(CallModel.agent_id.in_(agent_ids or [None]))
        if regions:
            missed = missed.where(AgentModel.region.in_(regions))

        m = missed.subquery("m")

        # Oxirgi javobsizdan KEYINGI eng yaqin aloqa
        contact = (
            select(CallModel.started_at.label("at"))
            .where(
                _phone_tail() == m.c.tail,
                CallModel.started_at > m.c.last_missed,
                CallModel.started_at
                <= m.c.last_missed + timedelta(hours=CALLBACK_WINDOW_HOURS),
                or_(
                    CallModel.direction == CallDirection.OUTBOUND,
                    CallModel.answered.is_(True),
                ),
            )
            .order_by(CallModel.started_at)
            .limit(1)
            .lateral("c")
        )

        at = literal_column("c.at")
        stmt = (
            select(
                m.c.agent_id,
                func.count().label("clients"),
                func.count(at).label("reached"),
                # Raqami BOR javobsiz hodisalar soni. `missed_open` shu
                # sondan hisoblanadi: raqamsiz javobsiz qo'ng'iroqqa
                # qaytish IMKONSIZ va uni «qaytilmagan» ro'yxatiga
                # qo'shish xodimni nohaq ayblardi.
                func.coalesce(func.sum(m.c.attempts), 0).label("addressable"),
                # Aloqa bo'lgan MIJOZLARning javobsiz hodisalari ham
                # yopilgan hisoblanadi — mijoz 4 marta urinib bitta
                # javob olgan bo'lsa, 4 tasi ham hal bo'lgan
                func.coalesce(
                    func.sum(case((at.is_not(None), m.c.attempts), else_=0)), 0
                ).label("events_closed"),
            )
            .select_from(m.outerjoin(contact, text("true")))
            .group_by(m.c.agent_id)
        )

        rows = (await self._session.execute(stmt)).all()

        # ⚠️ MEDIAN ALOHIDA, GURUHLASHSIZ so'rov bilan olinadi.
        #
        # Ilgari u yuqoridagi `GROUP BY agent_id` ichida turardi, ya'ni
        # har xodim uchun bitta median chiqib, keyin Python ULARNING
        # medianasini olardi. «Medianalarning medianasi» hajmni
        # HISOBGA OLMAYDI: 300 marta 3 daqiqada qaytargan xodim va bir
        # marta 120 daqiqada qaytargan uch xodim bo'lsa, natija ~120
        # daqiqa bo'lib chiqardi — holbuki haqiqiy median 3 ga yaqin.
        # O'lchandi: 4.2 daqiqa ko'rsatilgan, haqiqiysi 4.75.
        median_stmt = select(
            func.percentile_cont(0.5)
            .within_group(func.extract("epoch", at - m.c.last_missed) / 60)
            .label("median_minutes")
        ).select_from(m.outerjoin(contact, text("true")))
        median = (await self._session.execute(median_stmt)).scalar_one_or_none()

        return _CallbackStats(
            clients={row.agent_id: int(row.clients or 0) for row in rows},
            reached={row.agent_id: int(row.reached or 0) for row in rows},
            events_closed={
                row.agent_id: int(row.events_closed or 0) for row in rows
            },
            median_minutes=round(float(median), 1) if median is not None else None,
            addressable={
                row.agent_id: int(row.addressable or 0) for row in rows
            },
        )


@dataclass(slots=True)
class _CallbackStats:
    clients: dict[UUID, int]
    """Bog'lanolmagan mijozlar soni."""
    reached: dict[UUID, int]
    """Ulardan keyin bog'langanlari."""
    events_closed: dict[UUID, int]
    """Yopilgan javobsiz HODISALAR soni."""
    addressable: dict[UUID, int]
    """Raqami bor javobsiz hodisalar — `missed_open` shundan hisoblanadi."""
    median_minutes: float | None


def _sum_rows(rows: list[AgentActivity]) -> AgentActivity:
    """Kompaniya jamisi. Xodim maydonlari bo'sh — bu qator xodim emas."""
    total = AgentActivity(
        agent_id=UUID(int=0), agent_name="", region=None
    )
    for row in rows:
        total.outbound_total += row.outbound_total
        total.outbound_answered += row.outbound_answered
        total.outbound_no_answer += row.outbound_no_answer
        total.inbound_total += row.inbound_total
        total.inbound_answered += row.inbound_answered
        total.missed += row.missed
        total.missed_called_back += row.missed_called_back
        total.missed_addressable += row.missed_addressable
        total.missed_clients += row.missed_clients
        total.clients_reached += row.clients_reached
        total.unknown += row.unknown
        total.unknown_in += row.unknown_in
        total.unknown_out += row.unknown_out
        total.talk_seconds += row.talk_seconds
    return total
