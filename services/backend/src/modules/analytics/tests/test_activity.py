"""Faollik hisoboti — TA'RIFLAR qulflanadi.

Bu hisobot rahbarga ko'rsatiladi va xodimlar ish sifati bo'yicha
baholanadi. Shuning uchun bu yerdagi har bir test bitta savolga javob
beradi: «raqam ADOLATLIMI?».

Eng katta xato manbai — «javobsiz» so'zining ikki xil ma'nosi:

  · kiruvchi javobsiz  = kompaniya javob bermadi («propushenniy»);
  · chiquvchi javobsiz = mijoz ko'tarmadi.

Ikkinchisini birinchisiga qo'shish xodimni NOHAQ ayblardi va o'lchov
ko'rsatdi: bu raqamni deyarli ikki barobar oshirardi (7 kunda 983 va
1047). Shu farq shu fayldagi bir necha test bilan qulflangan.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.analytics.application.activity import (
    CALLBACK_WINDOW_HOURS,
    ActivityService,
)
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel

#: Testlar o'z oynasida ishlaydi — mavjud ma'lumotga tegmasin
BAZA = datetime(2021, 3, 10, 9, 0, tzinfo=UTC)
RAQAM = "+998 90 111-22-33"


@pytest_asyncio.fixture
async def xodim():
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"faollik-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(agent)
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()


async def _qongiroq(
    agent_id,
    *,
    inbound: bool,
    answered: bool | None,
    offset_min: float = 0,
    phone: str | None = RAQAM,
) -> None:
    async with SessionFactory() as session:
        session.add(
            CallModel(
                external_id=f"faollik-{uuid.uuid4().hex}",
                agent_id=agent_id,
                direction=CallDirection.INBOUND if inbound else CallDirection.OUTBOUND,
                status=CallStatus.SKIPPED,
                started_at=BAZA + timedelta(minutes=offset_min),
                duration_sec=0 if answered is False else 60,
                client_phone=phone,
                answered=answered,
            )
        )
        await session.commit()


async def _hisobot(agent_id):
    """Test oynasini qamrab oladigan hisobot.

    ⚠️ ANIQ oraliq beriladi, `days` EMAS. `days` oynani «hozirdan
    orqaga» deb quradi va u testdagi 2021-yildagi sun'iy sanalarni
    qamramaydi. Aniq oraliq esa o'zgartirilmasdan uzatiladi — bu
    xatti-harakat P0 tuzatishining bir qismi."""
    async with SessionFactory() as session:
        report = await ActivityService(session).report(
            since=BAZA - timedelta(hours=1),
            until=BAZA + timedelta(days=2),
            agent_ids=[agent_id],
        )
    assert len(report.agents) == 1
    return report, report.agents[0]


# ══════════════════════════════════════════════════════════════
#  «Javobsiz» ning ikki ma'nosi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_kiruvchi_javobsiz_propushenniy_deb_sanaladi(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=False)
    _, row = await _hisobot(xodim)

    assert row.missed == 1
    assert row.inbound_total == 1
    assert row.outbound_no_answer == 0


@pytest.mark.asyncio
async def test_chiquvchi_javobsiz_propushenniy_EMAS(xodim) -> None:
    """⚠️ ASOSIY ADOLAT SHARTI.

    Xodim mijozga qo'ng'iroq qildi, mijoz ko'tarmadi. Bu xodimning aybi
    emas (odam band, telefoni o'chiq). Uni «propushenniy» ga qo'shish
    xodimni nohaq ayblardi — o'lchandi, bu raqamni deyarli ikki barobar
    oshirardi."""
    await _qongiroq(xodim, inbound=False, answered=False)
    _, row = await _hisobot(xodim)

    assert row.missed == 0, "chiquvchi javobsiz — propushenniy emas"
    assert row.outbound_no_answer == 1
    assert row.outbound_total == 1


@pytest.mark.asyncio
async def test_javob_berilgan_qongiroq_javobsizga_qoshilmaydi(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=True)
    _, row = await _hisobot(xodim)

    assert row.missed == 0
    assert row.inbound_answered == 1


@pytest.mark.asyncio
async def test_nomalum_qator_HECH_QAYERDA_sanalmaydi(xodim) -> None:
    """⚠️ `answered IS NULL` — ustun paydo bo'lishidan oldingi qatorlar.

    Ularni «javobsiz» deb sanash raqamni OSHIRIB yuboradi, ya'ni xato
    aynan eng yomon tomonga: kompaniya javob bergan qo'ng'iroqlar
    «o'tkazib yuborilgan» bo'lib chiqadi. Noto'g'ri raqamdan ko'ra
    kamroq raqam yaxshiroq — shuning uchun alohida ko'rsatiladi."""
    await _qongiroq(xodim, inbound=True, answered=None)
    _, row = await _hisobot(xodim)

    assert row.missed == 0
    assert row.inbound_answered == 0
    assert row.inbound_total == 1, "jami hajmda ko'rinadi"
    assert row.unknown == 1, "soni alohida aytiladi"


# ══════════════════════════════════════════════════════════════
#  Qaytib aloqaga chiqish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qaytib_chiqish_aniqlanadi(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=12)
    _, row = await _hisobot(xodim)

    assert row.missed == 1
    assert row.missed_called_back == 1
    assert row.missed_open == 0
    assert row.callback_rate == 100.0


@pytest.mark.asyncio
async def test_qaytilmagan_javobsiz_ochiq_qoladi(xodim) -> None:
    """Bu son — rahbarning ish ro'yxati. O'lchandi: 3 kunda 99 ta."""
    await _qongiroq(xodim, inbound=True, answered=False)
    _, row = await _hisobot(xodim)

    assert row.missed_called_back == 0
    assert row.missed_open == 1
    assert row.callback_rate == 0.0


@pytest.mark.asyncio
async def test_oynadan_kechikkan_qongiroq_qaytish_deb_sanalmaydi(xodim) -> None:
    """⚠️ Chegarasiz har qanday keyingi qo'ng'iroq «qaytish» bo'lardi —
    hatto bir hafta o'tib, butunlay boshqa sabab bilan qilingani ham.
    O'shanda ko'rsatkich 100% ga yaqin bo'lib, hech narsani
    o'lchamaydigan holga kelardi."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(
        xodim,
        inbound=False,
        answered=True,
        offset_min=CALLBACK_WINDOW_HOURS * 60 + 1,
    )
    _, row = await _hisobot(xodim)

    assert row.missed_called_back == 0


@pytest.mark.asyncio
async def test_javobsizdan_OLDINGI_qongiroq_sanalmaydi(xodim) -> None:
    """Qaytish — javobsizdan KEYIN bo'lishi shart. Aks holda oldindan
    qilingan oddiy qo'ng'iroq ham «javob qaytarish» bo'lib chiqardi."""
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=30)
    _, row = await _hisobot(xodim)

    assert row.missed == 1
    assert row.missed_called_back == 0


