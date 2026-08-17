"""Hisob yaratish va tahrirlash — `POST /users`, `PATCH /users/{id}`.

Bu endpointlar faqat adminda. Ular orqali tizimga kirish huquqi
beriladi, shuning uchun har bir tekshiruv muhim:

  • email takrorlanmasin — aks holda ikkinchi hisob birinchisining
    parolini «bosib» ololmasa ham, kirish oqimi noaniq bo'lib qoladi;
  • parol kalta bo'lmasin;
  • SALES roli albatta savdo xodimiga bog'lansin — bog'lanmasa
    foydalanuvchi kiradi-yu, hech qanday ma'lumot ko'rmaydi;
  • admin o'zini o'chirib yoki roli tushirib yubormasin — tizimda
    umuman admin qolmasligi mumkin.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from src.conftest import API
from src.core.database import SessionFactory
from src.core.security import verify_password
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel

PAROL = "yetarlicha-uzun-parol-1"


async def _yaratish(
    client: httpx.AsyncClient, email: str, **qoshimcha
) -> httpx.Response:
    tana = {
        "email": email,
        "password": PAROL,
        "full_name": "Pytest Foydalanuvchi",
        "role": Role.VIEWER.value,
    }
    tana.update(qoshimcha)
    return await client.post(f"{API}/users", json=tana)


# ══════════════════════════════════════════════════════════════
#  Yaratish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hisob_yaratiladi_va_royxatda_korinadi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    email = yangi_email()
    response = await _yaratish(admin_client, email)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == email
    assert body["role"] == Role.VIEWER.value
    assert body["is_active"] is True
    assert body["agent_id"] is None
    assert "password" not in response.text
    assert "$2b$" not in response.text, "parol xeshi javobga tushib qolgan"

    royxat = (await admin_client.get(f"{API}/users")).json()
    assert email in [u["email"] for u in royxat]


@pytest.mark.asyncio
async def test_yaratilgan_hisob_darhol_kira_oladi(
    admin_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, yangi_email
) -> None:
    """Uchdan-uchgacha: admin hisob ochdi → odam kirdi."""
    email = yangi_email()
    assert (await _yaratish(admin_client, email)).status_code == 201

    login = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": PAROL}
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_email_kichik_harfga_keltiriladi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    """Katta harf bilan kiritilgan email baribir bir xil hisobga tushadi."""
    email = yangi_email()
    response = await _yaratish(admin_client, email.upper())

    assert response.status_code == 201, response.text
    assert response.json()["email"] == email.lower()


@pytest.mark.asyncio
async def test_takrorlangan_email_409_beradi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    email = yangi_email()
    assert (await _yaratish(admin_client, email)).status_code == 201

    ikkinchi = await _yaratish(admin_client, email)
    assert ikkinchi.status_code == 409, ikkinchi.text
    assert ikkinchi.json()["error"]["code"] == "conflict"


@pytest.mark.asyncio
async def test_takrorlangan_email_registrdan_qatiy_nazar_ushlanadi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    """`Ali@x.uz` va `ali@x.uz` — bitta odam, ikkita hisob bo'lmasin."""
    email = yangi_email()
    assert (await _yaratish(admin_client, email.lower())).status_code == 201

    ikkinchi = await _yaratish(admin_client, email.upper())
    assert ikkinchi.status_code == 409, ikkinchi.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parol",
    [
        pytest.param("", id="bosh"),
        pytest.param("kalta", id="5-belgi"),
        pytest.param("1234567", id="7-belgi-chegaradan-bitta-kam"),
    ],
)
async def test_kalta_parol_rad_etiladi(
    admin_client: httpx.AsyncClient, yangi_email, parol: str
) -> None:
    """Minimal uzunlik — 8 belgi (`CreateUserRequest.password`)."""
    response = await _yaratish(admin_client, yangi_email(), password=parol)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_chegaradagi_parol_qabul_qilinadi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    """Aynan 8 belgi — o'tishi kerak (chegara `>=`)."""
    response = await _yaratish(admin_client, yangi_email(), password="12345678")
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_notogri_email_va_rol_rad_etiladi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    assert (await _yaratish(admin_client, "email-emas")).status_code == 422
    assert (
        await _yaratish(admin_client, yangi_email(), role="bosh_direktor")
    ).status_code == 422


@pytest.mark.asyncio
async def test_juda_kalta_ism_rad_etiladi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    response = await _yaratish(admin_client, yangi_email(), full_name="A")
    assert response.status_code == 422, response.text


