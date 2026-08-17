"""`GET/POST/PATCH/DELETE /api/v1/regions` — ro'yxat, ruxsat va kaskad.

Haqiqiy ilova, haqiqiy JWT, haqiqiy baza. Har test o'z hududini
yaratadi va tekshiruvni AYNAN o'sha nomlar bo'yicha bajaradi — bazadagi
haqiqiy hududlar natijaga ta'sir qilmaydi va o'zgarmaydi ham.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/regions -q
"""

import uuid

import pytest
from sqlalchemy import select

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.infrastructure.models import RegionModel
from src.modules.regions.tests.conftest import (
    API,
    MARK,
    USAGE_ZERO,
    unique_name,
)

# ══════════════════════════════════════════════════════════════
#  Ro'yxat
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_admin_toliq_royxatni_tartib_boyicha_oladi(admin_client, seed):
    """Tartib: avval `sort_order`, teng bo'lsa `name`.

    Uchta hudud ataylab shunday qo'yiladi: eng kichik `sort_order`
    alifboda oxirgi nom bilan. Faqat nom bo'yicha saralangan kod
    bu testda yiqiladi.
    """
    suffix = uuid.uuid4().hex[:8]
    ikkinchi = await seed.region(f"{MARK}-b-{suffix}", sort_order=9000)
    birinchi = await seed.region(f"{MARK}-a-{suffix}", sort_order=9000)
    eng_yuqori = await seed.region(f"{MARK}-c-{suffix}", sort_order=8990)

    response = await admin_client.get(f"{API}/regions")
    assert response.status_code == 200, response.text
    body = response.json()

    bizniki = [row["name"] for row in body if suffix in row["name"]]
    assert bizniki == [eng_yuqori.name, birinchi.name, ikkinchi.name]

    # Butun ro'yxat ham `sort_order` bo'yicha o'sib boradi
    tartiblar = [row["sort_order"] for row in body]
    assert tartiblar == sorted(tartiblar)

    # Ishlatilish hisobi ro'yxatning bir qismi — admin o'chirishdan
    # oldin oqibatini ko'radi
    yangi = next(row for row in body if row["name"] == birinchi.name)
    assert yangi["usage"] == USAGE_ZERO
    assert yangi["is_active"] is True


@pytest.mark.asyncio
async def test_include_inactive_bayrogi_ishlaydi(admin_client, seed):
    """Faolsiz hudud arxiv: standart ro'yxatda yo'q, so'ralganda bor."""
    faol = await seed.region()
    faolsiz = await seed.region(is_active=False)

    standart = [
        row["name"] for row in (await admin_client.get(f"{API}/regions")).json()
    ]
    assert faol.name in standart
    assert faolsiz.name not in standart

    toliq = (
        await admin_client.get(f"{API}/regions", params={"include_inactive": True})
    ).json()
    nomlar = [row["name"] for row in toliq]
    assert faol.name in nomlar
    assert faolsiz.name in nomlar
    assert next(row for row in toliq if row["name"] == faolsiz.name)["is_active"] is False


# ══════════════════════════════════════════════════════════════
#  Rol doirasi — savdo xodimi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_guruhsiz_savdo_xodimida_royxat_bosh(sales_client):
    """Guruhi yo'q xodim BO'SH ro'yxat oladi — bu to'g'ri holat.

    ⚠️ Xodimning `agents.region` maydoni ro'yxatga QO'SHILMAYDI. Bu
    fixture'dagi xodim «Toshkent» da yashaydi va bazada shu nomli faol
    hudud bor — agar `agents.region` manba bo'lganida ro'yxat bo'sh
    bo'lmasdi. U yashash joyi, xizmat ko'rsatiladigan hudud emas.
    """
    client, data = sales_client
    assert data.region == "Toshkent"  # `agents.region` haqiqiy hudud nomi

    response = await client.get(f"{API}/regions")
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.asyncio
async def test_savdo_xodimi_faqat_oz_guruhlari_hududlarini_koradi(
    sales_client, admin_client, seed
):
    """Filtr xodimning O'Z guruhlaridan yig'iladi, kompaniyanikidan emas."""
    client, data = sales_client
    ishlaydigan = await seed.region()
    begona = await seed.region()  # boshqa xodimning hududi
    await seed.group(agent_id=data.agent_id, region=ishlaydigan.name)

    nomlar = [row["name"] for row in (await client.get(f"{API}/regions")).json()]
    assert nomlar == [ishlaydigan.name]
    assert begona.name not in nomlar
    assert data.region not in nomlar  # yana: `agents.region` qo'shilmaydi

    # Boshqa rollar uchun hech narsa o'zgarmaydi — admin ikkalasini ham ko'radi
    admin_nomlar = [
        row["name"] for row in (await admin_client.get(f"{API}/regions")).json()
    ]
    assert ishlaydigan.name in admin_nomlar
    assert begona.name in admin_nomlar


