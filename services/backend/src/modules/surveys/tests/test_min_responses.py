"""`survey.min_responses` — reyting «tayyor» deb hisoblanadigan chegara.

NEGA BU ALOHIDA TEKSHIRILADI
  Bu sozlama bir vaqtlar panelda bor edi-yu, kod uni O'QIMASDI: admin
  qiymatni o'zgartirar, hech narsa o'zgarmasdi. Endi yagona manba —
  `resolve_min_responses()`. Test aynan shu bog'lanishni ushlab turadi.

  Ikkinchi qoida: `average` chegaradan QAT'I NAZAR qaytadi. Ilgari
  `ready=False` da u `null` qilinardi, `/analytics/overview` esa
  o'sha reytingni chegarasiz ko'rsatardi — bitta baho ikkita ekranda
  ikki xil ko'rinardi. Endi qaror UI da: raqam ham, soni ham, `ready`
  ham qaytadi.

Sozlama dev bazasida umumiy, shuning uchun faqat `settings_guard`
orqali o'zgartiriladi — u test oxirida eski qiymatni QAYTARADI.
"""

import pytest

FEEDBACK = "/api/v1/surveys"


async def _feedback(client, agent_id):
    response = await client.get(
        FEEDBACK, params={"days": 90, "agent_id": str(agent_id)}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_chegaradan_kam_javobda_ready_false_lekin_qiymat_bor(
    admin_client, dataset, settings_guard
) -> None:
    await settings_guard("survey.min_responses", 5)
    data = await dataset(scores=[90], ratings=[5, 4, 3], rating_days_ago=[1, 2, 3])

    body = await _feedback(admin_client, data.agent_id)

    assert body["count"] == 3
    assert body["min_responses"] == 5
    assert body["ready"] is False
    # Qiymat baribir qaytadi — chizish yoki chizmaslikni UI hal qiladi
    assert body["average"] == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_chegara_pasaytirilsa_ayni_malumot_ready_boladi(
    admin_client, dataset, settings_guard
) -> None:
    """Bir xil uchta javob, faqat chegara boshqa — natija teskari.

    Shu juftlik `ready` ning sozlamadan hisoblanayotganini isbotlaydi:
    agar u kodga qotirilgan konstantadan olinsa, ikkala test bir xil
    javob berardi.
    """
    await settings_guard("survey.min_responses", 3)
    data = await dataset(scores=[90], ratings=[5, 4, 3], rating_days_ago=[1, 2, 3])

    body = await _feedback(admin_client, data.agent_id)

    assert body["count"] == 3
    assert body["min_responses"] == 3
    assert body["ready"] is True
    assert body["average"] == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_notogri_chegara_standart_qiymatga_qaytadi(
    admin_client, dataset, settings_guard
) -> None:
    """Sozlamaga matn yoki nol tushib qolsa — reyting ochilib ketmasligi kerak.

    `resolve_min_responses()` bunday qiymatni rad etib, konstantaga
    (`MIN_RESPONSES_FOR_RATING = 5`) qaytadi.
    """
    await settings_guard("survey.min_responses", 0)
    data = await dataset(scores=[90], ratings=[5], rating_days_ago=[1])

    body = await _feedback(admin_client, data.agent_id)

    assert body["min_responses"] == 5
    assert body["count"] == 1
    assert body["ready"] is False
