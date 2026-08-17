"""Guruh so'rovnomasining shaxsiy chatdagi tafsilot bosqichi (FSM).

Oqim:

    guruhda 1–5 tugma  →  (ball qabul qilindi, show_alert)
           ↓  «💬 Izoh va sabab qo'shish» — URL tugma
    shaxsiy chat:  sabablar ro'yxati  ⇄  izoh yozish
           ↓  «✅ Tayyor»
    POST /surveys/{token}/detail  →  rahmat

Ball bu bosqichda SO'RALMAYDI — u allaqachon guruhda qo'yilgan.
Holat `RedisStorage` da saqlanadi, shuning uchun bot qayta ishga
tushsa ham yarim to'ldirilgan ro'yxat yo'qolmaydi.
"""

from aiogram.fsm.state import State, StatesGroup


class GroupDetail(StatesGroup):
    flags = State()  # ko'p tanlovli sabablar ro'yxati (asosiy oyna)
    comment = State()  # izoh matni kutilmoqda
