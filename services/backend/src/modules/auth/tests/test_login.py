"""`POST /auth/login` va `GET /auth/me` — kirish oqimi.

Nima tekshiriladi:
  • to'g'ri ma'lumot bilan token beriladi va u haqiqatan ishlaydi;
  • xato ma'lumot bilan javob HECH QANDAY ma'lumot oshkor qilmaydi —
    «bunday email yo'q» bilan «parol xato» ni ajratib bo'lmasligi kerak,
    aks holda kimningdir hisobi bor-yo'qligini tashqaridan bilib olish
    mumkin bo'lardi (foydalanuvchi ro'yxatini yig'ish hujumi);
  • himoyalangan endpointga tokensiz yoki buzilgan token bilan kirib
    bo'lmaydi.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/auth -q
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from src.conftest import ADMIN, API
from src.core.security import create_access_token, create_refresh_token
from src.modules.users.domain.entities import Role

# ══════════════════════════════════════════════════════════════
#  Muvaffaqiyatli kirish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_togri_malumot_token_beradi_va_token_ishlaydi(
    anon_client: httpx.AsyncClient,
) -> None:
    """Kirish → token → shu token bilan `/auth/me` ochiladi."""
    email, password = ADMIN

    login = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text

    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"], "access token bo'sh bo'lmasligi kerak"
    assert body["refresh_token"], "refresh token bo'sh bo'lmasligi kerak"
    assert body["access_token"] != body["refresh_token"]

    me = await anon_client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_email_registri_ahamiyatsiz(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Email katta harf bilan kiritilsa ham kirish ishlaydi.

    Baza emailni kichik harfda saqlaydi, router esa `.lower()` qiladi —
    foydalanuvchi Caps Lock bilan tergani uchun tashqarida qolmasin.
    """
    user = await make_user()

    response = await anon_client.post(
        f"{API}/auth/login",
        json={"email": user.email.upper(), "password": user.password},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_refresh_yangi_juftlik_beradi(anon_client: httpx.AsyncClient) -> None:
    """`/auth/refresh` refresh token bo'yicha yangi access token beradi."""
    email, password = ADMIN
    login = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    refresh = login.json()["refresh_token"]

    response = await anon_client.post(
        f"{API}/auth/refresh", json={"refresh_token": refresh}
    )
    assert response.status_code == 200, response.text

    me = await anon_client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200


# ══════════════════════════════════════════════════════════════
#  Xato kirish — javob hech narsani oshkor qilmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_notogri_parol_va_notanish_email_bir_xil_javob_beradi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Ikkala holatda ham AYNAN bir xil status va matn qaytadi.

    Agar javoblar farq qilsa, begona odam email ro'yxatini shu farq
    orqali saralab, kimning hisobi borligini aniqlab olardi.
    """
    user = await make_user()
    yoq_email = f"{uuid.uuid4().hex}@zvonki.uz"

    notogri_parol = await anon_client.post(
        f"{API}/auth/login",
        json={"email": user.email, "password": "butunlay-boshqa-parol"},
    )
    notanish_email = await anon_client.post(
        f"{API}/auth/login",
        json={"email": yoq_email, "password": user.password},
    )

    assert notogri_parol.status_code == 401, notogri_parol.text
    assert notanish_email.status_code == 401, notanish_email.text
    assert notogri_parol.json() == notanish_email.json(), (
        "javoblar farq qilsa — hisob bor-yo'qligi oshkor bo'ladi"
    )

    # Xato matnida na email, na parol qaytarilmasin
    matn = notogri_parol.text
    assert user.email not in matn
    assert user.password not in matn


@pytest.mark.asyncio
async def test_bosh_parol_kiritish_mumkin_emas(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Bo'sh parol bilan hisobga kirib bo'lmaydi."""
    user = await make_user()

    response = await anon_client.post(
        f"{API}/auth/login", json={"email": user.email, "password": ""}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_faolsiz_hisob_kira_olmaydi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Parol to'g'ri bo'lsa ham o'chirilgan hisob ichkariga kirmaydi."""
    user = await make_user(is_active=False)

    response = await anon_client.post(
        f"{API}/auth/login",
        json={"email": user.email, "password": user.password},
    )
    assert response.status_code == 401, response.text
    assert "token" not in response.text.lower()


@pytest.mark.asyncio
async def test_faolsiz_qilingan_hisobning_tokeni_darhol_kuchini_yoqotadi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Hisob o'chirilganda ilgari berilgan token ham ishlamay qoladi.

    Token muddati 8 soat — hisobni o'chirgach ham shuncha vaqt ochiq
    qolsa, ishdan bo'shatilgan xodim kun oxirigacha ma'lumot ko'rardi.
    """
    from sqlalchemy import update

    from src.core.database import SessionFactory
    from src.modules.users.infrastructure.models import UserModel

    user = await make_user()
    login = await anon_client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert (await anon_client.get(f"{API}/auth/me", headers=headers)).status_code == 200

    async with SessionFactory() as session:
        await session.execute(
            update(UserModel).where(UserModel.id == user.id).values(is_active=False)
        )
        await session.commit()

    assert (await anon_client.get(f"{API}/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_buzilgan_xeshli_hisob_401_beradi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Bazadagi bitta buzilgan yozuv butun login endpointini yiqitmasin."""
    from sqlalchemy import update

    from src.core.database import SessionFactory
    from src.modules.users.infrastructure.models import UserModel

    user = await make_user()
    async with SessionFactory() as session:
        await session.execute(
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(password_hash="$2b$12$qisqa")
        )
        await session.commit()

    response = await anon_client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_notogri_formatdagi_email_422(anon_client: httpx.AsyncClient) -> None:
    """`EmailStr` xato formatni so'rov darajasida to'xtatadi."""
    response = await anon_client.post(
        f"{API}/auth/login", json={"email": "email-emas", "password": "12345678"}
    )
    assert response.status_code == 422, response.text


# ══════════════════════════════════════════════════════════════
#  Token himoyasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tokensiz_himoyalangan_endpoint_401(
    anon_client: httpx.AsyncClient,
) -> None:
    """Sarlavhasiz so'rov 401 oladi — 403 emas, 500 ham emas."""
    for manzil in (f"{API}/auth/me", f"{API}/users", f"{API}/settings"):
        response = await anon_client.get(manzil)
        assert response.status_code == 401, f"{manzil} → {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="bosh"),
        pytest.param("shunchaki-matn", id="jwt-emas"),
        pytest.param("a.b.c", id="uch-bolak-lekin-axlat"),
        pytest.param(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiLCJ0eXBlIjoiYWNjZXNzIn0."
            "yolgon-imzo",
            id="soxta-imzo",
        ),
    ],
)
async def test_buzilgan_token_401(anon_client: httpx.AsyncClient, token: str) -> None:
    """Yaroqsiz tokenning har bir ko'rinishi 401 bilan rad etiladi."""
    response = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_refresh_tokenni_access_orniga_ishlatib_bolmaydi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """Token turi tekshiriladi: `refresh` bilan `/auth/me` ochilmaydi.

    Ikkalasi ham bir xil kalit bilan imzolangani uchun imzo to'g'ri
    chiqadi — farqni faqat `type` maydoni ushlaydi.
    """
    user = await make_user()
    refresh = create_refresh_token(user.id)

    response = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_mavjud_bolmagan_foydalanuvchi_tokeni_401(
    anon_client: httpx.AsyncClient,
) -> None:
    """Imzosi to'g'ri, lekin egasi bazada yo'q token ham qabul qilinmaydi."""
    token = create_access_token(uuid.uuid4())

    response = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_bearer_prefiksisiz_sarlavha_qabul_qilinmaydi(
    anon_client: httpx.AsyncClient, make_user
) -> None:
    """`Authorization: <token>` — «Bearer» so'zisiz — o'tmaydi."""
    user = await make_user()
    token = create_access_token(user.id)

    response = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": token}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_muddati_otgan_token_401(
    anon_client: httpx.AsyncClient, make_user, monkeypatch
) -> None:
    """Muddati tugagan token ham 401 beradi."""
    from src.core import security as security_module

    user = await make_user()
    monkeypatch.setattr(
        security_module.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1, raising=False
    )
    eskirgan = create_access_token(user.id)

    response = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {eskirgan}"}
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_cookie_orqali_ham_kirish_mumkin(anon_client: httpx.AsyncClient) -> None:
    """Login `access_token` cookie'sini o'rnatadi — brauzer uchun.

    Sarlavhasiz keyingi so'rov ham shu cookie bilan o'tishi kerak.
    """
    email, password = ADMIN
    login = await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    assert "access_token" in login.cookies

    # `Authorization` sarlavhasi umuman qo'yilmadi — cookie ishlashi kerak
    me = await anon_client.get(f"{API}/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_logout_cookieni_ochiradi(anon_client: httpx.AsyncClient) -> None:
    email, password = ADMIN
    await anon_client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    response = await anon_client.post(f"{API}/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not anon_client.cookies.get("access_token")


# ══════════════════════════════════════════════════════════════
#  `/auth/me` javobining tarkibi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_me_javobida_parol_hech_qachon_bolmaydi(
    admin_client: httpx.AsyncClient,
) -> None:
    """Javob sxemasi parol xeshini o'z ichiga olmaydi."""
    response = await admin_client.get(f"{API}/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "role", "agent_id", "permissions"}
    assert "password" not in response.text
    assert "$2b$" not in response.text, "bcrypt xeshi javobga tushib qolgan"


@pytest.mark.asyncio
async def test_me_admin_uchun_agent_id_bosh(admin_client: httpx.AsyncClient) -> None:
    body = (await admin_client.get(f"{API}/auth/me")).json()
    assert body["role"] == Role.ADMIN.value
    assert body["agent_id"] is None


@pytest.mark.asyncio
async def test_me_savdo_xodimiga_oz_agentini_qaytaradi(sales_client) -> None:
    """SALES roli albatta xodimga bog'langan — `/auth/me` shuni ko'rsatadi."""
    client, data = sales_client
    body = (await client.get(f"{API}/auth/me")).json()

    assert body["role"] == Role.SALES.value
    assert body["agent_id"] == str(data.agent_id)
