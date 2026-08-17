"""`RubricService` — faol rubrika bittaligi va saqlash qoidalari.

⚠️ IZOLYATSIYA
  Rubrika — BUTUN tizim uchun bitta umumiy yozuv: uni almashtirish
  keyingi baholarni ham, dashboard'ni ham o'zgartiradi. Shuning uchun
  yozuvga tegadigan testlar TRANZAKSIYA ichida ishlaydi va
  `rollback()` bilan tugaydi — bazada hech qanday iz qolmaydi.

  Validatsiya qoidalari esa `RubricService._validate` — sof funksiya,
  unga baza umuman kerak emas.
"""

import pytest
from sqlalchemy import func, select, text

from src.core.database import SessionFactory
from src.core.exceptions import ValidationError
from src.modules.scoring.application.rubric_service import RubricService
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC
from src.modules.scoring.infrastructure.rubric_models import RubricModel

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]


def _blocks(**maxes: int) -> list[dict]:
    """Berilgan maksimumlar bilan soddalashtirilgan bloklar ro'yxati.

    Har blokda bitta kriteriya — uning `points` i blok maksimumiga teng,
    ya'ni «kriteriyalar yig'indisi» qoidasi bajarilgan holat.
    """
    return [
        {
            "key": key,
            "label": key,
            "max": value,
            "criteria": [{"id": f"{key}-1", "label": key, "points": value}],
        }
        for key, value in maxes.items()
    ]


# ══════════════════════════════════════════════════════════════
#  9a. Validatsiya — bazasiz
# ══════════════════════════════════════════════════════════════


def test_standart_rubrika_qoidalardan_otadi() -> None:
    """Kodda kelgan rubrika o'z tekshiruvini yiqitmasligi shart."""
    RubricService._validate(BLOCKS, FLAGS)


def test_bloklar_yigindisi_100_bolmasa_rad_etiladi() -> None:
    """90 ball — «85 ball oldi» degan gap ma'nosini yo'qotadi."""
    with pytest.raises(ValidationError) as exc:
        RubricService._validate(
            _blocks(script=25, communication=25, resolution=25, sales_skill=15),
            FLAGS,
        )

    assert "90" in exc.value.message
    assert "100" in exc.value.message


def test_bloklar_yigindisi_100_dan_oshsa_ham_rad_etiladi() -> None:
    with pytest.raises(ValidationError) as exc:
        RubricService._validate(_blocks(a=60, b=60), FLAGS)

    assert "120" in exc.value.message


def test_kriteriyalar_yigindisi_blok_maksimumiga_teng_bolishi_kerak() -> None:
    blocks = _blocks(a=50, b=50)
    blocks[0]["criteria"][0]["points"] = 40  # 50 emas

    with pytest.raises(ValidationError) as exc:
        RubricService._validate(blocks, FLAGS)

    assert "40" in exc.value.message


def test_kriteriyasiz_blok_rad_etiladi() -> None:
    """Kriteriyasiz blokda ballni dalil bilan asoslab bo'lmaydi."""
    blocks = _blocks(a=100)
    blocks[0]["criteria"] = []

    with pytest.raises(ValidationError) as exc:
        RubricService._validate(blocks, FLAGS)

    assert "kriteriya" in exc.value.message


def test_bosh_rubrika_rad_etiladi() -> None:
    with pytest.raises(ValidationError):
        RubricService._validate([], FLAGS)


def test_musbat_jarima_rad_etiladi() -> None:
    """«+10» jarima ballni KO'TARARDI — qoidabuzarlik uchun mukofot."""
    with pytest.raises(ValidationError) as exc:
        RubricService._validate(
            _blocks(a=100),
            [{"type": "shouting", "label": "Baqirish", "penalty": 10}],
        )

    assert "manfiy" in exc.value.message


def test_nol_jarima_ruxsat_etiladi() -> None:
    """0 — «qayd et, lekin ball ayirma». Bu haqiqiy stsenariy."""
    RubricService._validate(
        _blocks(a=100),
        [{"type": "note", "label": "Eslatma", "penalty": 0}],
    )


# ══════════════════════════════════════════════════════════════
#  9b. Faol rubrika bittaligi — tranzaksiya ichida, izsiz
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bazada_aynan_bitta_faol_rubrika_bor() -> None:
    async with SessionFactory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(RubricModel)
                .where(RubricModel.is_active.is_(True))
            )
        ).scalar_one()

    assert count == 1, (
        f"{count} ta faol rubrika topildi — `get_active()` ning "
        "`scalar_one_or_none()` si bunda 500 beradi"
    )


@pytest.mark.asyncio
async def test_get_active_faol_rubrikani_qaytaradi() -> None:
    async with SessionFactory() as session:
        rubric = await RubricService(session).get_active()

        assert rubric.is_active is True
        assert rubric.blocks, "Faol rubrikada bloklar bo'lishi kerak"

        # Hech narsa yozilmagan bo'lsa ham — kafolat uchun
        await session.rollback()


@pytest.mark.asyncio
async def test_yangi_versiya_saqlansa_eskisi_faolsizlanadi() -> None:
    """⚠️ Yozuv TRANZAKSIYA ichida — oxirida `rollback()`, iz qolmaydi."""
    async with SessionFactory() as session:
        try:
            previous = await RubricService(session).get_active()
            previous_id = previous.id
            previous_version = previous.version

            created = await RubricService(session).create_version(
                blocks=BLOCKS,
                red_flags=FLAGS,
                name="pytest — vaqtinchalik versiya",
            )

            assert created.version == previous_version + 1
            assert created.is_active is True

            # Eskisi o'chirilmaydi (unga bog'langan baholar qoladi),
            # lekin FAOL bo'lmaydi
            await session.refresh(previous)
            assert previous.is_active is False

            active = (
                await session.execute(
                    select(RubricModel.id).where(RubricModel.is_active.is_(True))
                )
            ).scalars().all()
            assert active == [created.id]
            assert previous_id not in active
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_notogri_rubrika_saqlanmaydi() -> None:
    """Validatsiya YOZUVDAN OLDIN — buzuq versiya bazaga tushmasin."""
    async with SessionFactory() as session:
        try:
            with pytest.raises(ValidationError):
                await RubricService(session).create_version(
                    blocks=_blocks(a=50), red_flags=FLAGS
                )

            # Faol rubrika tegilmagan
            still_active = (
                await session.execute(
                    select(func.count())
                    .select_from(RubricModel)
                    .where(RubricModel.is_active.is_(True))
                )
            ).scalar_one()
            assert still_active == 1
        finally:
            await session.rollback()


# ══════════════════════════════════════════════════════════════
#  10. Auditda topilgan xato — faollik cheklovsiz
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_faol_rubrika_indeksi_unikal() -> None:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'rubrics'"
                )
            )
        ).all()

    covering = [
        definition
        for _name, definition in rows
        if "is_active" in definition
    ]
    assert covering, "`is_active` ustida umuman indeks yo'q"
    assert any("UNIQUE" in definition for definition in covering), (
        "Faollikni bazaning o'zi kafolatlashi kerak: "
        f"topilgani — {covering}"
    )
