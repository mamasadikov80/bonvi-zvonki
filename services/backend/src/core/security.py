"""Parol xeshlash va JWT tokenlar."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt

from src.core.config import settings

ACCESS = "access"
REFRESH = "refresh"

# bcrypt 72 baytdan uzun parolni qabul qilmaydi
_MAX_BYTES = 72


def _encode(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Parolni xesh bilan solishtiradi. Buzuq xeshda `False`, xato EMAS.

    ⚠️ `except Exception` ataylab keng olingan, `(ValueError, TypeError)`
    emas. `bcrypt` kutubxonasining yadrosi Rust'da yozilgan va bcrypt'ga
    O'XSHAB boshlanadigan, ammo kesilgan qator uchun (`$2b$12$qisqa`)
    `pyo3_runtime.PanicException` beradi. U `Exception` dan emas,
    to'g'ridan-to'g'ri `BaseException` dan meros oladi — ya'ni tor
    `except` uni ushlamaydi.

    Oqibati og'ir edi: `users.password_hash` ustunida bitta buzuq qator
    bo'lsa (migratsiya, qo'lda `UPDATE`, yarim ko'chirilgan baza),
    `POST /auth/login` 401 o'rniga 500 bilan QULARDI — ya'ni bitta
    buzuq yozuv butun kirishni ishdan chiqarardi.

    Bu yerda har qanday nosozlik «parol to'g'ri kelmadi» degani: xeshni
    tekshirib bo'lmasa, foydalanuvchini kiritish mumkin emas.
    """
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except BaseException:  # noqa: BLE001 — sababi yuqorida
        return False


def _create_token(subject: UUID | str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: UUID | str) -> str:
    return _create_token(
        subject, ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: UUID | str) -> str:
    return _create_token(
        subject, REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: str = ACCESS) -> UUID | None:
    """Tokenni tekshiradi. Yaroqsiz bo'lsa None qaytaradi."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.PyJWTError:
        return None

    if payload.get("type") != expected_type:
        return None

    subject = payload.get("sub")
    if not subject:
        return None

    try:
        return UUID(subject)
    except ValueError:
        return None