@pytest.mark.asyncio
async def test_ikki_marta_qaytilsa_BIR_marta_sanaladi(xodim) -> None:
    """⚠️ Qaytilganlar soni javobsizlar sonidan OSHIB KETMASLIGI kerak.

    Oddiy `JOIN` bilan har javobsizga bir necha mos qator tushib,
    `COUNT` haqiqiydan katta chiqardi — natijada «110% qaytilgan» kabi
    ma'nosiz raqam ko'rinardi."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=5)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=20)
    await _qongiroq(xodim, inbound=False, answered=False, offset_min=40)
    _, row = await _hisobot(xodim)

    assert row.missed == 1
    assert row.missed_called_back == 1, "bir javobsiz — bir qaytish"
    assert row.callback_rate == 100.0


@pytest.mark.asyncio
async def test_boshqa_raqamga_qongiroq_qaytish_emas(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(
        xodim, inbound=False, answered=True, offset_min=10, phone="+998 91 999-88-77"
    )
    _, row = await _hisobot(xodim)

    assert row.missed_called_back == 0


@pytest.mark.asyncio
async def test_raqam_formati_farq_qilsa_ham_topiladi(xodim) -> None:
    """Bir xil mijoz turli formatda keladi: «+998 90 111-22-33»,
    «998901112233», «901112233». Formatga qarab solishtirish qaytish
    ko'rsatkichini soxta ravishda pasaytirardi."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0, phone=RAQAM)
    await _qongiroq(
        xodim, inbound=False, answered=True, offset_min=10, phone="998901112233"
    )
    _, row = await _hisobot(xodim)

    assert row.missed_called_back == 1


