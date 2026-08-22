"""`GET /auth/me` → `permissions` ro'yxati rolga mos keladimi.

Frontend menyuni AYNAN shu ro'yxat bo'yicha quradi: ruxsat yo'q bo'lsa
bo'lim ko'rinmaydi. Ya'ni bu maydondagi tasodifiy o'zgarish — savdo
xodimiga menejer bo'limlari ochilib qolishi yoki aksincha, adminning
sozlamalari yo'qolib qolishi demak.

Shuning uchun kutilgan to'plam bu yerda QO'LDA yozilgan — kod bilan bir
xil formuladan hisoblanmagan. Aks holda test kodni takrorlagan bo'lardi
va hech qanday xatoni ushlay olmasdi.
"""

from __future__ import annotations

import httpx
import pytest

from src.conftest import API
from src.modules.users.domain.entities import Role

# ── Kutilgan ruxsatlar (dinamik sozlamalar O'CHIRILGAN holatda) ──

ADMIN_KUTILGAN = {
    "users:read", "users:write",
    "agents:read", "agents:write", "agents:sync",
    "clients:read", "clients:write",
    "calls:read",
    "groups:read", "groups:write",
    "regions:read", "regions:write",
    "scores:read", "scores:write",
    "surveys:read", "surveys:write",
    "analytics:read", "analytics:read_all",
    "rubric:read", "rubric:write",
    "settings:read", "settings:write",
    "sales:read", "sales:review", "sales:import",
}

MANAGER_KUTILGAN = {
    "agents:read",
    "clients:read",
    "calls:read",
    "groups:read",
    "regions:read",
    "scores:read", "scores:write",
    "surveys:read",
    "analytics:read", "analytics:read_all",
    "rubric:read",
    "settings:read",
    "sales:read", "sales:review", "sales:import",
}

SALES_KUTILGAN = {
    "calls:read:own",
    "scores:read:own",
    "analytics:read:own",
    "regions:read",
}

VIEWER_KUTILGAN = {
    "analytics:read",
    "regions:read",
}


async def _kirish(client: httpx.AsyncClient, email: str, password: str) -> None:
    login = await client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


@pytest.mark.asyncio
async def test_admin_ruxsatlari(
    admin_client: httpx.AsyncClient, settings_guard
) -> None:
    """Adminga dinamik sozlamalar ta'sir qilmaydi — unda hammasi bor."""
    await settings_guard("access.manager_manages_agents", False)
    await settings_guard("access.sales_client_rating", "hidden")

    body = (await admin_client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == ADMIN_KUTILGAN


@pytest.mark.asyncio
async def test_manager_ruxsatlari_qoshimchasiz(
    anon_client: httpx.AsyncClient, make_user, settings_guard
) -> None:
    """`access.manager_manages_agents` o'chiq — bazaviy to'plam."""
    await settings_guard("access.manager_manages_agents", False)
    user = await make_user(role=Role.MANAGER)
    await _kirish(anon_client, user.email, user.password)

    body = (await anon_client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == MANAGER_KUTILGAN
    assert "users:write" not in body["permissions"], "menejer hisob yarata olmaydi"
    assert "settings:write" not in body["permissions"]


@pytest.mark.asyncio
async def test_manager_xodim_boshqarish_yoqilganda(
    anon_client: httpx.AsyncClient, make_user, settings_guard
) -> None:
    """Sozlama yoqilsa aynan 4 ta ruxsat qo'shiladi, boshqasi emas."""
    await settings_guard("access.manager_manages_agents", True)
    user = await make_user(role=Role.MANAGER)
    await _kirish(anon_client, user.email, user.password)

    body = (await anon_client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == MANAGER_KUTILGAN | {
        "agents:write",
        "agents:sync",
        "groups:write",
        "regions:write",
    }
    # Foydalanuvchi hisoblari va sozlamalar baribir faqat adminda
    assert "users:write" not in body["permissions"]
    assert "settings:write" not in body["permissions"]


@pytest.mark.asyncio
async def test_viewer_ruxsatlari(
    anon_client: httpx.AsyncClient, make_user, settings_guard
) -> None:
    """Kuzatuvchi — savdo xonasidagi monitor. Faqat ko'radi."""
    await settings_guard("access.manager_manages_agents", True)
    await settings_guard("access.sales_client_rating", "full")

    user = await make_user(role=Role.VIEWER)
    await _kirish(anon_client, user.email, user.password)

    body = (await anon_client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == VIEWER_KUTILGAN, (
        "kuzatuvchiga boshqa rollarning dinamik ruxsatlari yopishmasligi kerak"
    )


@pytest.mark.asyncio
async def test_sales_ruxsatlari_reyting_yopiq(sales_client, settings_guard) -> None:
    """Client bahosi yopilgan — so'rovnoma ruxsati umuman berilmaydi."""
    await settings_guard("access.sales_client_rating", "hidden")
    client, _ = sales_client

    body = (await client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == SALES_KUTILGAN
    assert not any(p.startswith("surveys") for p in body["permissions"])


@pytest.mark.asyncio
async def test_sales_ruxsatlari_faqat_ball(sales_client, settings_guard) -> None:
    """`score_only` — o'rtacha ball ko'rinadi, client izohlari yo'q."""
    await settings_guard("access.sales_client_rating", "score_only")
    client, _ = sales_client

    body = (await client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == SALES_KUTILGAN | {"surveys:read:own"}
    assert "surveys:read:own:comments" not in body["permissions"]


@pytest.mark.asyncio
async def test_sales_ruxsatlari_ball_va_izohlar(sales_client, settings_guard) -> None:
    """`full` — ball ustiga anonim izohlar ham qo'shiladi."""
    await settings_guard("access.sales_client_rating", "full")
    client, _ = sales_client

    body = (await client.get(f"{API}/auth/me")).json()
    assert set(body["permissions"]) == SALES_KUTILGAN | {
        "surveys:read:own",
        "surveys:read:own:comments",
    }


@pytest.mark.asyncio
async def test_sales_hech_qachon_boshqalarning_malumotini_kormaydi(
    sales_client, settings_guard
) -> None:
    """Sozlama qanday bo'lmasin — savdo xodimida `read_all` paydo bo'lmaydi."""
    for qiymat in ("hidden", "score_only", "full"):
        await settings_guard("access.sales_client_rating", qiymat)
        await settings_guard("access.manager_manages_agents", True)
        client, _ = sales_client

        ruxsatlar = set((await client.get(f"{API}/auth/me")).json()["permissions"])
        assert "analytics:read_all" not in ruxsatlar
        assert "users:read" not in ruxsatlar
        assert "settings:read" not in ruxsatlar
        assert "agents:write" not in ruxsatlar


@pytest.mark.asyncio
async def test_ruxsatlar_royxati_saralangan_va_takrorlanmaydi(
    admin_client: httpx.AsyncClient,
) -> None:
    """Router `sorted()` qaytaradi — frontend taqqoslashi barqaror bo'lsin."""
    ruxsatlar = (await admin_client.get(f"{API}/auth/me")).json()["permissions"]

    assert ruxsatlar == sorted(ruxsatlar)
    assert len(ruxsatlar) == len(set(ruxsatlar))