@pytest.mark.asyncio
async def test_faolsiz_guruh_xodim_hududiga_qoshilmaydi(sales_client, seed):
    """Bot chiqarilgan / arxivlangan guruh filtrda qolmasin."""
    client, data = sales_client
    faol = await seed.region()
    yopilgan = await seed.region()
    await seed.group(agent_id=data.agent_id, region=faol.name, is_active=True)
    await seed.group(agent_id=data.agent_id, region=yopilgan.name, is_active=False)

    nomlar = [row["name"] for row in (await client.get(f"{API}/regions")).json()]
    assert nomlar == [faol.name]


# ══════════════════════════════════════════════════════════════
#  Ruxsat: `regions:write`
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_admin_hudud_yaratadi_tahrirlaydi_va_ochiradi(admin_client, seed):
    nom = unique_name("crud")
    yaratildi = await admin_client.post(
        f"{API}/regions", json={"name": nom, "note": "  izoh  "}
    )
    assert yaratildi.status_code == 201, yaratildi.text
    body = yaratildi.json()
    seed.track_region(body["id"])

    assert body["name"] == nom
    assert body["is_active"] is True
    assert body["note"] == "izoh"  # chetki bo'shliqlar kesiladi
    assert body["usage"] == USAGE_ZERO

    tahrir = await admin_client.patch(
        f"{API}/regions/{body['id']}", json={"sort_order": 7777, "is_active": False}
    )
    assert tahrir.status_code == 200, tahrir.text
    assert tahrir.json()["sort_order"] == 7777
    assert tahrir.json()["is_active"] is False
    assert tahrir.json()["name"] == nom
    # Nom o'zgarmadi — kaskad ishlamasligi kerak
    assert tahrir.json()["renamed"] == USAGE_ZERO

    ochirildi = await admin_client.delete(f"{API}/regions/{body['id']}")
    assert ochirildi.status_code == 204

    qolgan = (
        await admin_client.get(f"{API}/regions", params={"include_inactive": True})
    ).json()
    assert nom not in [row["name"] for row in qolgan]


@pytest.mark.asyncio
async def test_yozish_savdo_xodimiga_yopiq(sales_client, seed):
    """`regions:write` SALES rolida yo'q — uchala amal ham 403."""
    client, _ = sales_client
    hudud = await seed.region()

    yaratish = await client.post(f"{API}/regions", json={"name": unique_name("taqiq")})
    tahrir = await client.patch(
        f"{API}/regions/{hudud.id}", json={"name": unique_name("taqiq")}
    )
    ochirish = await client.delete(f"{API}/regions/{hudud.id}")

    assert [yaratish.status_code, tahrir.status_code, ochirish.status_code] == [
        403,
        403,
        403,
    ]

    # Hudud tegilmagan holida turibdi
    async with SessionFactory() as session:
        saqlangan = await session.get(RegionModel, hudud.id)
        assert saqlangan is not None
        assert saqlangan.name == hudud.name