@pytest.mark.asyncio
async def test_raqamsiz_javobsiz_qaytish_hisobiga_kirmaydi(xodim) -> None:
    """Raqam yo'q bo'lsa nimaga qaytish kerakligi BILINMAYDI. Uni
    «qaytilmagan» deb sanash xodimni nohaq ayblardi."""
    await _qongiroq(xodim, inbound=True, answered=False, phone=None)
    _, row = await _hisobot(xodim)

    # Hajmda ko'rinadi
    assert row.missed == 1
    # ...lekin qaytish darajasi hisobiga kirmaydi
    assert row.missed_called_back == 0


# ══════════════════════════════════════════════════════════════
#  Hisob-kitob izchilligi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jami_qismlarga_teng(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=1)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=2)
    await _qongiroq(xodim, inbound=False, answered=False, offset_min=3)
    _, row = await _hisobot(xodim)

    assert row.inbound_total == row.inbound_answered + row.missed
    assert row.outbound_total == row.outbound_answered + row.outbound_no_answer
    assert row.total == 4


@pytest.mark.asyncio
async def test_qongirogi_yoq_xodim_royxatda_qoladi(xodim) -> None:
    """⚠️ Ichki birlashtirish uni yashirardi — aslida «hech ish
    qilmagan xodim» hisobotning eng muhim natijasi bo'lishi mumkin."""
    _, row = await _hisobot(xodim)

    assert row.total == 0
    assert row.missed_rate is None, "bo'linuvchi nol — foiz ko'rsatilmaydi"
    assert row.callback_rate is None


@pytest.mark.asyncio
async def test_foiz_faqat_BILINGAN_qatorlardan_hisoblanadi(xodim) -> None:
    """⚠️ ENG XAVFLI XATO TURI — past raqam XUSHOMAD qiladi.

    O'lchandi: 30 kunlik haqiqiy ma'lumotda `inbound_total` bo'yicha
    javobsizlar 4.6%, bilingan qatorlar bo'yicha 29.0% — olti barobar
    farq. Sababi: eski qatorlarda `answered` `NULL` va ular javobsiz
    ham, javobli ham deb sanalmaydi, lekin jamiga kiradi.

    Agar bo'linuvchi `inbound_total` bo'lsa, rahbar «javobsizlar 4.6% —
    yaxshi» degan xulosaga keladi va muammoni ko'rmaydi. Ya'ni xato
    aynan hech kim shubha qilmaydigan tomonga qarab bo'ladi."""
    # 1 javobsiz + 1 javobli + 8 noma'lum
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=1)
    for i in range(8):
        await _qongiroq(xodim, inbound=True, answered=None, offset_min=2 + i)

    _, row = await _hisobot(xodim)

    assert row.inbound_total == 10, "hajm — hammasi"
    assert row.inbound_known == 2, "bilinganlar — ikkitasi"
    assert row.unknown == 8
    # 1/2 = 50%, 1/10 = 10% BO'LMAYDI
    assert row.missed_rate == 50.0, "noma'lumlar foizni pasaytirmasligi kerak"


# ══════════════════════════════════════════════════════════════
#  MIJOZ darajasi — takroriy urinishlar bir marta sanaladi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tort_urinish_bitta_mijoz_deb_sanaladi(xodim) -> None:
    """⚠️ Mijoz bog'lanolmasa QAYTA-QAYTA uriniadi.

    O'lchandi: o'rtacha 1.8 marta (384 hodisa = 216 mijoz). Hodisalarni
    sanash bir odamning muammosini bir necha marta hisoblab, raqamni
    sun'iy kattalashtiradi — «384 muammo» aslida 216 odam."""
    for i in range(4):
        await _qongiroq(xodim, inbound=True, answered=False, offset_min=i * 2)
    _, row = await _hisobot(xodim)

    assert row.missed == 4, "hodisa hajmi — to'rtta"
    assert row.missed_clients == 1, "muammo — bitta odamda"
    assert row.clients_unreached == 1


