"""Savdo xodimi domeni — sof Python, bazani ham, FastAPI'ni ham bilmaydi.

Hozircha bitta mas'uliyat: **telefon raqamini solishtirish**. Bu ko'ringandan
muhimroq — butun avtomatik biriktirish zanjiri shundan boshlanadi. Raqam
mos kelmasa xodim ro'yxatdan o'tmaydi, ro'yxatdan o'tmasa guruhlari
biriktirilmaydi, biriktirilmasa so'rovnoma ketmaydi. Va hech qayerda
xato chiqmaydi — hammasi jimgina ishlamay qoladi.
"""

import re

# Solishtirish uchun ishlatiladigan oxirgi raqamlar soni.
#
# O'zbekiston raqami: mamlakat kodi (998) + operator kodi (90) + 7 raqam.
# Ya'ni mamlakat kodisiz aynan 9 ta raqam qoladi va u yagona.
PHONE_MATCH_DIGITS = 9

# Faqat ASCII raqamlar. `str.isdigit()` ISHLATILMAYDI — u arabcha «٣»
# kabi belgilarni ham raqam deb biladi, ular esa bazadagi qiymatga
# hech qachon mos kelmaydi.
_NON_DIGITS = re.compile(r"[^0-9]")


def normalize_phone(value: str | None) -> str | None:
    """Raqamni solishtirish uchun kalitga aylantiradi (oxirgi 9 ta raqam).

    Raqam bizga uch xil manbadan, uch xil ko'rinishda keladi:

        "+998 90 123-45-67"  → admin panelda qo'lda kiritilgan
        "998901234567"       → Telegram `contact.phone_number`
        "901234567"          → MoyZvonki eksporti

    Uchalasi ham `"901234567"` ga aylanadi va bitta xodimga tushadi.

    9 tadan kam raqam qolsa `None` — bunday qiymat bilan solishtirish
    xavfli: "1234567" istalgan raqamning oxiriga mos kelib, bahoni
    boshqa xodimga yozib yuborishi mumkin.
    """
    if not value:
        return None
    digits = _NON_DIGITS.sub("", value)
    if len(digits) < PHONE_MATCH_DIGITS:
        return None
    return digits[-PHONE_MATCH_DIGITS:]
