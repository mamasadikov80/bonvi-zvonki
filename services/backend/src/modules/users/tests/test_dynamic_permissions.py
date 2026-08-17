"""Dinamik ruxsatlar — sozlama → `SettingsService` → `resolve_permissions`.

`test_permissions_matrix.py` `resolve_permissions()` ni lug'at berib
chaqiradi. Bu yerda esa ZANJIRNING O'ZI tekshiriladi: admin sozlamalar
sahifasida bayroqni bosgan paytda haqiqatan ruxsat paydo bo'ladimi.

Zanjirning har bo'g'ini alohida ishlashi mumkin, lekin ular orasida
kalit nomi bitta harfga farq qilsa — sozlama saqlanadi, hech narsa
o'zgarmaydi va buni hech kim sezmaydi.

Sozlamalar dev bazasida umumiy, shuning uchun har o'zgartirish
`settings_guard` orqali — test oxirida eski qiymat qaytariladi.
"""

from __future__ import annotations

import pytest

from src.core.database import SessionFactory
from src.modules.settings.application.services import SettingsService
from src.modules.users.domain.entities import (
    ROLE_PERMISSIONS,
    Role,
    resolve_permissions,
)


async def _ruxsatlar(role: Role) -> set[str]:
    """Sozlamalarni bazadan haqiqiy o'qib, rol ruxsatlarini hisoblaydi."""
    async with SessionFactory() as session:
        access = await SettingsService(session).access_values()
    return resolve_permissions(role, access)


# ══════════════════════════════════════════════════════════════
#  `access.*` sozlamalari umuman o'qilyaptimi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_access_values_faqat_access_kalitlarini_qaytaradi() -> None:
    async with SessionFactory() as session:
        access = await SettingsService(session).access_values()

    assert access, "`access.*` sozlamalari umuman topilmadi"
    assert all(k.startswith("access.") for k in access)
    assert set(access) == {
        "access.sales_client_rating",
        "access.manager_manages_agents",
    }


# ══════════════════════════════════════════════════════════════
#  Menejer — xodimlarni boshqarish
# ══════════════════════════════════════════════════════════════

MANAGER_QOSHIMCHA = {"agents:write", "agents:sync", "groups:write", "regions:write"}


@pytest.mark.asyncio
async def test_menejer_bayrogi_yoqilganda_ruxsat_paydo_boladi(settings_guard) -> None:
    await settings_guard("access.manager_manages_agents", True)

    ruxsatlar = await _ruxsatlar(Role.MANAGER)
    assert MANAGER_QOSHIMCHA <= ruxsatlar
    assert ruxsatlar == ROLE_PERMISSIONS[Role.MANAGER] | MANAGER_QOSHIMCHA


@pytest.mark.asyncio
async def test_menejer_bayrogi_ochirilganda_ruxsat_yoqoladi(settings_guard) -> None:
    await settings_guard("access.manager_manages_agents", False)

    ruxsatlar = await _ruxsatlar(Role.MANAGER)
    assert not (MANAGER_QOSHIMCHA & ruxsatlar)
    assert ruxsatlar == ROLE_PERMISSIONS[Role.MANAGER]


@pytest.mark.asyncio
async def test_menejer_bayrogi_ikki_tomonga_ham_ishlaydi(settings_guard) -> None:
    """Yoqib-o'chirib ko'ramiz — qiymat kesh'da qotib qolmasligi kerak.

    Sozlama har so'rovda bazadan o'qiladi. Kesh qo'shilib qolsa,
    admin bayroqni o'chirgandan keyin ham menejerda huquq qolardi.
    """
    await settings_guard("access.manager_manages_agents", False)
    assert not (MANAGER_QOSHIMCHA & await _ruxsatlar(Role.MANAGER))

    await settings_guard("access.manager_manages_agents", True)
    assert MANAGER_QOSHIMCHA <= await _ruxsatlar(Role.MANAGER)

    await settings_guard("access.manager_manages_agents", False)
    assert not (MANAGER_QOSHIMCHA & await _ruxsatlar(Role.MANAGER))