@pytest.mark.asyncio
async def test_tort_urinishdan_keyin_javob_berilsa_MUAMMO_YOQ(xodim) -> None:
    """⚠️ ENG MUHIM HOLAT — hodisa hisobi bu yerda YOLG'ON gapiradi.

    Mijoz 4 marta qo'ng'iroq qildi, 4-chisida javob berildi. Mijoz
    BOG'LANDI, kompaniya xizmat ko'rsatdi.

    Hodisa darajasida bu «3 javobsiz, 75% javobsiz» bo'lib chiqadi va
    xodim yomon ishlagandek ko'rinadi. Mijoz darajasida esa haqiqat
    ko'rinadi: bitta mijoz, bog'langan, muammo yo'q."""
    for i in range(3):
        await _qongiroq(xodim, inbound=True, answered=False, offset_min=i * 2)
    # To'rtinchi urinish — JAVOB BERILDI
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=10)

    _, row = await _hisobot(xodim)

    assert row.missed == 3, "hodisa sifatida uchtasi javobsiz qolgan — bu fakt"
    assert row.missed_clients == 1
    assert row.clients_reached == 1, "mijoz bog'landi — muammo hal bo'lgan"
    assert row.clients_unreached == 0
    assert row.callback_rate == 100.0


@pytest.mark.asyncio
async def test_bitta_chiquvchi_hamma_urinishni_yopadi(xodim) -> None:
    """Mijoz 4 marta urindi, xodim bir marta qaytardi — hal bo'ldi.

    Har urinish uchun alohida qaytarish TALAB QILINMAYDI: mijozga bir
    marta qo'ng'iroq qilib gaplashish yetarli."""
    for i in range(4):
        await _qongiroq(xodim, inbound=True, answered=False, offset_min=i * 2)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=20)

    _, row = await _hisobot(xodim)

    assert row.missed_clients == 1
    assert row.clients_reached == 1
    assert row.missed_called_back == 4, "to'rtala hodisa ham yopilgan hisoblanadi"
    assert row.missed_open == 0


@pytest.mark.asyncio
async def test_sanoq_nuqtasi_OXIRGI_urinish(xodim) -> None:
    """⚠️ Birinchi urinishdan hisoblash XATO bo'lardi.

    Mijoz ertalab qo'ng'iroq qildi, 20 daqiqada javob qaytarildi.
    Kechqurun YANA qo'ng'iroq qildi — javobsiz. Birinchisiga qarab
    «bog'landi» deb yozish kechqurundagi muammoni yashirardi."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=20)
    # Kechqurun yana urindi — javobsiz, va endi hech kim qaytarmadi
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=9 * 60)

    _, row = await _hisobot(xodim)

    assert row.missed_clients == 1
    assert row.clients_reached == 0, "oxirgi urinishdan keyin aloqa bo'lmagan"
    assert row.clients_unreached == 1


@pytest.mark.asyncio
async def test_ikki_xil_mijoz_alohida_sanaladi(xodim) -> None:
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(
        xodim, inbound=True, answered=False, offset_min=1, phone="+998 91 555-44-33"
    )
    # Faqat birinchisiga qaytarildi
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=10)

    _, row = await _hisobot(xodim)

    assert row.missed_clients == 2
    assert row.clients_reached == 1
    assert row.clients_unreached == 1
    assert row.callback_rate == 50.0


# ══════════════════════════════════════════════════════════════
#  Oyna chegaralari va grafik — TOPILGAN XATOLARNI qulflaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aniq_oraliq_birinchi_kunni_TUSHIRMAYDI(xodim) -> None:
    """⚠️ P0: eng qimmat xato — jimgina ma'lumot yo'qotish.

    Ilgari chaqiruvchi aniq sana berardi, u KUN SONIGA aylantirilardi va
    oyna shu sondan qayta qurilardi. `timedelta.days` pastga
    yaxlitlaganligi uchun boshlanish 24 soatgacha oldinga siljirdi.
    O'lchandi: «10–16 avgust» so'rovida 853 qo'ng'iroq va 137 javobsiz
    tushib qolgan, javobda esa HECH QANDAY belgi yo'q edi."""
    # Oynaning ENG BOSHIDA turgan qo'ng'iroq
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)

    async with SessionFactory() as session:
        report = await ActivityService(session).report(
            since=BAZA,  # aynan qo'ng'iroq payti
            until=BAZA + timedelta(days=1),
            agent_ids=[xodim],
        )
    assert report.agents[0].missed == 1, "chegaradagi qo'ng'iroq yo'qolmasligi kerak"
    assert report.date_from == BAZA, "berilgan sana O'ZGARTIRILMASLIGI kerak"


