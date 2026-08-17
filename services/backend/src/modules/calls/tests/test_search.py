"""`GET /calls?search=...` — bitta maydon, to'rtta ustun.

Qidiruv ataylab keng: foydalanuvchi «Samarqand» deb yozganda hududdan,
xodim ismini yozganda xodimdan, mijoz nomini yozganda mijozdan topilishi
kutiladi (router.py:184-195). Quyidagi testlar shu va'daning har bir
qismini alohida qotiradi.

EKRANLASH
  `ILIKE` uchun `%` va `_` — metabelgilar: birinchisi «ixtiyoriy matn»,
  ikkinchisi «ixtiyoriy bitta belgi» degani. Foydalanuvchi ularni
  ODDIY BELGI deb yozadi (masalan mijoz nomi «MChJ 100% Sut»), shuning
  uchun router shablonga solishdan oldin ularni ekranlaydi — kiritilgan
  matn hech qachon shablonga aylanmaydi.
"""

import uuid

import pytest

LIST = "/api/v1/calls"


def _token() -> str:
    """Bazadagi haqiqiy yozuvlarga mos kelmaydigan noyob bo'lak."""
    return f"pytest{uuid.uuid4().hex[:10]}"


async def _calls(client, data, **params):
    response = await client.get(
        LIST, params={"agent_id": str(data.agent_id), "page_size": 200, **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


# ══════════════════════════════════════════════════════════════
#  Qidiruv nimani topadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qidiruv_xodim_ismi_boyicha_topadi(admin_client, dataset) -> None:
    data = await dataset(scores=[90, 70])

    body = await _calls(admin_client, data, search=data.agent_name)

    assert body["total"] == 2
    assert all(item["agent_name"] == data.agent_name for item in body["items"])


@pytest.mark.asyncio
async def test_qidiruv_mijoz_nomi_boyicha_topadi(admin_client, dataset, db) -> None:
    """Mijoz nomi xodim ismiga ham, hududga ham o'xshamaydi — demak
    topilsa, u AYNAN `client.name` orqali topilgan."""
    token = _token()
    data = await dataset(scores=[90, 70])
    await db.client(data.client_id, name=f"{token}mijoz")

    body = await _calls(admin_client, data, search=token)

    assert body["total"] == 2
    assert all(item["client_name"] == f"{token}mijoz" for item in body["items"])


@pytest.mark.asyncio
async def test_qidiruv_hudud_boyicha_topadi(admin_client, dataset) -> None:
    hudud = _token()
    data = await dataset(scores=[90], region=hudud)

    body = await _calls(admin_client, data, search=hudud)

    assert body["total"] == 1


@pytest.mark.asyncio
async def test_qidiruv_transkript_boyicha_topadi(admin_client, dataset, db) -> None:
    token = _token()
    data = await dataset(scores=[90, 70])
    await db.call(data.calls[0].call_id, transcript=f"Salom, {token} haqida gaplashdik")

    body = await _calls(admin_client, data, search=token)

    assert body["total"] == 1
    assert body["items"][0]["id"] == str(data.calls[0].call_id)


@pytest.mark.asyncio
async def test_qidiruv_registrga_sezgir_emas(admin_client, dataset, db) -> None:
    """`ILIKE` — katta-kichik harf farqi qidiruvni buzmasligi kerak."""
    token = _token()
    data = await dataset(scores=[90])
    await db.client(data.client_id, name=f"{token}MIJOZ")

    body = await _calls(admin_client, data, search=f"{token}mijoz")

    assert body["total"] == 1


@pytest.mark.asyncio
async def test_mos_kelmasa_bosh_royxat(admin_client, dataset) -> None:
    data = await dataset(scores=[90, 70])

    body = await _calls(admin_client, data, search=_token())

    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_bosh_qidiruv_royxatni_kesmaydi(admin_client, dataset) -> None:
    """Faqat probeldan iborat matn — filtr umuman qo'llanmasligi kerak."""
    data = await dataset(scores=[90, 70])

    body = await _calls(admin_client, data, search="   ")

    assert body["total"] == 2


# ══════════════════════════════════════════════════════════════
#  ILIKE metabelgilari oddiy belgi bo'lib qoladi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_foiz_belgisi_hammani_qaytarmaydi(admin_client, dataset) -> None:
    """Bitta `%` — filtrni o'chiruvchi shablon emas, izlanadigan belgi."""
    data = await dataset(scores=[90, 70])

    body = await _calls(admin_client, data, search="%")

    # Bu xodimning hech bir maydonida `%` belgisi yo'q
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_pastki_chiziq_ixtiyoriy_belgiga_aylanmaydi(
    admin_client, dataset, db
) -> None:
    """«MChJ_Sut» so'ragan odam «MChJ-Sut» ni olmasligi kerak."""
    token = _token()
    data = await dataset(scores=[90, 70])
    await db.client(data.client_id, name=f"{token}aXb")

    body = await _calls(admin_client, data, search=f"{token}a_b")

    # `a_b` — hech qayerda yo'q, `aXb` esa boshqa matn
    assert body["total"] == 0
