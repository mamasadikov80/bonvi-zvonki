"""Guruh asosidagi anonim so'rovnoma.

Bu modul uchta mustaqil ishni bajaradi:

  1. RO'YXATGA OLISH — bot guruhga qo'shilsa/chiqarilsa yoki kimdir
     `/bind` yozsa, guruh backend'ga yoziladi va admin panelida
     ko'rinadi. Admin chat id ni qo'lda kiritmaydi.
  2. BALL — guruhdagi 1–5 tugmasi. Eng nozik joy: Telegram ID
     jarayondan chiqmaydi, backend'ga faqat hash ketadi.
  3. TAFSILOT — shaxsiy chatdagi ixtiyoriy izoh va sabablar ro'yxati.

Eski, client uchun mo'ljallangan oqim `handlers/survey.py` da qoladi —
u tegilmaydi.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from src.core.anonymity import respondent_hash, short
from src.services.binding import AgentBinder

# Bu uchtasi endi `services/chat_info.py` da yashaydi (servis qatlami
# ham ularga muhtoj). Shu yerdan import qilinishi ATAYLAB: eski
# `from src.handlers.groups import member_count_of` importlari
# o'zgarishsiz ishlashda davom etadi.
from src.services.chat_info import (  # noqa: F401  (qayta eksport)
    GROUP_CHATS,
    INSIDE,
    STATUS_MAP,
    current_status,
    member_count_of,
)
from src.services.internal_api import DetailOutcome, InternalApiClient
from src.services.throttle import CounterThrottle
from src.states.groups import GroupDetail
from src.views.groups import (
    BACK,
    CANCEL,
    COMMENT,
    DONE,
    FLAG_PREFIX,
    comment_kb,
    detail_intro,
    flags_unavailable_text,
    red_flags_kb,
)

logger = logging.getLogger(__name__)
router = Router(name="groups")

WELCOME = (
    "✅ <b>Guruh ro'yxatga olindi.</b>\n\n"
    "Endi admin panelidan savdo xodimi va hudud biriktiring — "
    "shundan keyin bu guruhga anonim so'rovnomalar yuboriladi."
)


# ══════════════════════════════════════════════════════════════
#  1. Guruhni ro'yxatga olish
# ══════════════════════════════════════════════════════════════


@router.my_chat_member()
async def on_bot_status_changed(
    event: ChatMemberUpdated,
    bot: Bot,
    internal: InternalApiClient,
    binder: AgentBinder,
) -> None:
    """Bot guruhga qo'shildi / admin bo'ldi / chiqarildi."""
    chat = event.chat
    if chat.type not in GROUP_CHATS:
        return

    was = STATUS_MAP.get(event.old_chat_member.status, "left")
    now = STATUS_MAP.get(event.new_chat_member.status, "left")
    if was == now:
        return

    registered = await _register(bot, chat.id, chat.title, now, internal)

    # ── Biriktirishning 1- va 2-yo'li ─────────────────────────────
    # Botni QO'SHGAN odam ko'pincha o'sha guruhning savdo xodimi —
    # bu eng arzon va eng ishonchli belgi, boshqa hech qanday so'rov
    # talab qilmaydi. Mos kelmasa, adminlar ro'yxati ko'riladi.
    if now in INSIDE:
        await binder.discover(
            bot,
            chat.id,
            chat.title,
            bot_status=now,
            adder_id=event.from_user.id if event.from_user else None,
        )

    # Faqat guruhga KIRGANDA salomlashamiz (admin bo'lish yoki
    # huquq o'zgarishi uchun qayta-qayta yozib turmaymiz).
    if now in INSIDE and was not in INSIDE and registered:
        await _say(bot, chat.id, WELCOME)


@router.message(Command("bind", "start"), F.chat.type.in_(GROUP_CHATS))
async def bind_group(
    message: Message, bot: Bot, internal: InternalApiClient, binder: AgentBinder
) -> None:
    """Qo'lda ro'yxatga olish — `/bind` (guruhda `/start` ham shu).

    NEGA KERAK: Telegram Bot API da "bot qaysi guruhlarda bor" degan
    metod YO'Q, `my_chat_member` esa faqat O'ZGARISH paytida keladi.
    Ya'ni bot bu handler paydo bo'lishidan OLDIN qo'shilgan guruhlar
    hech qachon o'zi ko'rinmaydi. Shu buyruq — o'sha guruhlar uchun
    yagona yo'l: guruhdagi istalgan a'zo bir marta yozsa yetadi.
    """
    status = await current_status(bot, message.chat.id)
    registered = await _register(
        bot, message.chat.id, message.chat.title, status, internal
    )

    # `/bind` ni odatda o'sha guruhning savdo xodimi yozadi. Bu xabar
    # `handlers/autobind.py` dagi umumiy handler'gacha yetib bormaydi
    # (aiogram birinchi mos kelganda to'xtaydi), shuning uchun nomzod
    # shu yerda qo'lda uzatiladi.
    if message.from_user is not None and not message.from_user.is_bot:
        await binder.discover(
            bot,
            message.chat.id,
            message.chat.title,
            bot_status=status,
            sender_id=message.from_user.id,
        )

    # Javob yuborilmasligi mumkin (bot ovozi o'chirilgan, xabar
    # o'chirilgan va h.k.) — lekin guruh ALLAQACHON ro'yxatga olingan,
    # shuning uchun bu xato butun handler'ni yiqitmasin.
    await _reply(
        message,
        WELCOME
        if registered
        else (
            "⚠️ Hozir ro'yxatga olib bo'lmadi — server javob bermadi.\n"
            "Birozdan keyin <code>/bind</code> ni qayta yuboring."
        ),
    )


@router.message(F.new_chat_title, F.chat.type.in_(GROUP_CHATS))
async def on_title_changed(
    message: Message, bot: Bot, internal: InternalApiClient
) -> None:
    """Guruh nomi o'zgardi — panelda eski nom qolib ketmasin."""
    status = await current_status(bot, message.chat.id)
    await _register(bot, message.chat.id, message.new_chat_title, status, internal)