@pytest.mark.asyncio
async def test_oynadan_TASHQARIDAGI_qongiroq_sanalmaydi(xodim) -> None:
    """Chegara ikki tomonga ham ishlashi kerak."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=-24 * 60)
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=5 * 24 * 60)

    _, row = await _hisobot(xodim)
    assert row.missed == 0, "oynadan tashqaridagilar kirmasligi kerak"


@pytest.mark.asyncio
async def test_qongirogi_yoq_xodim_SOXTA_nomalum_bermaydi(xodim) -> None:
    """⚠️ P0: LEFT JOIN tuzog'i.

    Qo'ng'iroq qilmagan xodim uchun birlashtirish butunlay NULL qator
    beradi va unda `answered IS NULL` ROST bo'ladi. Natijada har bir
    bo'sh xodim «1 ta noma'lum qo'ng'iroq» berardi — o'lchandi, bir
    kunlik hisobotda 10 ta soxta qator. Ekranda esa «10 ta qo'ng'iroqda
    holat noma'lum» degan YOLG'ON ogohlantirish chiqardi."""
    _, row = await _hisobot(xodim)

    assert row.total == 0
    assert row.unknown == 0, "mavjud bo'lmagan qo'ng'iroq sanalmasligi kerak"
    assert row.unknown_in == 0
    assert row.unknown_out == 0


@pytest.mark.asyncio
async def test_chiquvchi_qatori_YIGILADI(xodim) -> None:
    """Ekranda ko'ringan sonlar o'z-o'ziga zid bo'lmasligi kerak."""
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=False, offset_min=1)
    await _qongiroq(xodim, inbound=False, answered=None, offset_min=2)

    _, row = await _hisobot(xodim)
    assert (
        row.outbound_total
        == row.outbound_answered + row.outbound_no_answer + row.unknown_out
    )


@pytest.mark.asyncio
async def test_raqamsiz_javobsiz_OCHIQ_royxatga_tushmaydi(xodim) -> None:
    """⚠️ Raqamsiz javobsiz qo'ng'iroqqa qaytish IMKONSIZ — kimga
    qaytish bilinmaydi. Uni «qaytilmagan» ro'yxatiga qo'shish xodimni
    nohaq ayblardi. O'lchandi: 7 kunda 971 javobsizdan 8 tasi shunday."""
    await _qongiroq(xodim, inbound=True, answered=False, phone=None)

    _, row = await _hisobot(xodim)
    assert row.missed == 1, "hajmda ko'rinadi"
    assert row.missed_addressable == 0, "raqami yo'q — murojaat qilib bo'lmaydi"
    assert row.missed_open == 0, "ish ro'yxatiga tushmasligi kerak"


