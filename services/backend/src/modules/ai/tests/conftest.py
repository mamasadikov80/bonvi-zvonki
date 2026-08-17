"""Test sozlamalari.

`pytest-asyncio` har test uchun yangi event loop yaratadi, SQLAlchemy pool'i
esa oldingi loop'ga bog'langan ulanishlarni saqlab qoladi. Shuning uchun har
testdan oldin va keyin pool bo'shatiladi.
"""

import pytest_asyncio

from src.core.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool():
    await engine.dispose()
    yield
    await engine.dispose()
