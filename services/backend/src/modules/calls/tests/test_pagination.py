"""`GET /calls` — sahifalash barqarormi?

`OFFSET/LIMIT` bilan sahifalashning klassik tuzog'i shu: agar saralash
tartibi NOYOB bo'lmasa (masalan o'nlab qo'ng'iroq bir xil soniyada
boshlangan), baza qatorlarni har so'rovda boshqacha joylashtirishi
mumkin. O'shanda 2-sahifadagi qator 1-sahifada ham chiqadi, boshqasi
esa ikkala sahifaga ham tushmay YO'QOLADI — foydalanuvchi jadvalni
oxirigacha varaqlab ham qo'ng'irog'ini topolmaydi.

Router bunga qarshi ikkilamchi mezon qo'yadi (router.py:228-232):
oxirida har doim `CallModel.id`. Quyidagi testlar aynan shu himoyani
qotiradi — ataylab bir xil `started_at` va bir xil ball bilan.
"""

import pytest

LIST = "/api/v1/calls"


async def _sahifalarni_yig(client, data, *, page_size, **params):
    """Barcha sahifalarni ketma-ket o'qib, id'larni KELGAN TARTIBDA yig'adi.

    Qaytaradi: (id'lar ro'yxati, oxirgi `total`, har sahifadagi `total`lar).
    """
    ids: list[str] = []
    totals: list[int] = []
    page = 1

    while True:
        response = await client.get(
            LIST,
            params={
                "agent_id": str(data.agent_id),
                "page": page,
                "page_size": page_size,
                **params,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        totals.append(body["total"])
        ids.extend(item["id"] for item in body["items"])

        if not body["items"] or len(ids) >= body["total"]:
            return ids, body["total"], totals

        page += 1
        assert page <= 50, "sahifalash tugamadi — cheksiz sikl"


@pytest.mark.asyncio
async def test_sahifalash_dublikat_ham_yoqotish_ham_bermaydi(
    admin_client, dataset
) -> None:
    """7 ta qo'ng'iroq, sahifada 2 tadan → 4 sahifada aynan 7 ta noyob id."""
    data = await dataset(
        scores=[90, 85, 80, 75, 70, 65, 60], days_ago=[1, 2, 3, 4, 5, 6, 7]
    )

    ids, total, totals = await _sahifalarni_yig(admin_client, data, page_size=2)

    kutilgan = {str(call.call_id) for call in data.calls}
    assert total == 7
    assert set(totals) == {7}, "«Jami» soni sahifadan sahifaga o'zgarib ketdi"
    assert len(ids) == 7, "sahifalarda yo'qolgan yoki ortiqcha qator bor"
    assert len(set(ids)) == 7, "bitta qo'ng'iroq ikki sahifada chiqdi"
    assert set(ids) == kutilgan


@pytest.mark.asyncio
async def test_bir_xil_vaqtli_qongiroqlar_sahifalar_orasida_sakramaydi(
    admin_client, dataset
) -> None:
    """Eng og'ir holat: to'rttala qo'ng'iroq AYNAN bir vaqtda boshlangan.

    `started_at` bo'yicha saralash ularni ajrata olmaydi, demak tartibni
    faqat `CallModel.id` ikkilamchi mezoni barqaror ushlab turadi.
    """
    data = await dataset(scores=[90, 80, 70, 60], days_ago=[1, 1, 1, 1])

    # Poydevor haqiqatan teng vaqt bergani — testning sharti
    vaqtlar = {call.started_at for call in data.calls}
    assert len(vaqtlar) == 1, "dataset teng `started_at` bermadi, test ma'nosiz"

    ids, total, _ = await _sahifalarni_yig(admin_client, data, page_size=1)

    assert total == 4
    assert len(ids) == 4
    assert set(ids) == {str(call.call_id) for call in data.calls}


@pytest.mark.asyncio
async def test_bir_xil_ball_boyicha_saralaganda_ham_barqaror(
    admin_client, dataset
) -> None:
    """Ball ham, vaqt ham teng — tartibni faqat oxirgi mezon saqlaydi."""
    data = await dataset(scores=[70, 70, 70, 70], days_ago=[2, 2, 2, 2])

    ids, total, _ = await _sahifalarni_yig(
        admin_client, data, page_size=1, sort="score", order="desc"
    )

    assert total == 4
    assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_sahifalangan_tartib_yaxlit_royxat_bilan_bir_xil(
    admin_client, dataset
) -> None:
    """Varaqlash tartibni O'ZGARTIRMASLIGI kerak.

    Bir sahifada olingan ketma-ketlik bilan bo'lak-bo'lak yig'ilgani
    bir xil bo'lsa — sahifalash haqiqatan barqaror.
    """
    data = await dataset(
        scores=[90, 90, 70, 70, 50], days_ago=[1, 1, 2, 2, 3], unscored_calls=2
    )

    yaxlit = await admin_client.get(
        LIST,
        params={
            "agent_id": str(data.agent_id),
            "page_size": 200,
            "sort": "score",
            "order": "desc",
        },
    )
    assert yaxlit.status_code == 200, yaxlit.text
    yaxlit_ids = [item["id"] for item in yaxlit.json()["items"]]

    bolak_ids, total, _ = await _sahifalarni_yig(
        admin_client, data, page_size=2, sort="score", order="desc"
    )

    assert total == 7
    assert bolak_ids == yaxlit_ids


@pytest.mark.asyncio
async def test_oxirgi_sahifadan_keyin_bosh_royxat(admin_client, dataset) -> None:
    """Mavjud bo'lmagan sahifa — 500 emas, bo'sh ro'yxat va o'sha `total`."""
    data = await dataset(scores=[90, 80])

    response = await admin_client.get(
        LIST, params={"agent_id": str(data.agent_id), "page": 9, "page_size": 2}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 2
    assert body["page"] == 9
    assert body["page_size"] == 2
