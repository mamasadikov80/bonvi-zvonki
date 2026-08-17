"""Sozlamalardan MoyZvonki klientini yig'adi.

Sozlama kalitlari `SETTINGS_REGISTRY` da allaqachon bor:
`moizvonki.domain`, `moizvonki.user`, `moizvonki.api_key`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.moizvonki.domain.entities import (
    MoizvonkiCredentials,
    MoizvonkiNotConfiguredError,
    normalise_base_url,
)
from src.modules.moizvonki.infrastructure.client import MoizvonkiClient
from src.modules.settings.application.services import SettingsService

DOMAIN_KEY = "moizvonki.domain"
USER_KEY = "moizvonki.user"
API_KEY = "moizvonki.api_key"

_LABEL_UZ = {
    DOMAIN_KEY: "Domen",
    USER_KEY: "Foydalanuvchi (email)",
    API_KEY: "API kaliti",
}


async def load_credentials(session: AsyncSession) -> MoizvonkiCredentials:
    """Sozlamalarni o'qiydi. To'ldirilmagan bo'lsa — 503 va aniq xabar."""
    values = await SettingsService(session).get_all_values()

    raw = {key: str(values.get(key) or "").strip() for key in _LABEL_UZ}
    missing = [_LABEL_UZ[key] for key, value in raw.items() if not value]
    if missing:
        raise MoizvonkiNotConfiguredError(
            "MoyZvonki sozlanmagan — Sozlamalar → MoyZvonki bo'limida "
            f"to'ldiring: {', '.join(missing)}"
        )

    return MoizvonkiCredentials(
        base_url=normalise_base_url(raw[DOMAIN_KEY]),
        user_name=raw[USER_KEY],
        api_key=raw[API_KEY],
    )


@asynccontextmanager
async def moizvonki_client(session: AsyncSession) -> AsyncIterator[MoizvonkiClient]:
    """Klientni ochadi va ishlatilib bo'lgach yopadi.

    Audio ko'prigida oqim javob qaytgandan keyin ham davom etadi —
    u yerda `AsyncExitStack` bilan qo'lda boshqariladi.
    """
    credentials = await load_credentials(session)
    client = MoizvonkiClient(credentials)
    try:
        yield client
    finally:
        await client.aclose()
