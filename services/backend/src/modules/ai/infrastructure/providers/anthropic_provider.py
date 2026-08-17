"""Anthropic Claude — rasmiy `anthropic` SDK bilan.

Qarorlar:
  • Standart model — `claude-opus-5`.
  • Uzun javoblar uchun **streaming** (`messages.stream()` +
    `get_final_message()`): baholash javobi 1000+ token bo'ladi,
    streaming'siz HTTP timeout xavfi bor.
  • `thinking` parametri ATAYLAB yuborilmaydi: admin model nomini qo'lda
    kiritishi mumkin, har bir model uchun to'g'ri `thinking` shakli har xil
    (`adaptive` yangi modellarda, eski modellarda 400 beradi). Modelning
    o'z standarti eng xavfsiz tanlov.
  • Strukturali javob `output_config.format` orqali `extra_body` bilan
    yuboriladi — SDK versiyasi eski bo'lsa ham so'rov tanasiga tushadi.
"""

from typing import Any

from src.modules.ai.domain.errors import AIError, sdk_missing
from src.modules.ai.infrastructure.providers.base import BaseClient


class AnthropicLLMClient(BaseClient):
    sdk_package = "anthropic"

    def _build_sdk(self) -> Any:
        try:
            from anthropic import AsyncAnthropic
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise sdk_missing(self.label, self.sdk_package) from exc

        kwargs: dict[str, Any] = {
            "api_key": self._config.api_key,
            "timeout": self._config.timeout,
            "max_retries": 1,
        }
        if self._config.provider.base_url:
            kwargs["base_url"] = self._config.provider.base_url
        if self._config.http_client is not None:
            kwargs["http_client"] = self._config.http_client
        return AsyncAnthropic(**kwargs)

    async def list_models(self) -> list[str]:
        """`GET /v1/models` — Anthropic'da hammasi matn modeli, filtr shart emas."""
        client = self._build_sdk()
        try:
            page = await client.models.list(limit=100)
            return [str(getattr(m, "id", "") or "") for m in page.data if getattr(m, "id", None)]
        except Exception:  # noqa: BLE001 — ro'yxat olinmasa zaxiraga qaytamiz
            return []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        client = self._build_sdk()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema:
            kwargs["extra_body"] = {
                "output_config": {"format": {"type": "json_schema", "schema": schema}}
            }
        try:
            async with client.messages.stream(**kwargs) as stream:
                message = await stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 — o'zbekchaga tarjima qilinadi
            raise self._fail(exc) from None
        return self._text_of(message)

    async def ping(self) -> str:
        client = self._build_sdk()
        try:
            message = await client.messages.create(
                model=self.model,
                # Yangi modellarda «thinking» sukut bo'yicha yoqiq va u ham
                # shu chegaradan yeydi — shuning uchun 8 emas, 1024.
                max_tokens=1024,
                messages=[{"role": "user", "content": "Javob: OK"}],
            )
        except Exception as exc:  # noqa: BLE001
            raise self._fail(exc) from None
        return self._text_of(message) or "OK"

    def _text_of(self, message: Any) -> str:
        if getattr(message, "stop_reason", None) == "refusal":
            raise AIError(
                f"{self.label} bu so'rovni bajarishdan bosh tortdi "
                "(xavfsizlik filtri) — matnni qayta ko'rib chiqing"
            )
        parts = [
            str(getattr(block, "text", "") or "")
            for block in (getattr(message, "content", None) or ())
            if getattr(block, "type", None) == "text"
        ]
        return "".join(parts).strip()
