"""Har handler'ga umumiy xizmatlarni uzatuvchi middleware.

Barcha klientlar butun jarayon davomida BITTA nusxada yashaydi
(HTTP ulanish havzasi, Redis ulanishi, throttle uyachalari) —
shuning uchun ular handler ichida yaratilmaydi, shu yerdan beriladi.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services.api import ApiClient
from src.services.binding import AgentBinder
from src.services.internal_api import InternalApiClient
from src.services.registry import GroupSurveyRegistry
from src.services.throttle import CounterThrottle


class ApiMiddleware(BaseMiddleware):
    """Handler'lar `api`, `internal`, `registry`, `throttle`, `binder` ni shu yerdan oladi."""

    def __init__(
        self,
        api: ApiClient,
        internal: InternalApiClient,
        registry: GroupSurveyRegistry,
        throttle: CounterThrottle,
        binder: AgentBinder,
    ) -> None:
        self._api = api
        self._internal = internal
        self._registry = registry
        self._throttle = throttle
        self._binder = binder

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["api"] = self._api
        data["internal"] = self._internal
        data["registry"] = self._registry
        data["throttle"] = self._throttle
        data["binder"] = self._binder
        return await handler(event, data)