@pytest.mark.asyncio
async def test_grafik_yigindisi_JAMIGA_teng(xodim) -> None:
    """⚠️ Grafik jamiga to'g'ri kelmasa prezentatsiyada eng yomon savol
    tug'iladi: «raqamlaringiz mos kelmayapti»."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=60)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=120)
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=25 * 60)

    report, row = await _hisobot(xodim)

    assert sum(d.inbound for d in report.days_series) == row.inbound_total
    assert sum(d.outbound for d in report.days_series) == row.outbound_total
    assert sum(d.missed for d in report.days_series) == row.missed
    # Soatlik razrez BARCHA 24 soatni qamraydi — aks holda yig'indi
    # kam chiqib, kartadagi son bilan mos kelmasdi
    assert len(report.hours_series) == 24
    assert sum(h.missed for h in report.hours_series) == row.missed


@pytest.mark.asyncio
async def test_grafikda_bosh_kun_QOLADI(xodim) -> None:
    """Bo'sh kun — HAQIQIY ma'lumot: dam olish kuni yoki hali
    boshlanmagan bugun. Uni yashirish grafikni uzluksiz qilib, «har
    kuni bir xil ishlayapti» degan yolg'on taassurot berardi; ustunlar
    soni ham davrga to'g'ri kelmay qolardi."""
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=0)
    # Bir kun tashlab
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=2 * 24 * 60)

    report, _ = await _hisobot(xodim)
    bosh = [d for d in report.days_series if d.inbound == 0 and d.outbound == 0]
    assert bosh, "o'rtadagi bo'sh kun ro'yxatda qolishi kerak"


@pytest.mark.asyncio
async def test_kompaniya_jamisi_mijozni_IKKI_MARTA_sanamaydi(xodim) -> None:
    """⚠️ P1: xato XUSHOMAD qiladigan tomonga edi.

    Bitta mijoz ikki xil xodimga qo'ng'iroq qilishi mumkin. Xodim
    kesimida bu to'g'ri ikki qator (javobgarlik alohida), kompaniya
    jamisida esa BITTA odam. Yig'indi olish asosiy raqamni shishtirardi —
    o'lchandi: 30 kunda 1341 o'rniga haqiqatda 1045 mijoz (+28%), qaytish
    darajasi 77.9% o'rniga 73.8%."""
    async with SessionFactory() as session:
        ikkinchi = AgentModel(
            full_name=f"faollik2-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(ikkinchi)
        await session.commit()
        ikkinchi_id = ikkinchi.id

    try:
        # BIR XIL raqam ikki xil xodimga qo'ng'iroq qildi
        await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
        await _qongiroq(ikkinchi_id, inbound=True, answered=False, offset_min=5)

        async with SessionFactory() as session:
            report = await ActivityService(session).report(
                since=BAZA - timedelta(hours=1),
                until=BAZA + timedelta(days=2),
                agent_ids=[xodim, ikkinchi_id],
            )

        yigindi = sum(a.missed_clients for a in report.agents)
        assert yigindi == 2, "xodim kesimida ikki qator — javobgarlik alohida"
        assert report.total.missed_clients == 1, (
            "kompaniya darajasida BITTA odam — yig'indi olinmasligi kerak"
        )
    finally:
        async with SessionFactory() as session:
            await session.execute(
                delete(AgentModel).where(AgentModel.id == ikkinchi_id)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_ikki_kesim_BIR_XIL_yigindi_beradi(xodim) -> None:
    """⚠️ BITTA grafik ikki kesimni ko'rsatadi (kun / soat).

    Ularning ustunlari va yig'indilari BIR XIL bo'lishi shart. Aks holda
    foydalanuvchi davrni almashtirganda sonlar sakrab, tizimga ishonchi
    qolmasdi — «qaysi biri to'g'ri?» degan savol paydo bo'lardi.

    Ilgari soatlik razrez faqat kiruvchi va faqat javob holati bilingan
    qatorlarni olardi, kunlik esa hammasini — ya'ni ikkisi turli narsani
    o'lchardi."""
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=30)
    await _qongiroq(xodim, inbound=True, answered=None, offset_min=45)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=60)
    await _qongiroq(xodim, inbound=False, answered=False, offset_min=90)

    report, row = await _hisobot(xodim)

    for nom, seriya in (("kunlik", report.days_series), ("soatlik", report.hours_series)):
        assert sum(r.inbound for r in seriya) == row.inbound_total, nom
        assert sum(r.inbound_answered for r in seriya) == row.inbound_answered, nom
        assert sum(r.missed for r in seriya) == row.missed, nom
        assert sum(r.outbound for r in seriya) == row.outbound_total, nom
        assert sum(r.outbound_no_answer for r in seriya) == row.outbound_no_answer, nom


@pytest.mark.asyncio
async def test_soatlik_foiz_BILINGAN_qatorlardan(xodim) -> None:
    """Noma'lum qatorlar soatlik foizni ham pasaytirmasligi kerak."""
    # Bir soat ichida: 1 javobsiz, 1 javobli, 3 noma'lum
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=5)
    for i in range(3):
        await _qongiroq(xodim, inbound=True, answered=None, offset_min=10 + i)

    report, _ = await _hisobot(xodim)
    soat = next(h for h in report.hours_series if h.inbound)
    assert soat.inbound == 5, "hajmda hammasi"
    # 1/2 = 50%, 1/5 = 20% BO'LMAYDI
    assert soat.missed_rate == 50.0


# ══════════════════════════════════════════════════════════════
#  Tafsilot ro'yxati — RAQAMNI ISBOTLAYDI
# ══════════════════════════════════════════════════════════════


