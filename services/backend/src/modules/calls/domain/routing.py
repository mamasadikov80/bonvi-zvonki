"""Qo'ng'iroq turini RAQAM bo'yicha aniqlash — sof Python, bazasiz.

Bitta savolga javob beradi: **suhbatdosh bizning odamimizmi?**

  · ha  → `INTERNAL` — ikki xodim o'zaro gaplashdi, savdo rubrikasi
          qo'llanmaydi (lekin transkript baribir olinadi);
  · yo'q → `SALES`   — suhbat tashqariga chiqdi, ya'ni baholanadi.

⚠️ NEGA MAZMUN EMAS, RAQAM. Ilgari turni LLM transkriptdan topardi va
YANGLISHARDI: mijozlarning aksariyati eski mijoz bo'lgani uchun ular ham
«qoldiq qancha», «narxlar qanaqa» deb qisqa gaplashadi. Matn jihatidan
bu hamkasb suhbatidan farq qilmaydi, model esa ikkilanganda «ichki» deb
qo'yardi. O'lchandi: tasniflangan 98 qo'ng'iroqning 82 tasi «ichki»,
savdo esa atigi 9 ta bo'lib chiqqan — ya'ni haqiqiy savdo suhbatlarining
ko'pi baholanmay qolgan.

Raqam esa taxmin emas: kompaniyaning liniyalari ma'lum (`agent_number`
ustuni har qo'ng'iroqda qaysi o'z raqamimizdan gaplashilganini yozib
boradi). Ikki tomon ham shu ro'yxatda bo'lsa — bu ichki suhbat, boshqa
o'qish mumkin emas.
"""

import re
from dataclasses import dataclass

from src.modules.calls.domain.entities import CallType

#: Solishtirish kaliti — oxirgi 9 raqam.
#
# O'zbekiston raqami: mamlakat kodi (998) + operator kodi (90) + 7 raqam.
# Mamlakat kodisiz aynan 9 ta raqam qoladi va u yagona. Raqam bizga uch
# ko'rinishda keladi — «+998 99 793-87-00», «998997938700», «997938700» —
# uchalasi ham bitta kalitga tushishi kerak.
PHONE_KEY_DIGITS = 9

#: Shundan qisqa raqam — ICHKI RAQAM (ATS ichidagi qisqa nomer).
#
# Bunday raqamga tashqaridan qo'ng'iroq qilib bo'lmaydi, ya'ni u
# ta'rifi bo'yicha kompaniya ichidagi liniya. Bazada bunday qatorlar
# bor (to'rt raqamli qiymatlar), ular tashqi mijoz bo'lishi MUMKIN
# EMAS.
#
# ⚠️ Chegara 7 da: 7 raqamli qiymat — Toshkent shahar telefoni
# («71» kodisiz yozilgani), ya'ni tashqi raqam bo'lishi mumkin.
EXTENSION_MAX_DIGITS = 6

_NON_DIGITS = re.compile(r"[^0-9]")


def phone_key(value: str | None) -> str | None:
    """Raqamni solishtirish kalitiga aylantiradi (oxirgi 9 raqam).

    `None` — raqam yo'q yoki kalit yasash uchun juda qisqa. Qisqa
    raqamni «kalit» deb olish XAVFLI: «1234567» istalgan raqamning
    oxiriga mos kelib, begona suhbatni ichki deb belgilab qo'yardi.
    """
    digits = _NON_DIGITS.sub("", value or "")
    if len(digits) < PHONE_KEY_DIGITS:
        return None
    return digits[-PHONE_KEY_DIGITS:]


def is_extension(value: str | None) -> bool:
    """ATS ichidagi qisqa raqammi (masalan «1042»).

    Bo'sh qiymat ichki raqam EMAS: raqamsiz qo'ng'iroq haqida hech
    narsa bilmaymiz va uni ichki deb belgilash — baholashdan asossiz
    chetlatish degani.
    """
    digits = _NON_DIGITS.sub("", value or "")
    return 0 < len(digits) <= EXTENSION_MAX_DIGITS


@dataclass(frozen=True, slots=True)
class CompanyLines:
    """Kompaniyaning o'z raqamlari — ikki ko'rinishda.

    `keys` — aniq raqamlar (`phone_key` shaklida). Ular ishning o'zidan
    o'rganiladi va taxmin emas.

    `suffixes` — raqam OXIRI bo'yicha qoida, masalan `700`. Kompaniyalar
    odatda operatordan ketma-ket raqamlar blokini oladi va bu blok
    yagona belgiga ega bo'ladi.

    ⚠️ NEGA SUFFIKS KERAK. Bonvi ma'lumotida o'lchandi: xodimlarning
    bir qismi MoyZvonki'da alohida foydalanuvchi EMAS (asosiy ombor,
    logistika, rejalashtirish, buxgalteriya, transport bo'limi) —
    ularning raqami hech qachon `src_number` bo'lib kelmaydi, ya'ni
    o'z-o'zidan o'rganilmaydi. Shunga qaramay ularning hammasi bitta
    blokdan: `…700`. Suffiks qoidasisiz shu bo'limlar bilan bo'lgan
    908 ta suhbat «savdo» deb baholanardi — pul ketardi va xodimlarning
    o'rtachasi asossiz tushardi.

    Suffiks — ADMIN qo'yadigan qoida, kodda qotirilmagan: raqamlash
    tartibi har kompaniyada boshqacha.
    """

    keys: frozenset[str] = frozenset()
    suffixes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.keys or self.suffixes)

    def matches(self, digits: str) -> bool:
        if not digits:
            return False
        if digits[-PHONE_KEY_DIGITS:] in self.keys:
            return True
        return any(digits.endswith(suffix) for suffix in self.suffixes)


def resolve_type(client_phone: str | None, lines: CompanyLines) -> CallType:
    """Suhbatdosh raqamiga qarab turni qaytaradi.

    ⚠️ Noma'lum holatda `SALES` qaytadi va bu ATAYLAB shunday. Ikki
    xatoning narxi teng emas:

      · noto'g'ri «ichki» — savdo suhbati jimgina baholanmay qoladi va
        buni hech kim sezmaydi (ro'yxatda ham ko'rinmaydi, chunki
        sukut bo'yicha savdo filtri yoqilgan);
      · noto'g'ri «savdo» — ichki suhbat baholanadi, bali past chiqadi.
        Bu KO'RINADI: menejer transkriptni ochib «bu hamkasb suhbati»
        deb aytadi va raqamni ro'yxatga qo'shish mumkin.

    Ko'rinadigan xato jimgina xatodan yaxshiroq.
    """
    if is_extension(client_phone):
        return CallType.INTERNAL
    digits = _NON_DIGITS.sub("", client_phone or "")
    if len(digits) >= PHONE_KEY_DIGITS and lines.matches(digits):
        return CallType.INTERNAL
    return CallType.SALES


def reason_uz(call_type: CallType, client_phone: str | None) -> str:
    """Qaror sababi — menejer o'qiydigan bitta jumla.

    Sabab har doim yoziladi: qo'lda tuzatish yo'q, shuning uchun qaror
    hech bo'lmasa TUSHUNTIRILGAN bo'lishi kerak.
    """
    raqam = (client_phone or "").strip() or "raqamsiz"
    if call_type is CallType.INTERNAL:
        if is_extension(client_phone):
            return f"{raqam} — ATS ichki raqami, ya'ni kompaniya ichidagi suhbat"
        return f"{raqam} — kompaniyaning o'z liniyasi, ikkala tomon ham xodim"
    return f"{raqam} — kompaniya liniyalari ro'yxatida yo'q, ya'ni tashqi suhbat"
