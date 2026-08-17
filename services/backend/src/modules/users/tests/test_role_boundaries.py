"""ROL CHEGARALARI — API darajasida.

`test_permissions_matrix.py` matritsaning O'ZINI tekshiradi. Bu yerda
esa matritsa haqiqatan HTTP qatlamiga ulanganmi degan savolga javob
beriladi: router `Depends` ni unutib qo'ysa yoki noto'g'ri ruxsat nomi
yozilsa, matritsa joyida turadi-yu, eshik ochiq qoladi.

Kutilgan kodlar:
    401 — kim ekaning noma'lum (token yo'q / yaroqsiz)
    403 — kimliging ma'lum, lekin bu yerga ruxsating yo'q
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from src.conftest import API
from src.modules.users.domain.entities import Role

# Savdo xodimi UMUMAN kira olmaydigan manzillar
YOPIQ_GET = [
    f"{API}/users",
    f"{API}/settings",
    f"{API}/settings/health",
    f"{API}/settings/ai/providers",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("manzil", YOPIQ_GET, ids=lambda m: m.rsplit("/v1", 1)[-1])
async def test_savdo_xodimi_admin_bolimlariga_kira_olmaydi(
    sales_client, manzil: str
) -> None:
    client, _ = sales_client
    response = await client.get(manzil)

    assert response.status_code == 403, f"{manzil} → {response.status_code}: {response.text}"
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_savdo_xodimi_hisob_yarata_olmaydi(sales_client) -> None:
    """So'rov tanasi TO'G'RI — ya'ni 422 emas, aynan 403 kutilyapti."""
    client, _ = sales_client
    response = await client.post(
        f"{API}/users",
        json={
            "email": f"pytest-{uuid.uuid4().hex[:8]}@zvonki.uz",
            "password": "yetarlicha-uzun-parol",
            "full_name": "O'zimni ko'tarish",
            "role": Role.ADMIN.value,
        },
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_savdo_xodimi_ozini_admin_qila_olmaydi(sales_client) -> None:
    """Eng xavfli stsenariy — o'z hisobiga PATCH bilan admin roli."""
    client, _ = sales_client
    ozi = (await client.get(f"{API}/auth/me")).json()["id"]

    response = await client.patch(
        f"{API}/users/{ozi}", json={"role": Role.ADMIN.value}
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_savdo_xodimi_sozlamalarni_yoza_olmaydi(sales_client) -> None:
    client, _ = sales_client
    response = await client.put(
        f"{API}/settings", json={"values": {"survey.enabled": True}}
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_kuzatuvchi_ham_admin_bolimlariga_kira_olmaydi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """VIEWER — monitor rejimi, unda `settings:read` ham yo'q."""
    user = await make_user(role=Role.VIEWER)
    login = await anon_client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    anon_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    assert (await anon_client.get(f"{API}/users")).status_code == 403
    assert (await anon_client.get(f"{API}/settings")).status_code == 403


@pytest.mark.asyncio
async def test_menejer_sozlamalarni_koradi_lekin_yozmaydi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Menejerda `settings:read` bor, `settings:write` yo'q."""
    user = await make_user(role=Role.MANAGER)
    login = await anon_client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    anon_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    assert (await anon_client.get(f"{API}/settings")).status_code == 200
    assert (await anon_client.get(f"{API}/users")).status_code == 403

    yozish = await anon_client.put(
        f"{API}/settings", json={"values": {"survey.period_days": 14}}
    )
    assert yozish.status_code == 403, yozish.text


@pytest.mark.asyncio
async def test_admin_hamma_yerga_kiradi(admin_client: httpx.AsyncClient) -> None:
    for manzil in YOPIQ_GET:
        response = await admin_client.get(manzil)
        assert response.status_code == 200, f"{manzil} → {response.text}"


@pytest.mark.asyncio
async def test_tokensiz_403_emas_401_qaytadi(anon_client: httpx.AsyncClient) -> None:
    """Farq muhim: 401 — «kim ekaningni ayt», 403 — «sen bo'lmaysan».

    Frontend 401 da login sahifasiga otadi, 403 da esa xato ko'rsatadi.
    Aralashib ketsa foydalanuvchi cheksiz aylanib qolardi.
    """
    for manzil in YOPIQ_GET:
        response = await anon_client.get(manzil)
        assert response.status_code == 401, f"{manzil} → {response.status_code}"
        assert response.json()["error"]["code"] == "unauthorized"
