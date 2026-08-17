"""Backend bilan aloqa."""

import logging
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class ApiClient:
    """Bot uchun backend klienti.

    Hozircha so'rovnoma endpointlari backend'da hali qurilmagan —
    metodlar mavjud, lekin 404 kelsa xatoni yutadi va None qaytaradi.
    Bu bot'ni backend'dan oldin ishga tushirish imkonini beradi.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=(base_url or settings.API_BASE_URL) + "/api/v1",
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def open_survey(self, token: str) -> dict[str, Any] | None:
        """Tokenni tekshiradi va so'rovnomani 'ochilgan' deb belgilaydi.

        ANONIMLIK: ilgari bu yerda `telegram_user_id` yuborilardi.
        Backend uni ataylab saqlamasa ham, ID jarayondan chiqib
        HTTP so'rovga, u yerdan esa proxy/kirish loglariga tushardi.
        Endi umuman yuborilmaydi — maydon backend'da ixtiyoriy.
        """
        try:
            response = await self._client.post(f"/surveys/{token}/open", json={})
            if response.status_code == 200:
                return response.json()
            logger.warning("open_survey: %s — %s", response.status_code, token)
        except httpx.HTTPError as exc:
            logger.error("open_survey xatosi: %s", exc)
        return None

    async def submit_survey(
        self,
        token: str,
        csat: int,
        resolution: str | None,
        comment: str | None,
    ) -> bool:
        try:
            response = await self._client.post(
                f"/surveys/{token}/submit",
                json={"csat": csat, "resolution": resolution, "comment": comment},
            )
            return response.status_code in (200, 201)
        except httpx.HTTPError as exc:
            logger.error("submit_survey xatosi: %s", exc)
            return False

    async def health(self) -> bool:
        try:
            response = await httpx.AsyncClient(timeout=5.0).get(
                f"{settings.API_BASE_URL}/health"
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
