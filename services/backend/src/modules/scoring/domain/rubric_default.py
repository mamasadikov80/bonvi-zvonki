"""Standart rubrika (v1) — PLAN.md 3.4-bo'limidan.

Bu faqat BOSHLANG'ICH qiymat. Birinchi ishga tushirishda bazaga
yoziladi, keyin dashboard → "Baholash mezonlari" orqali tahrirlanadi.
Kodni o'zgartirish shart emas.

Qoida: bloklar yig'indisi aniq 100 ball bo'lishi kerak.
"""

from typing import Any

DEFAULT_RUBRIC: dict[str, Any] = {
    "name": "Bonvi savdo rubrikasi v1",
    "description": (
        "Savdo direktori bilan kelishilgan boshlang'ich rubrika. "
        "Har oyda ko'rib chiqilishi tavsiya etiladi."
    ),
    "blocks": [
        {
            "key": "script",
            "label": "Skript va struktura",
            "max": 25,
            "criteria": [
                {
                    "id": "A1",
                    "label": "Salomlashish va o'zini tanishtirish",
                    "points": 5,
                    "description": "«Assalomu alaykum, men [ism], Bonvi kompaniyasidan»",
                },
                {
                    "id": "A2",
                    "label": "Ehtiyojni aniqlash",
                    "points": 8,
                    "description": "Ochiq savollar berdimi, mahsulot ehtiyojini so'radimi",
                },
                {
                    "id": "A3",
                    "label": "Mahsulotni to'g'ri taqdim etish",
                    "points": 7,
                    "description": "Model, xususiyat va narx to'g'ri aytildi",
                },
                {
                    "id": "A4",
                    "label": "Keyingi qadam kelishildi",
                    "points": 5,
                    "description": "Aniq sana yoki zakaz tasdig'i bilan yakunlandi",
                },
            ],
        },
        {
            "key": "communication",
            "label": "Muloqot madaniyati",
            "max": 25,
            "criteria": [
                {
                    "id": "B1",
                    "label": "Hurmatli ohang",
                    "points": 8,
                    "description": "Siz'lash, xushmuomalalik",
                },
                {
                    "id": "B2",
                    "label": "Haqorat va so'kinish yo'q",
                    "points": 10,
                    "description": "Buzilsa — umumiy ball 0 ga tushadi",
                },
                {
                    "id": "B3",
                    "label": "Client'ni bo'lmadi",
                    "points": 4,
                    "description": "Overlap va bo'lish soni akustik tahlildan olinadi",
                },
                {
                    "id": "B4",
                    "label": "Ovoz toni mos",
                    "points": 3,
                    "description": "Prosodika: baqirish yoki asabiylik belgilari",
                },
            ],
        },
        {
            "key": "resolution",
            "label": "Muammoni hal qilish",
            "max": 25,
            "criteria": [
                {
                    "id": "C1",
                    "label": "Client savoliga to'g'ri javob berdi",
                    "points": 10,
                    "description": "Ma'lumot aniq va to'liq",
                },
                {
                    "id": "C2",
                    "label": "E'tirozlarni ishlab chiqdi",
                    "points": 8,
                    "description": "Narx, muddat, sifat e'tirozlariga javob",
                },
                {
                    "id": "C3",
                    "label": "Mos taklif berdi",
                    "points": 7,
                    "description": "Mahsulot client ehtiyojiga to'g'ri keldi",
                },
            ],
        },
        {
            "key": "sales_skill",
            "label": "Savdo qobiliyati",
            "max": 25,
            "criteria": [
                {
                    "id": "D1",
                    "label": "Yopish urinishi",
                    "points": 8,
                    "description": "«Nechta olamiz?» — suhbat osilgan holda tugamadi",
                },
                {
                    "id": "D2",
                    "label": "Upsell / cross-sell",
                    "points": 6,
                    "description": "Qo'shimcha model yoki miqdor taklif qilindi",
                },
                {
                    "id": "D3",
                    "label": "Aniq keyingi qadam",
                    "points": 6,
                    "description": "«Payshanba qo'ng'iroq qilaman» — mavhum emas",
                },
                {
                    "id": "D4",
                    "label": "Qiymat argumenti",
                    "points": 5,
                    "description": "Nega aynan hozir olish kerakligi asoslandi",
                },
            ],
        },
    ],
    "red_flags": [
        {
            "type": "profanity",
            "label": "Haqorat / so'kinish",
            "penalty": -100,
            "zeroes_score": True,
            "description": "Umumiy ball 0 ga tushadi va menejerga darhol xabar boradi",
        },
        {
            "type": "off_policy_deal",
            "label": "Qoidadan tashqari kelishuv",
            "penalty": -25,
            "zeroes_score": False,
            "description": "Rasmiy narxdan tashqari shaxsiy kelishuv",
        },
        {
            "type": "shouting",
            "label": "Baqirish",
            "penalty": -20,
            "zeroes_score": False,
            "description": "Prosodika + matn konteksti birgalikda tasdiqlaydi",
        },
        {
            "type": "unrealistic_promise",
            "label": "Bajarilmas va'da",
            "penalty": -15,
            "zeroes_score": False,
            "description": "Bajarib bo'lmaydigan muddat yoki shart va'da qilindi",
        },
        {
            "type": "badmouthing",
            "label": "Salbiy gap (kompaniya / hamkasb)",
            "penalty": -15,
            "zeroes_score": False,
            "description": "Client oldida kompaniya yoki hamkasb haqida salbiy fikr",
        },
        {
            "type": "ignored_complaint",
            "label": "Shikoyat e'tiborsiz qoldirilgan",
            "penalty": -10,
            "zeroes_score": False,
            "description": "Client muammo aytdi, javob berilmadi",
        },
    ],
}
