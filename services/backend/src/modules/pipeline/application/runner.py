"""Celery (sinxron) va quvur (asinxron) o'rtasidagi ko'prik.

Muammo: Celery vazifasi oddiy funksiya, quvur esa `async`. Har vazifada
`asyncio.run()` chaqirish — TUZOQ: `asyncio.run` tugaganda event loop
yopiladi, SQLAlchemy pool'idagi asyncpg ulanishlari esa o'sha yopilgan
loop'ga bog'langan qoladi va ikkinchi vazifa «attached to a different
loop» xatosiga uchraydi.

Yechim: har WORKER JARAYONIDA bitta doimiy loop. U yopilmaydi,
ulanishlar pool'da tirik qoladi, keyingi vazifa tayyor ulanishni oladi.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None


def get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return get_loop().run_until_complete(coro)


def reset_loop() -> None:
    """Worker jarayoni fork bo'lgach chaqiriladi — meros loop ishlatilmasin."""
    global _loop
    if _loop is not None and not _loop.is_closed():
        _loop.close()
    _loop = None