# ══════════════════════════════════════════════════════════════
#  `agent_id` bog'lanishi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_savdo_xodimi_roli_agentsiz_yaratilmaydi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    """Bog'lanmagan SALES kiradi-yu, hech qanday ma'lumot ko'rmaydi."""
    response = await _yaratish(
        admin_client, yangi_email(), role=Role.SALES.value, agent_id=None
    )
    assert response.status_code == 422, response.text
    assert "xodim" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_savdo_xodimi_roli_agent_bilan_yaratiladi(
    admin_client: httpx.AsyncClient, yangi_email, dataset
) -> None:
    data = await dataset(scores=[75])
    response = await _yaratish(
        admin_client,
        yangi_email(),
        role=Role.SALES.value,
        agent_id=str(data.agent_id),
    )

    assert response.status_code == 201, response.text
    assert response.json()["agent_id"] == str(data.agent_id)


@pytest.mark.asyncio
async def test_mavjud_bolmagan_agentga_boglash_404(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    response = await _yaratish(
        admin_client,
        yangi_email(),
        role=Role.SALES.value,
        agent_id=str(uuid.uuid4()),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_royxatda_agent_nomi_ham_qaytadi(
    admin_client: httpx.AsyncClient, yangi_email, dataset
) -> None:
    """`GET /users` xodim nomini join bilan olib keladi — UI shuni ko'rsatadi."""
    data = await dataset(scores=[60])
    email = yangi_email()
    assert (
        await _yaratish(
            admin_client, email, role=Role.SALES.value, agent_id=str(data.agent_id)
        )
    ).status_code == 201

    royxat = (await admin_client.get(f"{API}/users")).json()
    qator = next(u for u in royxat if u["email"] == email)
    assert qator["agent_name"] == data.agent_name


# ══════════════════════════════════════════════════════════════
#  Tahrirlash
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rolni_ozgartirish(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    email = yangi_email()
    user_id = (await _yaratish(admin_client, email)).json()["id"]

    response = await admin_client.patch(
        f"{API}/users/{user_id}", json={"role": Role.MANAGER.value}
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == Role.MANAGER.value


@pytest.mark.asyncio
async def test_rol_ozgargach_ruxsatlar_ham_ozgaradi(
    admin_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, yangi_email
) -> None:
    """Rol yangilangach foydalanuvchi keyingi kirishda yangi menyuni ko'radi."""
    email = yangi_email()
    user_id = (await _yaratish(admin_client, email)).json()["id"]

    login = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": PAROL}
    )
    anon_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    oldin = set((await anon_client.get(f"{API}/auth/me")).json()["permissions"])
    assert "calls:read" not in oldin

    await admin_client.patch(
        f"{API}/users/{user_id}", json={"role": Role.MANAGER.value}
    )

    keyin = set((await anon_client.get(f"{API}/auth/me")).json()["permissions"])
    assert "calls:read" in keyin
    assert "analytics:read_all" in keyin


@pytest.mark.asyncio
async def test_agentga_boglash_va_uzish(
    admin_client: httpx.AsyncClient, yangi_email, dataset
) -> None:
    data = await dataset(scores=[90])
    user_id = (await _yaratish(admin_client, yangi_email())).json()["id"]

    boglash = await admin_client.patch(
        f"{API}/users/{user_id}",
        json={"role": Role.SALES.value, "agent_id": str(data.agent_id)},
    )
    assert boglash.status_code == 200, boglash.text
    assert boglash.json()["agent_id"] == str(data.agent_id)

    # SALES bo'lib turib bog'lanishni uzib bo'lmaydi
    uzish = await admin_client.patch(f"{API}/users/{user_id}", json={"agent_id": None})
    assert uzish.status_code == 422, uzish.text

    # Avval rol o'zgaradi — keyin bog'lanish keraksiz bo'lib qoladi
    rolni_qaytarish = await admin_client.patch(
        f"{API}/users/{user_id}", json={"role": Role.VIEWER.value, "agent_id": None}
    )
    assert rolni_qaytarish.status_code == 200, rolni_qaytarish.text
    assert rolni_qaytarish.json()["agent_id"] is None


@pytest.mark.asyncio
async def test_hisobni_ochirish_va_qayta_yoqish(
    admin_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, yangi_email
) -> None:
    email = yangi_email()
    user_id = (await _yaratish(admin_client, email)).json()["id"]

    ochirish = await admin_client.patch(
        f"{API}/users/{user_id}", json={"is_active": False}
    )
    assert ochirish.status_code == 200, ochirish.text
    assert ochirish.json()["is_active"] is False

    kirish = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": PAROL}
    )
    assert kirish.status_code == 401

    await admin_client.patch(f"{API}/users/{user_id}", json={"is_active": True})
    assert (
        await anon_client.post(
            f"{API}/auth/login", json={"email": email, "password": PAROL}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_parolni_almashtirish(
    admin_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, yangi_email
) -> None:
    """Yangi parol ishlaydi, eskisi ishlamaydi, bazada xesh yangilanadi."""
    email = yangi_email()
    user_id = (await _yaratish(admin_client, email)).json()["id"]
    yangi_parol = "butunlay-yangi-parol-9"

    response = await admin_client.patch(
        f"{API}/users/{user_id}", json={"password": yangi_parol}
    )
    assert response.status_code == 200, response.text

    assert (
        await anon_client.post(
            f"{API}/auth/login", json={"email": email, "password": PAROL}
        )
    ).status_code == 401
    assert (
        await anon_client.post(
            f"{API}/auth/login", json={"email": email, "password": yangi_parol}
        )
    ).status_code == 200

    async with SessionFactory() as session:
        row = (
            await session.execute(select(UserModel).where(UserModel.email == email))
        ).scalar_one()
    assert yangi_parol not in row.password_hash
    assert verify_password(yangi_parol, row.password_hash)


@pytest.mark.asyncio
async def test_kalta_yangi_parol_rad_etiladi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    user_id = (await _yaratish(admin_client, yangi_email())).json()["id"]

    response = await admin_client.patch(
        f"{API}/users/{user_id}", json={"password": "kalta"}
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_yoq_foydalanuvchini_tahrirlash_404(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.patch(
        f"{API}/users/{uuid.uuid4()}", json={"full_name": "Yo'q odam"}
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_faqat_yuborilgan_maydonlar_ozgaradi(
    admin_client: httpx.AsyncClient, yangi_email
) -> None:
    """`exclude_unset` — yuborilmagan maydon eskisicha qoladi."""
    email = yangi_email()
    yaratilgan = (await _yaratish(admin_client, email)).json()

    response = await admin_client.patch(
        f"{API}/users/{yaratilgan['id']}", json={"full_name": "Yangi Ism"}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["full_name"] == "Yangi Ism"
    assert body["role"] == yaratilgan["role"]
    assert body["is_active"] is True
    assert body["email"] == email


# ══════════════════════════════════════════════════════════════
#  Admin o'zini himoyalash
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_admin_ozini_ochira_olmaydi(admin_client: httpx.AsyncClient) -> None:
    """Aks holda tizimda umuman admin qolmasligi mumkin."""
    ozi = (await admin_client.get(f"{API}/auth/me")).json()["id"]

    response = await admin_client.patch(
        f"{API}/users/{ozi}", json={"is_active": False}
    )
    assert response.status_code == 422, response.text

    # Hisob haqiqatan tegilmagan
    assert (await admin_client.get(f"{API}/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_admin_oz_rolini_tushira_olmaydi(
    admin_client: httpx.AsyncClient,
) -> None:
    ozi = (await admin_client.get(f"{API}/auth/me")).json()["id"]

    response = await admin_client.patch(
        f"{API}/users/{ozi}", json={"role": Role.VIEWER.value}
    )
    assert response.status_code == 422, response.text
    assert (await admin_client.get(f"{API}/auth/me")).json()["role"] == Role.ADMIN.value


@pytest.mark.asyncio
async def test_admin_oz_ismini_ozgartira_oladi(
    admin_client: httpx.AsyncClient,
) -> None:
    """Himoya faqat rol va faollikka tegishli — qolganini o'zgartirsa bo'ladi."""
    ozi = (await admin_client.get(f"{API}/auth/me")).json()
    eski_ism = ozi["full_name"]

    try:
        response = await admin_client.patch(
            f"{API}/users/{ozi['id']}", json={"full_name": "Pytest vaqtincha"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["full_name"] == "Pytest vaqtincha"
    finally:
        # Dev bazadagi haqiqiy yozuv — eski holatiga qaytariladi
        await admin_client.patch(
            f"{API}/users/{ozi['id']}", json={"full_name": eski_ism}
        )
