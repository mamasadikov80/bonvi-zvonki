"""Umumiy xato tutuvchi — anonimlikni loglarda ham saqlaydi.

Handler ichida kutilmagan istisno chiqsa, aiogram uni O'ZI logga
yozadi va xabar bilan birga BUTUN `Update` obyektini chiqaradi —
u yerda `from_user` (id, ism, username) bor. Ya'ni bitta tasodifiy
xato anonimlik va'dasini buzib qo'yishi mumkin.

Shuning uchun barcha xatolar shu yerda tutiladi va faqat istisno
turi bilan matni yoziladi. `True` qaytarilgani aiogram'ga "xato
ishlandi" deydi va u update ni loglamaydi.
"""

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    logger.error("❌ Handler xatosi: %s: %s", type(exc).__name__, exc)
    return True
