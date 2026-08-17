"""`runner.py` — Celery jarayonidagi YAGONA event loop.

Sof unit test: bazasiz, Celery'siz.

NEGA MUHIM: har vazifada `asyncio.run()` chaqirilsa, loop yopiladi va
SQLAlchemy pool'idagi asyncpg ulanishlari o'sha YOPILGAN loop'ga
bog'langan qoladi. Ikkinchi vazifa «attached to a different loop»
xatosiga uchraydi va butun navbat to'xtaydi — buni odam faqat
navbat qotib qolganda payqaydi.

Shuning uchun loop bitta va DOIMIY, `reset_loop()` esa faqat fork'dan
keyin chaqiriladi (meros loop ishlatilmasin).

⚠️ Bu testlar global holatga (`runner._loop`) tegadi, shuning uchun har
biri kirishdagi qiymatni saqlab, chiqishda QAYTARADI.
"""

import asyncio
from collections.abc import Iterator

import pytest

from src.modules.pipeline.application import runner


@pytest.fixture
def toza_loop() -> Iterator[None]:
    """Testni bo'sh holatdan boshlaydi va global holatni tiklaydi."""
    saved = runner._loop
    runner._loop = None
    try:
        yield
    finally:
        created = runner._loop
        if created is not None and created is not saved and not created.is_closed():
            created.close()
        runner._loop = saved
        # `get_loop()` joriy oqim uchun loop o'rnatadi — uni qoldirsak
        # keyingi async test boshqa loop bilan chalkashishi mumkin
        asyncio.set_event_loop(None)


def test_get_loop_har_safar_bir_xil_loopni_qaytaradi(toza_loop) -> None:
    first = runner.get_loop()
    second = runner.get_loop()

    assert first is second
    assert not first.is_closed()


def test_get_loop_joriy_oqimga_loopni_ornatadi(toza_loop) -> None:
    """`asyncio.get_event_loop()` ga tayanadigan kutubxonalar uchun."""
    loop = runner.get_loop()

    assert asyncio.get_event_loop_policy().get_event_loop() is loop


def test_reset_loop_dan_keyin_yangi_loop_beriladi(toza_loop) -> None:
    first = runner.get_loop()

    runner.reset_loop()
    second = runner.get_loop()

    assert second is not first
    assert first.is_closed(), "Eski loop yopilishi kerak — resurs oqmasin"
    assert not second.is_closed()


def test_reset_loop_bosh_holatda_ham_xato_bermaydi(toza_loop) -> None:
    """Fork'dan keyin ikki marta chaqirilishi mumkin."""
    runner.reset_loop()
    runner.reset_loop()

    assert runner.get_loop() is not None


def test_tashqaridan_yopilgan_loop_ornini_yangisi_egallaydi(toza_loop) -> None:
    """Kimdir loop'ni yopib qo'ysa, `get_loop()` yiqilmasligi kerak."""
    first = runner.get_loop()
    first.close()

    second = runner.get_loop()

    assert second is not first
    assert not second.is_closed()


def test_run_async_natijani_qaytaradi_va_loopni_yopmaydi(toza_loop) -> None:
    """`asyncio.run()` dan asosiy farq: loop TIRIK qoladi."""

    async def ish() -> str:
        await asyncio.sleep(0)
        return "tayyor"

    assert runner.run_async(ish()) == "tayyor"

    loop = runner.get_loop()
    assert not loop.is_closed()
    # Ikkinchi «vazifa» — aynan shu joyda eski kod yiqilardi
    assert runner.run_async(ish()) == "tayyor"
    assert runner.get_loop() is loop


def test_run_async_xatoni_ozgartirmasdan_otkazadi(toza_loop) -> None:
    """Quvur xatosi Celery'ga yetib borishi kerak — yutilmasin."""

    async def yiqiladi() -> None:
        raise RuntimeError("stub nosozlik")

    with pytest.raises(RuntimeError, match="stub nosozlik"):
        runner.run_async(yiqiladi())

    # Xatodan keyin ham loop ishlaydi
    assert not runner.get_loop().is_closed()