async def _register(
    bot: Bot,
    chat_id: int,
    title: str | None,
    status: str,
    internal: InternalApiClient,
) -> bool:
    """`POST /groups/register` — a'zolar soni bilan birga (bo'lsa)."""
    member_count = await member_count_of(bot, chat_id) if status in INSIDE else None
    result = await internal.register_group(
        chat_id=chat_id,
        title=(title or "").strip() or "Nomsiz guruh",
        member_count=member_count,
        bot_status=status,
    )
    if result is None:
        logger.warning("⚠️  Guruh ro'yxatga olinmadi (chat %s)", chat_id)
        return False

    logger.info(
        "👥 Guruh ro'yxatda: %s · holat=%s · a'zolar=%s · biriktirilgan=%s",
        chat_id,
        status,
        member_count if member_count is not None else "—",
        "ha" if result.get("agent_id") else "yo'q",
    )
    return True


async def _say(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as exc:
        logger.debug("xabar yuborilmadi (chat %s): %s", chat_id, exc)


async def _reply(message: Message, text: str) -> None:
    try:
        await message.reply(text)
    except Exception as exc:
        logger.debug("javob yuborilmadi (chat %s): %s", message.chat.id, exc)


# ══════════════════════════════════════════════════════════════
#  2. Ball qo'yish — anonimlik shu yerda hal bo'ladi
# ══════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("rate:"))
async def on_rate(
    call: CallbackQuery,
    bot: Bot,
    internal: InternalApiClient,
    throttle: CounterThrottle,
) -> None:
    """`rate:<token>:<n>` — guruhdagi ball tugmasi.

    NEGA BU HANDLER MINI APP REJIMIDA HAM RO'YXATDA QOLADI
      `telegram.miniapp_name` to'ldirilgach YANGI xabarlarda 1–5
      tugmalari bo'lmaydi, lekin sozlamadan OLDIN yuborilgan xabarlar
      guruhlarda o'z tugmalari bilan turaveradi — Telegram eski
      xabarlarni o'zi o'zgartirmaydi. Kimdir ertaga o'sha xabardagi
      «4️⃣» ni bossa, handler o'chirilgan bo'lsa, bosish javobsiz
      qolardi: odam «baho ketmadi» deb o'ylaydi, ball esa yo'qoladi.
      Shuning uchun bu yo'l eski xabarlar muddati tugaguncha ochiq
      turadi. Mini App rejimidagi yangi xabarlarda `callback_data`
      umuman yo'q, ya'ni bu handler ularga hech qachon tegmaydi.

    Shu sababdan hisoblagich ham ESKI shaklda qayta chiziladi
    (`throttle.push` → `survey_kb(...)` qisqa nomsiz): bu callback
    faqat eski xabardan kelishi mumkin, uning tugmalari esa
    tahrirdan keyin ham joyida qolishi kerak.
    """
    parsed = _parse_rate(call.data or "")
    if parsed is None:
        await call.answer("Tugma eskirgan.", show_alert=True)
        return
    token, score = parsed

    # ── Anonimlik: xom ID shu qatordan nariga o'tmaydi ──────────
    # `call.from_user.id` faqat hash hisoblash uchun o'qiladi.
    # Natija — qaytarib bo'lmaydigan hash; backend'ga faqat u ketadi,
    # logga esa uning ham qisqartmasi tushadi.
    digest = respondent_hash(token, call.from_user.id)

    result = await internal.rate(token, digest, score)

    if result is None:
        await call.answer(
            "⚠️ Hozir bahoni qabul qilib bo'lmadi.\n"
            "Iltimos, birozdan keyin qayta urinib ko'ring.",
            show_alert=True,
        )
        return

    if result.already_rated:
        # Xato emas — oddiy holat. Ohang xotirjam bo'lsin.
        await call.answer(
            "Siz allaqachon baho bergansiz 🙏\n"
            "Har bir kishi bir marta baho qo'yadi.",
            show_alert=True,
        )
        return

    # `show_alert=True` — javob FAQAT bosgan odamga ko'rinadi.
    # Guruhda hech qanday iz qolmaydi.
    #
    # Matn izohga UMUMAN chaqirmaydi: tugmalar rejimida so'rovnoma shu
    # bosish bilan tugaydi. Ilgari bu yerda «xabardagi "💬 Izoh va sabab
    # qo'shish" tugmasi» haqida yozilardi — o'sha tugma esa allaqachon
    # olib tashlangan edi, ya'ni mijoz yo'q tugmani qidirardi.
    await call.answer(
        "Rahmat! Bahoyingiz qabul qilindi ✅",
        show_alert=True,
    )
    logger.info("⭐ Baho qabul qilindi · token=%s · javob=%s", token, short(digest))

    # Hisoblagichni yangilash — to'g'ridan-to'g'ri emas, siqib
    # (qarang: services/throttle.py, 30 kishi bir vaqtda bossa).
    if call.message is not None:
        me = await bot.me()
        await throttle.push(
            bot=bot,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            token=token,
            bot_username=me.username or "",
            count=result.response_count,
        )


def _parse_rate(data: str) -> tuple[str, int] | None:
    """`rate:<token>:<n>` → (token, n). Noto'g'ri bo'lsa None."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "rate":
        return None
    token = parts[1].strip()
    if not token:
        return None
    try:
        score = int(parts[2])
    except ValueError:
        return None
    return (token, score) if 1 <= score <= 5 else None


# ══════════════════════════════════════════════════════════════
#  3. Shaxsiy chatdagi tafsilot bosqichi
# ══════════════════════════════════════════════════════════════


async def open_detail(
    message: Message, state: FSMContext, internal: InternalApiClient, token: str
) -> None:
    """`/start srv_<token>` guruh so'rovnomasi uchun kelganda.

    `handlers/survey.py` dagi deep-link handleri shu funksiyani
    chaqiradi (qaysi oqim ekani o'sha yerda hal qilinadi).
    """
    await state.set_state(GroupDetail.flags)
    await state.update_data(token=token, selected=[], comment=None)

    flags = await internal.red_flags()
    if not flags:
        # Ro'yxat kelmadi — izoh baribir yozilsin, oqim to'xtamasin.
        await message.answer(flags_unavailable_text(), reply_markup=red_flags_kb([], [], False))
        return

    await message.answer(
        detail_intro(0, None), reply_markup=red_flags_kb(flags, [], False)
    )


@router.callback_query(GroupDetail.flags, F.data.startswith(FLAG_PREFIX))
async def toggle_flag(
    call: CallbackQuery, state: FSMContext, internal: InternalApiClient
) -> None:
    """Sababni belgilash/bekor qilish — klaviatura qayta chiziladi."""
    key = (call.data or "")[len(FLAG_PREFIX) :]
    data = await state.get_data()
    selected: list[str] = list(data.get("selected") or [])

    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    await state.update_data(selected=selected)

    comment = data.get("comment")
    flags = await internal.red_flags()
    await _redraw(call, flags, selected, comment)
    await call.answer()


@router.callback_query(GroupDetail.flags, F.data == COMMENT)
async def ask_comment(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GroupDetail.comment)
    await _edit(
        call,
        "💬 <b>Izohingizni yozing.</b>\n\n"
        "Nima yoqmadi yoki nimani yaxshilashimiz kerak?\n"
        "<i>Izoh anonim — kim yozganini hech kim ko'rmaydi.</i>",
        comment_kb(),
    )
    await call.answer()


@router.message(GroupDetail.comment, F.text)
async def save_comment(
    message: Message, state: FSMContext, internal: InternalApiClient
) -> None:
    """Izoh yozildi — sabablar ro'yxatiga qaytamiz (hali yuborilmadi)."""
    comment = (message.text or "").strip()[:2000]
    await state.update_data(comment=comment)
    await state.set_state(GroupDetail.flags)

    data = await state.get_data()
    selected: list[str] = list(data.get("selected") or [])
    flags = await internal.red_flags()

    await message.answer(
        detail_intro(len(selected), comment),
        reply_markup=red_flags_kb(flags, selected, bool(comment)),
    )


@router.callback_query(GroupDetail.comment, F.data == BACK)
async def back_to_flags(
    call: CallbackQuery, state: FSMContext, internal: InternalApiClient
) -> None:
    await state.set_state(GroupDetail.flags)
    data = await state.get_data()
    selected: list[str] = list(data.get("selected") or [])
    flags = await internal.red_flags()
    await _redraw(call, flags, selected, data.get("comment"))
    await call.answer()


@router.callback_query(GroupDetail.flags, F.data == CANCEL)
async def cancel_detail(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(
        call,
        "✅ Yaxshi, bahoyingiz allaqachon hisobga olingan.\nRahmat!",
        None,
    )
    await call.answer()


@router.callback_query(GroupDetail.flags, F.data == DONE)
async def submit_detail(
    call: CallbackQuery, state: FSMContext, internal: InternalApiClient
) -> None:
    """«Tayyor» — izoh va sabablarni backend'ga yuboradi."""
    data = await state.get_data()
    token = str(data.get("token") or "")
    selected: list[str] = list(data.get("selected") or [])
    comment: str | None = data.get("comment")

    if not token:
        await state.clear()
        await call.answer("Sessiya eskirgan — guruhdagi tugmani qayta bosing.", show_alert=True)
        return

    if not selected and not comment:
        # Bo'sh yuborishdan ma'no yo'q — ohista turtki beramiz.
        await call.answer("Sabab tanlang yoki izoh yozing 🙏")
        return

    digest = respondent_hash(token, call.from_user.id)
    outcome = await internal.send_detail(token, digest, comment, selected)

    if outcome is DetailOutcome.OK:
        await state.clear()
        await _edit(
            call,
            "✅ <b>Rahmat!</b>\n\n"
            "Javobingiz qabul qilindi va faqat rahbariyatga ko'rinadi.\n"
            "Kim yozganini hech kim bilmaydi.",
            None,
        )
        await call.answer()
        return

    if outcome is DetailOutcome.NOT_RATED:
        # Xom xatoni ko'rsatmaymiz — nima qilish kerakligini aytamiz.
        await state.clear()
        await _edit(
            call,
            "ℹ️ <b>Avval ball qo'yish kerak.</b>\n\n"
            "Guruhga qayting va so'rovnoma xabaridagi "
            "<b>1️⃣–5️⃣</b> tugmalaridan birini bosing.\n"
            "Shundan keyin bu yerga qaytib izoh yozishingiz mumkin.",
            None,
        )
        await call.answer(
            "Avval guruhda 1–5 ball qo'ying, keyin izoh yozing.", show_alert=True
        )
        return

    # FAILED — holat saqlanadi, odam qayta urinib ko'ra oladi
    await call.answer(
        "⚠️ Hozir yuborib bo'lmadi. Birozdan keyin «Tayyor» ni qayta bosing.",
        show_alert=True,
    )


# ── Chizish yordamchilari ─────────────────────────────────────


async def _redraw(
    call: CallbackQuery,
    flags: list[tuple[str, str]],
    selected: list[str],
    comment: str | None,
) -> None:
    await _edit(
        call,
        detail_intro(len(selected), comment),
        red_flags_kb(flags, selected, bool(comment)),
    )


async def _edit(call: CallbackQuery, text: str, markup) -> None:
    """Xabarni tahrirlaydi; imkoni bo'lmasa yangisini yuboradi."""
    message = call.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception as exc:
        if "not modified" in str(exc).lower():
            return
        logger.debug("tafsilot oynasi tahrirlanmadi: %s", exc)
        try:
            await message.answer(text, reply_markup=markup)
        except Exception:
            pass
