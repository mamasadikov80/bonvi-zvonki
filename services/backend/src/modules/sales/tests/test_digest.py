"""Rahbarga kunlik Telegram xabari.

⚠️ BU TESTLARNING BOSH VAZIFASI — XABAR YUBORILMASLIGINI ISBOTLASH.
Bu bo'lim tashqariga chiqadi: noto'g'ri guruhga tushgan xabarni
qaytarib bo'lmaydi. Shuning uchun «to'g'ri matn yig'ildimi» dan
oldin «sozlama o'chiq bo'lganda hech narsa ketmadimi» tekshiriladi.

⚠️ HAQIQIY TELEGRAM API GA CHIQILMAYDI. Yagona chiqish nuqtasi —
`infrastructure/telegram.send_message` va u HAR BIR testda soxta
funksiya bilan almashtiriladi (`sender` fixture'i). Almashtirilmagan
test qolib ketmasin: `sender` avtomatik ishlaydi (`autouse`), ya'ni
tarmoqqa chiqish yo'li umuman yopiq.

Xabar butun BAZA ustidan yig'iladi (eng oxirgi savdo kuni), shuning
uchun testdagi savdolar KELAJAKDAGI sanaga qo'yiladi — o'shanda
haqiqiy 2 383 operatsiya natijaga aralashmaydi.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, or_, select

from src.core.config import settings as env_settings
from src.core.database import SessionFactory
from src.modules.groups.domain.entities import BotStatus
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.sales.application import digest as mod
from src.modules.sales.application.compliance import ComplianceRow, SaleVerdict
from src.modules.sales.domain.entities import SaleOpType, WALK_IN_PARTNER_CODE
from src.modules.sales.infrastructure.models import SaleDigestModel, SaleModel
from src.modules.sales.infrastructure.telegram import (
    TELEGRAM_TEXT_LIMIT,
    send_message,
)

from src.modules.sales.tests import test_compliance as base

# `world` fixture'i va uning yordamchilari savdo nazorati testlaridan
# OLINADI, nusxa ko'chirilmaydi. Ular u yerda bir marta yozilgan:
# telefon kaliti bazada mavjud emasligini tekshirish, vaqt
# mintaqasi qoidasi va tozalash tartibi. Ikki joyda ikki xil bo'lib
# qolsa, bir test yashil turgani holda ikkinchisi jimgina noto'g'ri
# ma'lumot ustidan ishlardi.
#
# ⚠️ Import EMAS, moduldan olingan nom: fixture'ni to'g'ridan-to'g'ri
# import qilsak, uni parametr sifatida ishlatgan har bir test
# `F811` (import ustiga yozish) ogohlantirishini chiqarardi.
MARK = base.MARK
World = base.World
add_call = base.add_call
world = base.world

API = "http://test/api/v1"

#: Xabar HAR DOIM bazadagi eng oxirgi savdo kuni uchun yig'iladi.
#: Kelajakdagi sana — dev bazasidagi haqiqiy savdolar (oxirgisi
#: 20.08.2026) natijaga aralashmasin.
DIGEST_DAY = date(2027, 6, 10)

#: Sinov chati — hech qanday haqiqiy guruh emas.
TEST_CHAT = "-1009000000001"
TEST_TOKEN = "123456:pytest-token"


# ══════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def sender(monkeypatch) -> list[dict[str, Any]]:
    """Telegram o'rniga soxta yuboruvchi — TARMOQQA CHIQMAYDI.

    ⚠️ `autouse=True` ATAYLAB. Almashtirishni har testda qo'lda yozsak,
    bir kuni kimdir uni unutardi va test haqiqiy guruhga xabar
    yuborardi. Ro'yxat bo'sh qolishi — «hech narsa ketmadi» degan
    isbot.
    """
    sent: list[dict[str, Any]] = []

    async def _fake(*, token: str, chat_id: str, text: str):
        sent.append({"token": token, "chat_id": chat_id, "text": text})
        from src.modules.sales.infrastructure.telegram import SendResult

        return SendResult(ok=True, message_id=len(sent))

    monkeypatch.setattr(mod, "send_message", _fake)
    return sent


@pytest_asyncio.fixture(autouse=True)
async def _clean_digests() -> AsyncIterator[None]:
    """`sale_digests` dan test qoldiqlarini oldin ham, keyin ham o'chiradi.

    ⚠️ Bu jadval TAKRORLANMASLIK uchun ishlatiladi: test qoldirgan
    qator ishlab turgan tizimda kechasi keladigan haqiqiy xabarni
    jimgina o'chirib qo'yardi.
    """
    await _wipe_digests()
    yield
    await _wipe_digests()


async def _wipe_digests() -> None:
    async with SessionFactory() as session:
        await session.execute(
            delete(SaleDigestModel).where(
                or_(
                    SaleDigestModel.chat_id == TEST_CHAT,
                    SaleDigestModel.covered_on == DIGEST_DAY,
                )
            )
        )
        # Kelajakdagi sinov sanasidagi savdolar ham qolib ketmasin —
        # ular keyingi testda «eng oxirgi kun» bo'lib chiqardi.
        await session.execute(
            delete(SaleModel).where(SaleModel.occurred_on == DIGEST_DAY)
        )
        await session.commit()


@pytest_asyncio.fixture
async def sozlama(settings_guard) -> Callable[..., Any]:
    """Kunlik xabar sozlamalarini bir chaqiruvda qo'yadi."""

    async def _set(
        *, enabled: bool = True, chat: str | None = TEST_CHAT, min_amount: float = 0
    ) -> None:
        await settings_guard(mod.ENABLED_KEY, enabled)
        await settings_guard(mod.CHAT_ID_KEY, "" if chat is None else chat)
        await settings_guard(mod.MIN_AMOUNT_KEY, min_amount)
        await settings_guard(mod.BOT_TOKEN_KEY, TEST_TOKEN)

    return _set