async def _tafsilot(agent_id):
    async with SessionFactory() as session:
        return await ActivityService(session).missed_clients(
            agent_id=agent_id,
            since=BAZA - timedelta(hours=1),
            until=BAZA + timedelta(days=2),
        )


@pytest.mark.asyncio
async def test_tafsilot_JADVAL_BILAN_mos(xodim) -> None:
    """⚠️ ENG MUHIM SHART: «jadvalda 9, ro'yxatda 8» bo'lishi MUMKIN EMAS.

    Bu ro'yxat raqamni isbotlash uchun qo'yilgan. Agar u jamiga to'g'ri
    kelmasa, tekshirish vositasi o'zi ishonchni BUZARDI — rahbar oldida
    eng yomon natija.

    Ikkita tenglik qulflanadi:
      · qatorlar soni      = «mijoz» ustuni;
      · urinishlar yig'indi = «javobsiz» ustuni (raqamli mijozlar uchun).
    """
    # 1-mijoz: 3 marta urindi, qaytarildi
    for i in range(3):
        await _qongiroq(xodim, inbound=True, answered=False, offset_min=i)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=10)
    # 2-mijoz: 2 marta urindi, qaytarilmadi
    for i in range(2):
        await _qongiroq(
            xodim, inbound=True, answered=False, offset_min=100 + i,
            phone="+998 91 555-44-33",
        )

    _, row = await _hisobot(xodim)
    tafsilot = await _tafsilot(xodim)

    assert len(tafsilot) == row.missed_clients == 2
    assert sum(c.attempts for c in tafsilot) == row.missed == 5
    assert sum(1 for c in tafsilot if c.contacted_at is None) == row.clients_unreached


@pytest.mark.asyncio
async def test_tafsilot_boglanmaganlarni_YUQORIDA_beradi(xodim) -> None:
    """Ro'yxat ISH uchun — avval nima qilish kerakligi ko'rinishi kerak."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=5)
    await _qongiroq(
        xodim, inbound=True, answered=False, offset_min=60, phone="+998 91 555-44-33"
    )

    tafsilot = await _tafsilot(xodim)
    assert tafsilot[0].contacted_at is None, "bog'lanmagan yuqorida turishi kerak"


@pytest.mark.asyncio
async def test_tafsilot_aloqa_YONALISHINI_ajratadi(xodim) -> None:
    """Mijoz o'zi qayta urinib javob olgani va xodim qaytargani —
    IKKI BOSHQA holat va ular ajratilishi kerak: birinchisida kompaniya
    hech nima qilmagan, mijoz o'zi qaytgan."""
    # Mijoz o'zi qayta urindi va javob oldi
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=True, answered=True, offset_min=5)

    tafsilot = await _tafsilot(xodim)
    assert len(tafsilot) == 1
    assert tafsilot[0].contact_inbound is True, "mijoz o'zi qaytgan"
    assert tafsilot[0].minutes_to_contact == 5.0


@pytest.mark.asyncio
async def test_tafsilot_oynadan_tashqarini_olmaydi(xodim) -> None:
    """Oyna asosiy hisobot bilan bir xil bo'lishi shart."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=5 * 24 * 60)
    assert await _tafsilot(xodim) == []


# ══════════════════════════════════════════════════════════════
#  Davr chegarasi va aloqa oynasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_keyingi_kundagi_aloqa_HISOBGA_olinadi(xodim) -> None:
    """⚠️ ATAYLAB SHUNDAY: aloqa qidiruvi DAVR chegarasidan chiqadi.

    Mijoz 15-kuni kechqurun qo'ng'iroq qilib javob olmagan, 16-kuni
    ertalab qaytarilgan bo'lsa — u 15-kun hisobotida «bog'langan»
    bo'lishi kerak. Mijoz xizmat OLGAN va uni «bog'lanmagan» deb
    yozish haqiqatga zid bo'lardi.

    Haqiqiy ma'lumotda 15-avgustda 11 ta shunday holat bor.
    """
    kech = BAZA + timedelta(hours=14)  # kunning oxiri
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=14 * 60)
    # Ertasi ertalab qaytarildi — DAVRDAN TASHQARIDA
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=23 * 60)

    async with SessionFactory() as session:
        report = await ActivityService(session).report(
            since=BAZA,
            # Davr javobsiz qo'ng'iroqdan keyin TUGAYDI
            until=kech + timedelta(minutes=30),
            agent_ids=[xodim],
        )
    row = report.agents[0]
    assert row.missed == 1
    assert row.clients_reached == 1, (
        "davrdan tashqaridagi aloqa ham hisobga olinishi kerak"
    )
    assert row.clients_unreached == 0


@pytest.mark.asyncio
async def test_javobsiz_qongiroq_faqat_DAVR_ichidan_olinadi(xodim) -> None:
    """Aloqa qidiruvi kengaysa ham, JAVOBSIZ qo'ng'iroqning o'zi
    tanlangan davrdan olinadi — aks holda hisobot boshqa kunning
    muammosini ko'rsatardi."""
    # Davrdan KEYIN javobsiz qoldi
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=30 * 60)

    async with SessionFactory() as session:
        report = await ActivityService(session).report(
            since=BAZA, until=BAZA + timedelta(hours=12), agent_ids=[xodim]
        )
    assert report.agents[0].missed == 0


