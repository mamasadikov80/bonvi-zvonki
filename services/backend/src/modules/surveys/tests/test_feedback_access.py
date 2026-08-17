"""`GET /surveys` — kim nimani ko'radi.

BU MODULNING BUTUN QIYMATI ANONIMLIKDA. Har mijozga alohida Telegram
guruh ochilgan, ya'ni guruhda bitta mijoz o'tiradi: savdo xodimiga
«3 yulduz, 14-avgust» degan bitta qator ko'rsatilsa, u kim baho
berganini darhol topadi. Shundan keyin mijoz rostini yozmaydi va
so'rovnoma umuman keraksiz bo'lib qoladi.

Shuning uchun bu yerdagi testlar «chiroyli ko'rinsin» uchun emas:
ular ATAYLAB QO'YILGAN cheklovlarni qotirib qo'yadi.
"""

from datetime import UTC, datetime, timedelta

import pytest

FEEDBACK = "/api/v1/surveys"


@pytest.mark.asyncio
async def test_savdo_xodimi_faqat_ozinikini_koradi(sales_client, dataset) -> None:
    """URL da boshqa `agent_id` majburlansa ham natija o'zgarmaydi.

    Ruxsat doirasi so'rovdan KEYIN qo'yiladi (`router.py:160`:
    `agent_id = user.agent_id`), shuning uchun tashqaridan kelgan
    qiymat e'tiborga olinmasligi kerak.
    """
    client, own = sales_client
    other = await dataset(scores=[10], ratings=[1, 1, 1], rating_days_ago=[1, 2, 3])

    forced = await client.get(
        FEEDBACK, params={"days": 90, "agent_id": str(other.agent_id)}
    )
    assert forced.status_code == 200, forced.text
    body = forced.json()

    # `sales_client` fixture'ining bahosi: [5, 3] → (5 + 3) / 2 = 4.0
    assert own.ratings == [5, 3]
    assert body["count"] == 2
    assert body["average"] == pytest.approx(4.0, abs=0.01)
    # Boshqa xodimning uchta bir yulduzi taqsimotga ham tushmaydi
    assert body["distribution"]["1"] == 0


@pytest.mark.asyncio
async def test_savdo_xodimiga_alohida_yozuvlar_korsatilmaydi(sales_client) -> None:
    """`items` — SALES uchun HAR DOIM bo'sh (`hide_items`).

    Yig'ma raqamlar esa BARIBIR qaytadi: xodim o'z natijasini ko'rishi
    kerak, faqat kimning bahosi ekanini ko'rmasligi kerak.
    """
    client, _own = sales_client

    response = await client.get(FEEDBACK, params={"days": 90})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["items"] == []
    assert body["count"] == 2
    assert body["average"] is not None


@pytest.mark.asyncio
async def test_tokensiz_sorov_401_oladi(anon_client) -> None:
    response = await anon_client.get(FEEDBACK, params={"days": 90})

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_hidden_sozlamasida_savdo_xodimi_403_oladi(
    sales_client, settings_guard
) -> None:
    client, _own = sales_client
    await settings_guard("access.sales_client_rating", "hidden")

    response = await client.get(FEEDBACK, params={"days": 90})

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_score_only_sozlamasida_raqamlar_koringan_holda_qaytadi(
    sales_client, settings_guard
) -> None:
    """`score_only` — standart rejim: raqam bor, yozuvlar yo'q."""
    client, _own = sales_client
    await settings_guard("access.sales_client_rating", "score_only")

    response = await client.get(FEEDBACK, params={"days": 90})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["count"] == 2
    assert body["average"] == pytest.approx(4.0, abs=0.01)
    assert body["items"] == []


@pytest.mark.asyncio
async def test_full_sozlamasi_ham_yozuvlarni_ochmaydi(
    sales_client, settings_guard
) -> None:
    """⚠️ ATAYLAB SHUNDAY: `full` sozlamasi `items` ni OCHMAYDI.

    Sozlama izohlarni boshqaradi, alohida yozuvlarni esa `hide_items`
    butunlay yashiradi (`router.py:187`) — va bu qoida sozlamadan
    KUCHLIROQ. Sababi fayl boshida: bitta baho = bitta mijoz.

    Shu sababli SALES uchun `show_comments` (`router.py:189`) hech
    qanday kuzatiladigan natija bermaydi: izoh chiqadigan yagona joy
    `items`, u esa har doim bo'sh. Sozlamaning haqiqiy ta'siri faqat
    `hidden` qiymatida ko'rinadi (403).

    Kimdir kelajakda «`full` ishlamayapti» deb bu yerni tuzatmoqchi
    bo'lsa — avval shu izohni o'qisin.
    """
    client, _own = sales_client
    await settings_guard("access.sales_client_rating", "full")

    response = await client.get(FEEDBACK, params={"days": 90})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["items"] == []
    assert body["count"] == 2


@pytest.mark.asyncio
async def test_menejer_izohlarni_koradi(admin_client, dataset, survey_factory) -> None:
    """Nazorat testi: izoh yo'lining o'zi ishlayotganini isbotlaydi.

    Aks holda «SALES izohni ko'rmaydi» degan testlar bo'sh gap bo'lardi —
    izoh umuman hech kimga ko'rinmayotgan bo'lsa ham ular yashil turardi.
    """
    data = await dataset(scores=[])
    now = datetime.now(UTC)

    await survey_factory(
        agent_id=data.agent_id,
        client_id=data.client_id,
        responses=[
            {
                "csat": 2,
                "responded_at": now - timedelta(days=1),
                "comment": "pytest: yetkazib berish kechikdi",
                "red_flags": ["late_delivery"],
            }
        ],
    )

    response = await admin_client.get(
        FEEDBACK, params={"days": 90, "agent_id": str(data.agent_id)}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["comment"] == "pytest: yetkazib berish kechikdi"
    assert item["red_flags"] == ["late_delivery"]
    assert item["csat"] == 2
