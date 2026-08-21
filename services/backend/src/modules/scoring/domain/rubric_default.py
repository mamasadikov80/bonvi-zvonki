"""Standart rubrika (v1) — PLAN.md 3.4-bo'limidan.

Bu faqat BOSHLANG'ICH qiymat. Birinchi ishga tushirishda bazaga
yoziladi, keyin dashboard → "Baholash mezonlari" orqali tahrirlanadi.
Kodni o'zgartirish shart emas.

Qoida: bloklar yig'indisi aniq 100 ball bo'lishi kerak.

## `optional` — MEZON HAR SUHBATGA TUSHAVERMAYDI

Har kriteriyada `optional` bayrog'i bor. `True` bo'lsa, AI o'sha
mezonni «bu suhbatga taalluqli emas» (`na`) deb belgilashi va ball
hisobidan CHIQARIB tashlashi mumkin.

NEGA KERAK. Bonvi mijozlarining aksariyati — ESKI mijoz. Ular skript
bo'yicha gaplashmaydi: «akajon, menga 50 ta chiqarib qo'ying» yoki
«yangi narxlarni tashlang» deb bir daqiqada tugatadi. Bunday suhbatda
ehtiyojni aniqlash ham, mahsulotni taqdim etish ham, qiymat argumenti
ham KERAK EMAS — mijoz nima olishini o'zi biladi va allaqachon oldi.

Agar bunday qo'ng'iroq to'liq savdo skripti bo'yicha tekshirilsa,
xodim aybsiz holda 40–50 ball oladi: u hamma ishni to'g'ri qilgan,
lekin rubrikaning yarmi shu suhbatga umuman tegishli emas. Ya'ni past
ball xodim haqida emas, RUBRIKA haqida gapiradi.

Yechim: taalluqli bo'lmagan mezon nol OLMAYDI, u umuman sanalmaydi va
ball QO'LLANILGAN mezonlar ichida hisoblanadi (`validator` ni qarang).

`optional: False` — har qanday suhbatga tushadigan mezon: salomlashish,
muomala madaniyati, savolga to'g'ri javob, kelishuvning aniqligi.
Bularni «taalluqli emas» deb belgilash mumkin emas, aks holda hech
narsa qolmasdi va har qo'ng'iroq 100 ball bo'lardi.
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
                    "optional": False,
                    "description": (
                        "«Assalomu alaykum, men [ism], Bonvi kompaniyasidan». "
                        "Tanish mijoz bilan to'liq tanishtirish shart emas — "
                        "xushmuomala salomlashish yetarli."
                    ),
                },
                {
                    "id": "A2",
                    "label": "Ehtiyojni aniqlash",
                    "points": 8,
                    "optional": True,
                    "description": (
                        "Ochiq savollar berdimi, mahsulot ehtiyojini so'radimi. "
                        "Mijoz o'zi aniq buyurtma aytgan bo'lsa (masalan «50 ta "
                        "chiqaring») — bu mezon TAALLUQLI EMAS."
                    ),
                },
                {
                    "id": "A3",
                    "label": "Mahsulotni to'g'ri taqdim etish",
                    "points": 7,
                    "optional": True,
                    "description": (
                        "Model, xususiyat va narx to'g'ri aytildi. Mijoz "
                        "mahsulotni allaqachon biladi va faqat qoldiq/narx "
                        "so'ragan bo'lsa — taalluqli emas."
                    ),
                },
                {
                    "id": "A4",
                    "label": "Keyingi qadam kelishildi",
                    "points": 5,
                    "optional": False,
                    "description": (
                        "Suhbat osilgan holda tugamadi: buyurtma tasdiqlandi, "
                        "sana aytildi yoki «qayta qo'ng'iroq qilaman» deyildi."
                    ),
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
                    "optional": False,
                    "description": "Siz'lash, xushmuomalalik",
                },
                {
                    "id": "B2",
                    "label": "Haqorat va so'kinish yo'q",
                    "points": 10,
                    "optional": False,
                    "description": "Buzilsa — umumiy ball 0 ga tushadi",
                },
                {
                    "id": "B3",
                    "label": "Client'ni bo'lmadi",
                    "points": 4,
                    "optional": False,
                    "description": "Overlap va bo'lish soni akustik tahlildan olinadi",
                },
                {
                    "id": "B4",
                    "label": "Ovoz toni mos",
                    "points": 3,
                    "optional": False,
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
                    "optional": False,
                    "description": (
                        "Ma'lumot aniq va to'liq. Qisqa suhbatda ham shu mezon "
                        "ishlaydi: mijoz nima so'ragan bo'lsa, javob olganmi."
                    ),
                },
                {
                    "id": "C2",
                    "label": "E'tirozlarni ishlab chiqdi",
                    "points": 8,
                    "optional": True,
                    "description": (
                        "Narx, muddat, sifat e'tirozlariga javob. Mijoz e'tiroz "
                        "bildirmagan bo'lsa — taalluqli emas."
                    ),
                },
                {
                    "id": "C3",
                    "label": "Mos taklif berdi",
                    "points": 7,
                    "optional": True,
                    "description": (
                        "Mahsulot client ehtiyojiga to'g'ri keldi. Mijoz aniq "
                        "mahsulotni o'zi so'ragan bo'lsa — taalluqli emas."
                    ),
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
                    "optional": True,
                    "description": (
                        "«Nechta olamiz?» — suhbat osilgan holda tugamadi. "
                        "Mijozning o'zi buyurtma bergan bo'lsa, yopish "
                        "allaqachon bo'lgan — taalluqli emas."
                    ),
                },
                {
                    "id": "D2",
                    "label": "Upsell / cross-sell",
                    "points": 6,
                    "optional": True,
                    "description": (
                        "Qo'shimcha model yoki miqdor taklif qilindi. Bir "
                        "daqiqalik qoldiq/narx so'rovida taalluqli emas."
                    ),
                },
                {
                    "id": "D3",
                    "label": "Aniq keyingi qadam",
                    "points": 6,
                    "optional": False,
                    "description": (
                        "«Payshanba qo'ng'iroq qilaman», «ertaga jo'natamiz» — "
                        "mavhum emas, aniq."
                    ),
                },
                {
                    "id": "D4",
                    "label": "Qiymat argumenti",
                    "points": 5,
                    "optional": True,
                    "description": (
                        "Nega aynan hozir olish kerakligi asoslandi. Mijoz "
                        "allaqachon sotib olayotgan bo'lsa — taalluqli emas."
                    ),
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
