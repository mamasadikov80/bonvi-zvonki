"""Tur bo'yicha filtr — `not_sales` da NULL TUZOG'I.

NEGA BU TEST BOR. Tasniflashdan keyin ma'lumotning katta qismi savdo
bo'lmay chiqdi (o'lchandi: 172 tadan 166 tasi). Filtrsiz ro'yxatni
ishlatib bo'lmaydi, filtr esa bitta joyda jimgina yolg'on gapirishi
mumkin:

    WHERE call_type <> 'sales'

SQL da `NULL <> 'sales'` → `NULL`, ya'ni YOLG'ON emas, NOMA'LUM — va
qator natijaga tushmaydi. Natijada «Savdo emas» filtri hali
tasniflanmagan qo'ng'iroqlarni yashirib qo'yardi. Ular ham savdo emas:
hali bilinmagani ularni savdo qilmaydi. Yashirilgani esa bilinmasdi —
son shunchaki kichikroq bo'lardi.
"""

import pytest

API = "http://test/api/v1"

#: Barcha turlarni qamrash uchun yetarlicha keng oyna
ORALIQ = {"date_from": "2019-01-01T00:00:00Z", "date_to": "2035-01-01T00:00:00Z"}


async def _total(client, **params) -> int:
    response = await client.get(f"{API}/calls", params={**ORALIQ, "page_size": 1, **params})
    assert response.status_code == 200, response.text
    return response.json()["total"]


@pytest.mark.asyncio
async def test_savdo_va_savdo_emas_jami_filtrsizga_teng(admin_client) -> None:
    """⚠️ ASOSIY KAFOLAT: hech bir qo'ng'iroq ikki filtr orasida
    yo'qolmaydi. Bu tenglik buzilsa NULL tuzog'i qaytgan bo'ladi."""
    hammasi = await _total(admin_client)
    savdo = await _total(admin_client, call_type="sales")
    savdo_emas = await _total(admin_client, call_type="not_sales")

    assert savdo + savdo_emas == hammasi, (
        f"{savdo} + {savdo_emas} != {hammasi} — oradan qo'ng'iroq tushib qoldi"
    )


@pytest.mark.asyncio
async def test_tasniflanmaganlar_savdo_emas_ichida(admin_client) -> None:
    """`unknown` — `not_sales` ning QISMI, alohida guruh emas."""
    tasniflanmagan = await _total(admin_client, call_type="unknown")
    savdo_emas = await _total(admin_client, call_type="not_sales")
    assert tasniflanmagan <= savdo_emas


@pytest.mark.asyncio
async def test_aniq_turlar_yigindisi(admin_client) -> None:
    """Aniq turlar + tasniflanmaganlar = hammasi.

    Turlar bir-birini QOPLAMASLIGI kerak: qoplasa yig'indi kattaroq
    chiqadi va razrezdagi sonlar hech narsani ifodalamaydi."""
    turlar = ["sales", "internal", "unknown"]
    yigindi = 0
    for tur in turlar:
        yigindi += await _total(admin_client, call_type=tur)
    assert yigindi == await _total(admin_client)


@pytest.mark.asyncio
async def test_notogri_qiymat_422(admin_client) -> None:
    """Noma'lum qiymat JIMGINA e'tiborsiz qoldirilmaydi.

    Aks holda `call_type=sale` (harf tushib qolgan) filtrsiz ro'yxatni
    qaytarardi va foydalanuvchi buni «savdo qo'ng'iroqlari 172 ta» deb
    o'qirdi."""
    response = await admin_client.get(f"{API}/calls", params={"call_type": "xato"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_filtr_boshqa_filtrlar_bilan_birga_ishlaydi(admin_client) -> None:
    """Tur filtri qidiruv/sana bilan BIRGA qo'llanishi kerak — biri
    ikkinchisini o'chirib yubormasin."""
    response = await admin_client.get(
        f"{API}/calls",
        params={**ORALIQ, "call_type": "internal", "sort": "date", "order": "asc"},
    )
    assert response.status_code == 200, response.text
    for row in response.json()["items"]:
        assert row["call_type"] == "internal"