async def add_sale(w: World, *, amount: float, day: date = DIGEST_DAY) -> uuid.UUID:
    """Bitta savdo — summasi bilan (xabar eng kattalarini ko'rsatadi)."""
    async with SessionFactory() as session:
        sale = SaleModel(
            external_id=f"{MARK}{uuid4().hex[:12]}",
            op_type=SaleOpType.SALE.value,
            occurred_on=day,
            branch=f"{MARK}filial",
            partner_code=w.partner_code,
            partner_name=f"{MARK}mijoz",
            amount=Decimal(str(amount)),
            currency="USD",
            amount_usd=Decimal(str(amount)),
            agent_id=w.agent_id,
            phone_key=w.phone_key or None,
            source_file="pytest",
        )
        session.add(sale)
        await session.commit()
        return sale.id


async def run(*, manual: bool = False) -> mod.DigestOutcome:
    async with SessionFactory() as session:
        return await mod.run_digest(session, manual=manual)


# ══════════════════════════════════════════════════════════════
#  ⚠️ YUBORILMASLIK — eng muhim qism
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ochiq_bolganda_HECH_NARSA_YUBORILMAYDI(
    world, sozlama, sender
) -> None:
    """Sukut holati: kalit o'chiq — xabar yig'ilmaydi ham, ketmaydi ham."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=False)

    outcome = await run()

    assert outcome.sent is False
    assert outcome.reason == "disabled"
    assert outcome.text == ""
    assert sender == [], "O'chiq sozlamada Telegram'ga murojaat bo'lmasligi kerak"


@pytest.mark.asyncio
async def test_sozlama_umuman_yozilmagan_bolsa_ham_yubormaydi(
    world, sender
) -> None:
    """Reyestrdagi SUKUT qiymati tekshiriladi — bazada qator yo'q.

    Yangi o'rnatilgan tizimda `sales.digest_enabled` bazada umuman
    bo'lmaydi. O'shanda ham javob bitta bo'lishi kerak: yubormaslik.
    """
    w = await world()
    await add_sale(w, amount=1000)

    outcome = await run()

    assert outcome.sent is False
    assert outcome.reason == "disabled"
    assert sender == []


@pytest.mark.asyncio
async def test_chat_korsatilmaganda_yubormaydi(world, sozlama, sender) -> None:
    """Kalit yoqilgan, lekin manzil yo'q — xabar ketmaydi.

    Matn baribir qaytariladi: foydalanuvchi nima yo'qotayotganini
    ko'rsin va chatni to'ldirsin.
    """
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True, chat=None)

    outcome = await run()

    assert outcome.sent is False
    assert outcome.reason == "no_chat"
    assert outcome.text, "Matn ko'rsatilishi kerak — muammo faqat manzilda"
    assert sender == []


@pytest.mark.asyncio
async def test_bot_token_yoq_bolsa_yubormaydi(
    world, sozlama, settings_guard, monkeypatch, sender
) -> None:
    """Bot tokeni bo'lmasa — Telegram'ga chiqishning iloji yo'q.

    ⚠️ TOKENNI BO'SHATISH UCHUN BAZANI TOZALASH YETARLI EMAS.
    `telegram.bot_token` da `env_var` bor, ya'ni sozlamalar
    ustuvorligi «baza > .env > standart» bo'yicha bo'sh qiymat
    `.env` dagi haqiqiy tokenga qaytadi. Bu xatolik emas —
    reyestrdagi ataylab qilingan tanlov, lekin testda ikkala
    manbani ham yopish kerak.
    """
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True)
    await settings_guard(mod.BOT_TOKEN_KEY, "")
    monkeypatch.setattr(env_settings, "TELEGRAM_BOT_TOKEN", "")

    outcome = await run()

    assert outcome.sent is False
    assert outcome.reason == "no_token"
    assert sender == []


@pytest.mark.asyncio
async def test_bot_guruhdan_chiqarilgan_bolsa_yubormaydi(
    world, sozlama, sender
) -> None:
    """`telegram_groups` da bot `kicked` bo'lsa — urinib ham ko'rmaymiz."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True)

    async with SessionFactory() as session:
        session.add(
            TelegramGroupModel(
                chat_id=int(TEST_CHAT),
                title=f"{MARK}guruh",
                bot_status=BotStatus.KICKED.value,
            )
        )
        await session.commit()

    try:
        outcome = await run()
        assert outcome.sent is False
        assert outcome.reason == "bot_not_in_chat"
        assert sender == []
    finally:
        async with SessionFactory() as session:
            await session.execute(
                delete(TelegramGroupModel).where(
                    TelegramGroupModel.chat_id == int(TEST_CHAT)
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_yangi_import_bolmasa_ikkinchi_marta_yubormaydi(
    world, sozlama, sender
) -> None:
    """Takroriy xabar shovqin — u xabarni umuman o'qimaslikka olib keladi."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True)

    birinchi = await run()
    assert birinchi.sent is True
    assert len(sender) == 1

    ikkinchi = await run()
    assert ikkinchi.sent is False
    assert ikkinchi.reason == "no_new_import"
    assert len(sender) == 1, "Ikkinchi xabar ketmasligi kerak"

    # Yangi savdo importi bo'lgach xabar YANA ketadi
    await add_sale(w, amount=2000)
    uchinchi = await run()
    assert uchinchi.sent is True
    assert len(sender) == 2


@pytest.mark.asyncio
async def test_savdo_umuman_bolmasa(sozlama, sender) -> None:
    """Kelajakdagi kun bo'sh — lekin bazada haqiqiy savdolar bor.

    Bu holatda xabar oxirgi HAQIQIY kun uchun yig'iladi; muhimi —
    yiqilmaydi va sonlar manfiy bo'lmaydi.
    """
    await sozlama(enabled=True)

    outcome = await run()

    assert outcome.reason in (None, "no_sales")
    if outcome.day is not None:
        assert outcome.counts["total"] >= 0


# ══════════════════════════════════════════════════════════════
#  Matn yig'ilishi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sonlar_togri(world, sozlama) -> None:
    """Uchala toifa ham sanaladi va matnda ko'rinadi."""
    toza = await world()
    shubhali = await world()
    nomalum = await world(code=WALK_IN_PARTNER_CODE)

    # `toza` — savdo kunida suhbat bo'lgan
    await add_sale(toza, amount=500)
    await add_call(toza, DIGEST_DAY)

    # `shubhali` — birorta suhbat yo'q (R1 va R3)
    await add_sale(shubhali, amount=9000)
    await add_sale(shubhali, amount=7000)

    # `nomalum` — umumiy kod, tekshirib bo'lmaydi
    await add_sale(nomalum, amount=300)

    async with SessionFactory() as session:
        data = await mod.collect(session)

    assert data is not None
    assert data.day == DIGEST_DAY
    assert data.total == 4
    assert data.ok == 1
    assert data.suspicious == 2
    assert data.not_checkable == 1

    # Eng katta shubhali savdo birinchi turadi
    assert [row.amount_usd for row in data.top] == [9000.0, 7000.0]

    text = mod.build_text(data)
    assert "Savdo nazorati — 10.06.2027" in text
    assert "✅ Toza: <b>1</b>" in text
    assert "⚠️ Shubhali: <b>2</b>" in text
    assert "❔ Tekshirib bo'lmadi: <b>1</b>" in text
    assert "9 000 $" in text
    # Ayblov emasligi HAR DOIM yoziladi
    assert "AYBLAMAYDI" in text


@pytest.mark.asyncio
async def test_summa_chegarasi_kichik_savdolarni_olib_tashlaydi(
    world, sozlama
) -> None:
    """`sales.digest_min_amount` — faqat xabarga tegishli."""
    w = await world()
    await add_sale(w, amount=50)
    await add_sale(w, amount=5000)

    async with SessionFactory() as session:
        data = await mod.collect(session, min_amount=1000)

    assert data is not None
    assert data.total == 1
    assert data.skipped_by_amount == 1
    assert [row.amount_usd for row in data.top] == [5000.0]


@pytest.mark.asyncio
async def test_summasi_nomalum_savdo_chegaradan_otadi(world) -> None:
    """«Bilmadim» — «kichik» degani emas, savdo ro'yxatda qoladi."""
    w = await world()
    async with SessionFactory() as session:
        session.add(
            SaleModel(
                external_id=f"{MARK}{uuid4().hex[:12]}",
                op_type=SaleOpType.SALE.value,
                occurred_on=DIGEST_DAY,
                branch=f"{MARK}filial",
                partner_code=w.partner_code,
                partner_name=f"{MARK}mijoz",
                amount=None,
                currency="USD",
                amount_usd=None,
                agent_id=w.agent_id,
                phone_key=w.phone_key,
                source_file="pytest",
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        data = await mod.collect(session, min_amount=10_000)

    assert data is not None
    assert data.total == 1


@pytest.mark.asyncio
async def test_xodimlar_kesimi_beshtadan_keyin_qisqaradi(world) -> None:
    """«va yana N ta» — telefon ekraniga sig'sin."""
    for _ in range(7):
        w = await world()
        await add_sale(w, amount=1000)

    async with SessionFactory() as session:
        data = await mod.collect(session)

    assert data is not None
    assert len(data.agents) == 7
    text = mod.build_text(data)
    assert "…va yana 2 ta xodim" in text
    # Beshtadan ortiq xodim qatori chiqmasin
    assert text.count("shubhali /") == mod.TOP_AGENTS


# ══════════════════════════════════════════════════════════════
#  4096 belgi — Telegram chegarasi
# ══════════════════════════════════════════════════════════════


def _row(name: str) -> ComplianceRow:
    """Uzun nomli soxta qator — chegarani sinash uchun."""
    return ComplianceRow(
        id=uuid4(),
        occurred_on=DIGEST_DAY,
        external_id="x",
        partner_code="К00099",
        partner_name=name,
        phone=None,
        phone_key="901234567",
        branch=name,
        direction="ВЕЛО",
        agent_id=None,
        agent_name=name,
        amount=1000.0,
        currency="USD",
        amount_usd=1000.0,
        verdict=SaleVerdict(
            sale_id=uuid4(),
            verdict="suspicious",
            broken_rules=["R1", "R2", "R3"],
            skip_reason=None,
            last_call_at=datetime(2027, 6, 1, 9, 0, tzinfo=UTC),
            last_call_agent=name,
            days_before=9,
            previous_sale_on=DIGEST_DAY - timedelta(days=4),
            calls_between=0,
            calls_total=0,
        ),
        review=None,
    )


def test_4096_chegarasidan_oshmaydi() -> None:
    """⚠️ Chegaradan uzun xabar YUBORILMAYDI — Telegram 400 qaytaradi.

    Ya'ni «uzun bo'lsa kesilar» degan umid ish bermaydi: xabar
    butunlay yo'qolardi. Shuning uchun matn sig'guncha qisqaradi.
    """
    uzun = "Ў" * 200
    data = mod.DigestData(
        day=DIGEST_DAY,
        window_days=3,
        min_amount=0,
        total=900,
        ok=100,
        suspicious=700,
        not_checkable=100,
        agents=[mod.AgentLine(name=uzun + str(i), sales=90, suspicious=80) for i in range(40)],
        top=[_row(uzun + str(i)) for i in range(40)],
    )

    text = mod.build_text(data)

    assert len(text) <= TELEGRAM_TEXT_LIMIT
    # Ma'no yo'qolmasin: sonlar va ayblov emasligi haqidagi jumla qolsin
    assert "Shubhali: <b>700</b>" in text


@pytest.mark.asyncio
async def test_uzun_matn_tarmoqqa_umuman_chiqmaydi() -> None:
    """Chegaradan oshgan matn Telegram'ga JO'NATILMAYDI.

    Bu — himoyaning oxirgi qavati: matn yig'ishda xato bo'lsa ham
    so'rov tarmoqqa chiqmaydi (test shu sababli haqiqiy
    `send_message` ni chaqiradi va u tarmoqsiz qaytishi kerak).
    """
    result = await send_message(
        token=TEST_TOKEN, chat_id=TEST_CHAT, text="x" * (TELEGRAM_TEXT_LIMIT + 1)
    )
    assert result.ok is False
    assert "juda uzun" in (result.error or "")


# ══════════════════════════════════════════════════════════════
#  HTTP chegarasi — «Sinov xabari» tugmasi
# ══════════════════════════════════════════════════════════════
#
# ⚠️ Xizmat qatlamini sinash yetarli emas (test_compliance.py dagi
# izohga qarang): javob `slots=True` dataclass'dan yig'iladi va
# bunday xato FAQAT Pydantic javobni qurayotganda chiqadi.


@pytest.mark.asyncio
async def test_endpoint_sinov_xabari(admin_client, world, sozlama, sender) -> None:
    """`POST /sales/digest/test` — matn bilan birga qaytadi."""
    w = await world()
    await add_sale(w, amount=4200)
    await sozlama(enabled=True)

    response = await admin_client.post(f"{API}/sales/digest/test")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] is True
    assert body["chat_id"] == TEST_CHAT
    assert body["day"] == DIGEST_DAY.isoformat()
    assert body["chars"] == len(body["text"])
    assert body["chars"] <= TELEGRAM_TEXT_LIMIT
    assert "Savdo nazorati" in body["text"]
    assert body["counts"]["suspicious"] >= 1
    assert len(sender) == 1


@pytest.mark.asyncio
async def test_sinov_ochiq_sozlamada_ham_ishlaydi(
    admin_client, world, sozlama, sender
) -> None:
    """Tugmaning ma'nosi — kalitni YOQISHDAN OLDIN matnni ko'rish."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=False)

    response = await admin_client.post(f"{API}/sales/digest/test")

    assert response.status_code == 200, response.text
    assert response.json()["sent"] is True
    assert len(sender) == 1


@pytest.mark.asyncio
async def test_sinov_kunlik_xabarni_ochirib_qoymaydi(
    admin_client, world, sozlama, sender
) -> None:
    """Sinov `kind='test'` bo'lib tushadi — kechasi xabar baribir keladi."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True)

    await admin_client.post(f"{API}/sales/digest/test")
    kunlik = await run()

    assert kunlik.sent is True
    assert len(sender) == 2

    async with SessionFactory() as session:
        kinds = (
            (
                await session.execute(
                    select(SaleDigestModel.kind).where(
                        SaleDigestModel.chat_id == TEST_CHAT
                    )
                )
            )
            .scalars()
            .all()
        )
    assert sorted(kinds) == ["daily", "test"]


@pytest.mark.asyncio
async def test_sinov_chatsiz_matnni_qaytaradi(
    admin_client, world, sozlama, sender
) -> None:
    """Manzil yo'q — xato emas, lekin `sent=false` va sabab ochiq."""
    w = await world()
    await add_sale(w, amount=1000)
    await sozlama(enabled=True, chat=None)

    response = await admin_client.post(f"{API}/sales/digest/test")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] is False
    assert body["reason"] == "no_chat"
    assert body["text"]
    assert sender == []


@pytest.mark.asyncio
async def test_savdo_xodimi_sinov_xabarini_YUBORA_OLMAYDI(sales_client) -> None:
    """`sales:review` — SALES rolida yo'q va bo'lmasligi kerak.

    Bu ro'yxat xodim ustidan tekshiruv; uni guruhga yuborish huquqi
    ham xodimda bo'lishi mumkin emas.
    """
    client, _ = sales_client
    response = await client.post(f"{API}/sales/digest/test")
    assert response.status_code == 403