@pytest.mark.asyncio
async def test_menejer_bayrogi_boshqa_rollarga_tegmaydi(settings_guard) -> None:
    await settings_guard("access.manager_manages_agents", True)

    assert await _ruxsatlar(Role.ADMIN) == ROLE_PERMISSIONS[Role.ADMIN]
    assert await _ruxsatlar(Role.VIEWER) == ROLE_PERMISSIONS[Role.VIEWER]
    assert not (MANAGER_QOSHIMCHA & await _ruxsatlar(Role.SALES))


# ══════════════════════════════════════════════════════════════
#  Savdo xodimi — client bahosi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_client_bahosi_yopilganda_sorovnoma_ruxsati_yoq(
    settings_guard,
) -> None:
    await settings_guard("access.sales_client_rating", "hidden")

    ruxsatlar = await _ruxsatlar(Role.SALES)
    assert not any(p.startswith("surveys:") for p in ruxsatlar)
    assert ruxsatlar == ROLE_PERMISSIONS[Role.SALES]


@pytest.mark.asyncio
async def test_client_bahosi_faqat_ball_holatida(settings_guard) -> None:
    await settings_guard("access.sales_client_rating", "score_only")

    ruxsatlar = await _ruxsatlar(Role.SALES)
    assert "surveys:read:own" in ruxsatlar
    assert "surveys:read:own:comments" not in ruxsatlar, (
        "`score_only` da izohlar ochilib ketmasligi kerak"
    )


@pytest.mark.asyncio
async def test_client_bahosi_toliq_holatida_izohlar_ham_ochiladi(
    settings_guard,
) -> None:
    await settings_guard("access.sales_client_rating", "full")

    ruxsatlar = await _ruxsatlar(Role.SALES)
    assert {"surveys:read:own", "surveys:read:own:comments"} <= ruxsatlar


@pytest.mark.asyncio
async def test_client_bahosiga_axlat_yozilsa_ruxsat_berilmaydi(
    settings_guard,
) -> None:
    """Noma'lum qiymat — eng yopiq holat (fail-closed).

    Bazaga qo'lda yoki eski migratsiya orqali tanish bo'lmagan qiymat
    tushib qolsa, tizim «ochib qo'yish» tomonga emas, «yopib qo'yish»
    tomonga og'ishi kerak.
    """
    await settings_guard("access.sales_client_rating", "hammasi-ochiq")

    ruxsatlar = await _ruxsatlar(Role.SALES)
    assert not any(p.startswith("surveys:") for p in ruxsatlar)


@pytest.mark.asyncio
async def test_client_bahosi_sozlamasi_boshqa_rollarga_tegmaydi(
    settings_guard,
) -> None:
    await settings_guard("access.sales_client_rating", "full")

    assert await _ruxsatlar(Role.ADMIN) == ROLE_PERMISSIONS[Role.ADMIN]
    assert await _ruxsatlar(Role.MANAGER) >= ROLE_PERMISSIONS[Role.MANAGER]
    assert await _ruxsatlar(Role.VIEWER) == ROLE_PERMISSIONS[Role.VIEWER]


# ══════════════════════════════════════════════════════════════
#  Sozlama yozilgani bilan hisob chegarasi ochilmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ikkala_bayroq_ham_ochiq_bolsa_ham_admin_huquqi_berilmaydi(
    settings_guard,
) -> None:
    """Sozlamalar orqali admin bo'lib olishning yo'li YO'Q."""
    await settings_guard("access.manager_manages_agents", True)
    await settings_guard("access.sales_client_rating", "full")

    for role in (Role.MANAGER, Role.SALES, Role.VIEWER):
        ruxsatlar = await _ruxsatlar(role)
        assert "users:write" not in ruxsatlar, role.value
        assert "users:read" not in ruxsatlar, role.value
        assert "settings:write" not in ruxsatlar, role.value
        assert "rubric:write" not in ruxsatlar, role.value
