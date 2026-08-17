"""Anonimlik — loyihaning buzilmas qoidasi.

Guruhda kim qanday baho qo'yganini HECH KIM bila olmasligi kerak: na
savdo xodimi, na admin, na backend, na loglarni o'qigan odam. Shuning
uchun Telegram ID bot jarayonidan TASHQARIGA CHIQMAYDI — u faqat shu
faylda, faqat hash hisoblash uchun ishlatiladi.

    respondent_hash = sha256(f"{token}:{telegram_user_id}")[:64]

Nega token hash ichida?
  Agar hash faqat ID dan olinsa, bitta odamning turli so'rovnomalardagi
  javoblari bir xil hash'ga ega bo'lardi va ularni bir-biriga bog'lab,
  "shu odam har safar 2 qo'yadi" degan profil tuzish mumkin bo'lardi.
  Har so'rovnomaning tokeni har xil — shuning uchun hash'lar ham har xil
  va bog'lanmaydi.

Nega qaytarib bo'lmaydi?
  sha256 bir tomonlama. Telegram ID lar oralig'i katta (~10^10), lekin
  token bilan birga "tuz" (salt) vazifasini bajaradi: tokenni bilmagan
  odam lug'at hujumi ham qura olmaydi.

Bu funksiya HECH QACHON log yozmaydi va chaqiruvchi ham xom ID ni
logga chiqarmasligi shart.
"""

import hashlib

# Shartnomadagi uzunlik. sha256 hexdigest allaqachon 64 belgi — kesish
# hech narsani o'zgartirmaydi, lekin shartnoma matniga aynan mos tursin
# va backend ustuni String(64) ekani kod orqali ham ko'rinib tursin.
HASH_LENGTH = 64


def respondent_hash(token: str, telegram_user_id: int) -> str:
    """Javob beruvchining qaytarib bo'lmaydigan belgisi.

    Backend'ga FAQAT shu qiymat yuboriladi.
    """
    raw = f"{token}:{telegram_user_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:HASH_LENGTH]


def short(digest: str) -> str:
    """Diagnostika uchun hash'ning qisqartmasi (log uchun xavfsiz).

    To'liq hash ham logga tushmasligi ma'qul: u backend'dagi qator bilan
    solishtirilsa, kim qachon baho berganini taxmin qilish oson bo'lardi.
    """
    return f"{digest[:8]}…" if digest else "—"