@pytest.mark.asyncio
async def test_yozish_tokensiz_klientga_yopiq(anon_client, seed):
    hudud = await seed.region()

    yaratish = await anon_client.post(
        f"{API}/regions", json={"name": unique_name("taqiq")}
    )
    tahrir = await anon_client.patch(f"{API}/regions/{hudud.id}", json={"name": "x"})
    ochirish = await anon_client.delete(f"{API}/regions/{hudud.id}")

    assert [yaratish.status_code, tahrir.status_code, ochirish.status_code] == [
        401,
        401,
        401,
    ]

    async with SessionFactory() as session:
        assert await session.get(RegionModel, hudud.id) is not None


# ══════════════════════════════════════════════════════════════
#  Kaskad nom o'zgartirish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nom_ozgarsa_xodim_mijoz_va_guruh_ham_yangilanadi(
    admin_client, dataset, seed
):
    """Hudud nomi uch jadvalda MATN bo'lib takrorlanadi.

    Faqat `regions` da o'zgartirilsa, xodim/mijoz/guruh eski nom bilan
    yetim qolardi. Shu sababli kaskad — shu modulning butun mavjudlik
    sababi.
    """
    eski = unique_name("eski")
    yangi = unique_name("yangi")

    hudud = await seed.region(eski)
    data = await dataset(scores=[70], region=eski)  # xodim + mijoz shu hududda
    guruh = await seed.group(agent_id=data.agent_id, region=eski)

    response = await admin_client.patch(f"{API}/regions/{hudud.id}", json={"name": yangi})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["name"] == yangi
    assert body["renamed"] == {"agents": 1, "clients": 1, "groups": 1}
    assert body["usage"] == {"agents": 1, "clients": 1, "groups": 1}

    async with SessionFactory() as session:
        assert (await session.get(AgentModel, data.agent_id)).region == yangi
        assert (await session.get(ClientModel, data.client_id)).region == yangi
        assert (await session.get(TelegramGroupModel, guruh.id)).region == yangi

        # Eski nom hech qayerda qolmadi
        qoldiq = (
            await session.execute(
                select(AgentModel.id).where(AgentModel.region == eski)
            )
        ).first()
        assert qoldiq is None


@pytest.mark.asyncio
async def test_ishlatilayotgan_hududni_ochirib_bolmaydi(admin_client, dataset, seed):
    """O'chirish `agents.region` ni ro'yxatdan tashqarida qoldirardi — 409."""
    nom = unique_name("band")
    hudud = await seed.region(nom)
    await dataset(scores=[80], region=nom)

    response = await admin_client.delete(f"{API}/regions/{hudud.id}")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "region_in_use"

    async with SessionFactory() as session:
        assert await session.get(RegionModel, hudud.id) is not None


# ══════════════════════════════════════════════════════════════
#  Nom takrorlanishi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bir_xil_nomli_ikkinchi_hudud_409(admin_client, seed):
    """Takroriy nom — tushunarli 409, `IntegrityError` traceback emas."""
    mavjud = await seed.region()

    aynan = await admin_client.post(f"{API}/regions", json={"name": mavjud.name})
    if aynan.status_code == 201:  # himoya ishlamasa qoldiq qolmasin
        seed.track_region(aynan.json()["id"])
    assert aynan.status_code == 409, aynan.text
    assert aynan.json()["error"]["code"] == "region_exists"

    # Katta-kichik harf farqi ham himoyalangan: dropdownda ko'zga bir xil
    # ko'rinadigan ikkita qator paydo bo'lmasin
    boshqa_registr = await admin_client.post(
        f"{API}/regions", json={"name": mavjud.name.upper()}
    )
    if boshqa_registr.status_code == 201:
        seed.track_region(boshqa_registr.json()["id"])
    assert boshqa_registr.status_code == 409, boshqa_registr.text

    # Boshqa hududdagi nomga o'tkazish ham rad etiladi
    ikkinchi = await seed.region()
    tahrir = await admin_client.patch(
        f"{API}/regions/{ikkinchi.id}", json={"name": mavjud.name}
    )
    assert tahrir.status_code == 409, tahrir.text
    assert tahrir.json()["error"]["code"] == "region_exists"