@pytest.mark.asyncio
async def test_tafsilot_ham_keyingi_kunni_KORSATADI(xodim) -> None:
    """⚠️ Jamlanma va tafsilot BIR XIL qoida bilan ishlashi shart.

    Tafsilot ro'yxati raqamni isbotlash uchun. Agar u davr chegarasida
    to'xtasa, jamlanmada «bog'langan» deb turgan mijoz ro'yxatda
    «bog'lanmagan» bo'lib chiqardi — tekshirish vositasi o'zi
    ishonchni buzardi."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=14 * 60)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=23 * 60)

    async with SessionFactory() as session:
        tafsilot = await ActivityService(session).missed_clients(
            agent_id=xodim,
            since=BAZA,
            until=BAZA + timedelta(hours=14, minutes=30),
        )
    assert len(tafsilot) == 1
    assert tafsilot[0].contacted_at is not None, "keyingi kundagi aloqa ko'rinishi kerak"
    assert tafsilot[0].minutes_to_contact == 540.0


@pytest.mark.asyncio
async def test_median_MIJOZ_boyicha_hisoblanadi(xodim) -> None:
    """Kartada qaytish darajasi (mijoz bo'yicha) va median yonma-yon
    turadi. Ular boshqa-boshqa birlikdan hisoblansa son o'z-o'ziga zid
    bo'lardi — o'lchandi: xodim kesimida 5,1 daqiqa, mijoz bo'yicha 4,1."""
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=10)

    report, _ = await _hisobot(xodim)
    assert report.callback_median_minutes == 10.0


@pytest.mark.asyncio
async def test_har_xodimning_MEDIANI_alohida(xodim) -> None:
    """⚠️ Daraja va VAQT ikki boshqa savolga javob beradi.

    Xodim 100% qaytarishi mumkin, lekin har birini uch soatdan keyin —
    daraja buni KO'RSATMAYDI. Haqiqiy ma'lumotda o'lchandi: «Колл
    центр» 89,4% qaytaradi, lekin medianasi 43 daqiqa; «Тошкент» esa
    93,1% da 2,5 daqiqa. Rahbarga ikkalasi ham kerak."""
    # Ikki mijoz: biri 5 daqiqada, ikkinchisi 15 daqiqada qaytarilgan
    await _qongiroq(xodim, inbound=True, answered=False, offset_min=0)
    await _qongiroq(xodim, inbound=False, answered=True, offset_min=5)
    await _qongiroq(
        xodim, inbound=True, answered=False, offset_min=100, phone="+998 91 555-44-33"
    )
    await _qongiroq(
        xodim, inbound=False, answered=True, offset_min=115, phone="+998 91 555-44-33"
    )

    _, row = await _hisobot(xodim)
    assert row.callback_rate == 100.0, "ikkalasiga ham qaytarilgan"
    assert row.callback_median_minutes == 10.0, "median (5 va 15) = 10 daqiqa"


@pytest.mark.asyncio
async def test_qaytarilmagan_xodimda_median_YOQ(xodim) -> None:
    """Median bo'lmasa `None` — nol EMAS. Nol «darhol qaytardi» degan
    ma'no berardi, holbuki umuman qaytarilmagan."""
    await _qongiroq(xodim, inbound=True, answered=False)
    _, row = await _hisobot(xodim)
    assert row.callback_median_minutes is None
