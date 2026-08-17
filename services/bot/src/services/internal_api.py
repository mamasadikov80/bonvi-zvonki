"""Guruh so'rovnomalari uchun ichki backend klienti.

`config_client.py` dagi bilan bir xil naqsh: bot foydalanuvchi emas,
shuning uchun JWT o'rniga `X-Internal-Token` sarlavhasi ishlatiladi
(kalit `.env` → `INTERNAL_API_TOKEN`).

Shartnomadagi endpointlar (GROUPS_CONTRACT.md, 3-bo'lim):

    POST /agents/enroll              → xodimni raqami bo'yicha topish
    POST /groups/autobind            → guruhga xodimni avtomatik biriktirish
    POST /groups/register            → guruhni ro'yxatga olish (upsert)
    GET  /groups/pending-surveys     → yuborilmagan so'rovnomalar
    POST /surveys/{token}/sent       → guruhdagi xabar id sini qaytarish
    POST /surveys/{token}/rate       → ball (faqat hash bilan)
    POST /surveys/{token}/detail     → izoh + red flag (faqat hash bilan)
    GET  /surveys/red-flags          → sabablar ro'yxati (kalit + yorliq)

Tarmoq xatosi va 404 — kutilgan holat: backend hali ko'tarilmagan yoki
endpoint hali chiqarilmagan bo'lishi mumkin. Bunday paytda istisno
ko'tarilmaydi, `None`/bo'sh qiymat qaytadi va bot ishlashda davom etadi.
Ogohlantirish har xil endpoint uchun BIR MARTA yoziladi — aks holda
60 soniyalik poller loglarni ko'mib tashlaydi.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


def _text(value: Any) -> str | None:
    """JSON dagi qiymatni bo'sh bo'lmagan satrga keltiradi (yoki None)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True, slots=True)
class RateResult:
    """`POST /surveys/{token}/rate` javobi."""

    accepted: bool
    response_count: int
    already_rated: bool


@dataclass(frozen=True, slots=True)
class EnrollResult:
    """`POST /agents/enroll` javobi.

    `matched=False` — xato emas: shunday raqamli xodim yo'q. Bot
    xushmuomala javob beradi va hech narsa saqlamaydi.
    """

    matched: bool
    agent_id: str | None
    full_name: str | None
    bound_groups: int


@dataclass(frozen=True, slots=True)
class AutobindResult:
    """`POST /groups/autobind` javobi.

    `kind` maydonini bot O'QIMAYDI: guruh ishchimi yoki keraksizmi —
    buni a'zolar soniga qarab hal qilib bo'lmaydi va bot hal qilmaydi.
    """

    bound: bool
    agent_id: str | None
    agent_name: str | None
    region: str | None
    reason: str


class DetailOutcome(str, Enum):
    """`POST /surveys/{token}/detail` natijasi."""

    OK = "ok"
    # 409 — bu hash hali guruhda ball qo'ymagan
    NOT_RATED = "not_rated"
    # Tarmoq/serverdagi vaqtinchalik muammo — qayta urinib ko'rish mumkin
    FAILED = "failed"


class InternalApiClient:
    """Ichki (bot ↔ backend) endpointlar uchun yupqa klient."""

    def __init__(self, base_url: str | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=(base_url or settings.API_BASE_URL) + "/api/v1",
            timeout=10.0,
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        # Takrorlanadigan ogohlantirishlarni bosish uchun
        self._warned: set[str] = set()
        # Red flag ro'yxati keshi: (olingan_vaqt, ro'yxat)
        self._flags_cache: tuple[float, list[tuple[str, str]]] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    # ── Xodimni ro'yxatdan o'tkazish ──────────────────────────

    async def enroll(
        self,
        phone: str,
        telegram_user_id: int,
        telegram_username: str | None,
    ) -> EnrollResult | None:
        """Xodimni telefon raqami bo'yicha topadi va Telegram id ni bog'laydi.

        Raqamni NORMALLASHTIRISH backend'da bo'ladi (oxirgi 9 raqam
        bo'yicha solishtiriladi) — bot uni xom holda uzatadi, chunki
        ikki joyda ikki xil normallashtirish qoidasi paydo bo'lishi
        eng oson buziladigan narsa.

        Bu YAGONA joy: raqam shu chaqiruvdan boshqa hech qayerga
        (logga ham, Redis'ga ham) tushmaydi.
        """
        payload = {
            "phone": phone,
            "telegram_user_id": telegram_user_id,
            "telegram_username": telegram_username,
        }
        data = await self._post_json("/agents/enroll", payload, what="agents/enroll")
        if data is None:
            return None
        return EnrollResult(
            matched=bool(data.get("matched")),
            agent_id=_text(data.get("agent_id")),
            full_name=_text(data.get("full_name")),
            bound_groups=int(data.get("bound_groups") or 0),
        )

    # ── Guruhlar ──────────────────────────────────────────────

    async def autobind_group(
        self,
        chat_id: int,
        title: str,
        member_count: int | None,
        bot_status: str,
        candidate_user_ids: list[int],
    ) -> AutobindResult | None:
        """Guruhdagi nomzodlarni backend'ga aytadi.

        Backend ularni ro'yxatdan o'tgan xodimlar bilan solishtiradi.
        Mos kelgani bo'lsa guruh o'sha xodimga biriktiriladi.

        `member_count` PANEL uchun yuboriladi — guruhni tasniflash
        uchun emas.
        """
        payload = {
            "chat_id": chat_id,
            "title": title,
            "member_count": member_count,
            "bot_status": bot_status,
            "candidate_user_ids": candidate_user_ids,
        }
        data = await self._post_json(
            "/groups/autobind", payload, what="groups/autobind"
        )
        if data is None:
            return None
        return AutobindResult(
            bound=bool(data.get("bound")),
            agent_id=_text(data.get("agent_id")),
            agent_name=_text(data.get("agent_name")),
            region=_text(data.get("region")),
            reason=str(data.get("reason") or ""),
        )

    async def register_group(
        self,
        chat_id: int,
        title: str,
        member_count: int | None,
        bot_status: str,
    ) -> dict[str, Any] | None:
        """Guruhni backend'ga yozadi (bo'lsa yangilaydi, bo'lmasa yaratadi).

        Admin panelida guruh shu chaqiruvdan keyin ko'rinadi — admin
        chat id ni qo'lda kiritmaydi.
        """
        payload = {
            "chat_id": chat_id,
            "title": title,
            "member_count": member_count,
            "bot_status": bot_status,
        }
        return await self._post_json("/groups/register", payload, what="groups/register")

    async def pending_surveys(self) -> list[dict[str, Any]]:
        """Guruhga yuborilishi kerak bo'lgan so'rovnomalar."""
        data = await self._get_json(
            "/groups/pending-surveys", what="groups/pending-surveys"
        )
        return data if isinstance(data, list) else []

    # ── So'rovnoma ────────────────────────────────────────────

    async def live_surveys(self) -> list[dict[str, Any]]:
        """Yuborilgan so'rovnomalar va ulardagi javoblar soni.

        Mini App rejimida baho backendga to'g'ridan-to'g'ri tushadi —
        bot uni ko'rmaydi. Guruhdagi hisoblagich yangilanib turishi
        uchun shu ro'yxat davriy o'qiladi.
        """
        data = await self._get_json("/groups/live-surveys", what="jonli so'rovnomalar")
        return data if isinstance(data, list) else []

    async def expired_survey_messages(self) -> list[dict[str, Any]]:
        """Guruhdan o'chirilishi kerak bo'lgan so'rovnoma xabarlari.

        ⚠️ Bot O'CHIRISH UCHUN NIMANI TANLASHINI O'ZI HAL QILMAYDI.
        Ro'yxat backenddan keladi va unda faqat botning o'zi yuborgan,
        `mark_sent` bilan qayd etilgan xabarlar bo'ladi. Bot guruh
        tarixini o'qimaydi va hech qanday xabarni «so'rovnomaga
        o'xshaydi» deb taxmin qilmaydi — shu sababli boshqa dastur
        yuborgan xabarga hech qachon tegmaydi.
        """
        data = await self._get_json(
            "/groups/expired-survey-messages", what="muddati o'tgan xabarlar"
        )
        return data if isinstance(data, list) else []

    async def mark_message_deleted(self, token: str) -> bool:
        """«Bu xabar bilan ish tugadi» — yozuv navbatdan chiqadi."""
        result = await self._post_json(
            f"/groups/surveys/{token}/message-deleted",
            {},
            what="xabar o'chirildi belgisi",
        )
        return result is not None

    async def mark_sent(self, token: str, chat_message_id: int) -> bool:
        """Guruhdagi xabar id sini backend'ga qaytaradi (tahrirlash uchun)."""
        result = await self._post_json(
            f"/surveys/{token}/sent",
            {"chat_message_id": chat_message_id},
            what="surveys/sent",
        )
        return result is not None

    async def rate(
        self, token: str, respondent_hash: str, csat: int
    ) -> RateResult | None:
        """Ballni yuboradi. Backend Telegram ID ni umuman ko'rmaydi.

        Bir xil hash ikkinchi marta kelsa xato emas: 200 qaytadi,
        `already_rated=true` bilan (shartnoma, 3-bo'lim).
        """
        data = await self._post_json(
            f"/surveys/{token}/rate",
            {"respondent_hash": respondent_hash, "csat": csat},
            what="surveys/rate",
        )
        if data is None:
            return None
        return RateResult(
            accepted=bool(data.get("accepted")),
            response_count=int(data.get("response_count") or 0),
            already_rated=bool(data.get("already_rated")),
        )

    async def send_detail(
        self,
        token: str,
        respondent_hash: str,
        comment: str | None,
        red_flags: list[str],
    ) -> DetailOutcome:
        """Izoh va red flag'larni yuboradi.

        MUHIM: bu funksiya ataylab "yupqa" — u faqat to'rtta qiymatni
        oladi va HTTP ga o'giradi, hech qanday Telegram tushunchasiga
        bog'lanmagan. Kelajakda izoh shaxsiy chat o'rniga veb-sahifada
        (Mini App) yozilsa, o'sha yo'l ham AYNAN shu funksiyani va
        aynan shu endpointni qayta ishlatadi — qayta yozish kerak emas.
        """
        body = {
            "respondent_hash": respondent_hash,
            "comment": comment,
            "red_flags": red_flags,
        }
        try:
            response = await self._client.post(f"/surveys/{token}/detail", json=body)
        except httpx.HTTPError as exc:
            self._warn_once("surveys/detail", "so'rov ketmadi: %s", exc)
            return DetailOutcome.FAILED

        if response.status_code in (200, 201):
            return DetailOutcome.OK
        if response.status_code == 409:
            # Bu xato emas: odam hali guruhda ball qo'ymagan
            return DetailOutcome.NOT_RATED

        self._warn_once(
            "surveys/detail", "kutilmagan javob %s", response.status_code
        )
        return DetailOutcome.FAILED

    async def red_flags(self) -> list[tuple[str, str]]:
        """Sabablar ro'yxati: [(kalit, yorliq), ...].

        Ro'yxat BOTDA YOZILMAGAN — backend beradi. Shu sababli yangi
        mezon qo'shish uchun botni qayta yig'ish shart emas.
        Kesh TTL bilan: har bosishda HTTP so'rov ketmasin.
        """
        now = time.monotonic()
        if self._flags_cache is not None:
            fetched_at, cached = self._flags_cache
            if now - fetched_at < settings.RED_FLAGS_TTL_SECONDS:
                return cached

        data = await self._get_json("/surveys/red-flags", what="surveys/red-flags")
        if not isinstance(data, list):
            # Backend javob bermadi — eski keshni ishlatamiz (bo'lsa)
            return self._flags_cache[1] if self._flags_cache else []

        flags: list[tuple[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            label = str(item.get("label") or "").strip()
            if key and label:
                flags.append((key, label))

        self._flags_cache = (now, flags)
        return flags

    # ── Umumiy yordamchilar ───────────────────────────────────

    async def _get_json(self, path: str, *, what: str) -> Any | None:
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            self._warn_once(what, "so'rov ketmadi: %s", exc)
            return None
        return self._read(response, what)

    async def _post_json(
        self, path: str, payload: dict[str, Any], *, what: str
    ) -> dict[str, Any] | None:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            self._warn_once(what, "so'rov ketmadi: %s", exc)
            return None
        data = self._read(response, what)
        return data if isinstance(data, dict) else None

    def _read(self, response: httpx.Response, what: str) -> Any | None:
        if response.status_code in (200, 201):
            self._warned.discard(what)
            try:
                return response.json()
            except ValueError:
                self._warn_once(what, "javob JSON emas")
                return None

        if response.status_code == 401:
            self._warn_once(
                what,
                "backend ichki kalitni qabul qilmadi (401) — "
                ".env dagi INTERNAL_API_TOKEN bot va backend uchun bir xil bo'lsin",
            )
        elif response.status_code == 404:
            self._warn_once(
                what,
                "endpoint hali yo'q (404) — backend chiqarilishini kutamiz",
            )
        else:
            self._warn_once(what, "kutilmagan javob %s", response.status_code)
        return None

    def _warn_once(self, what: str, message: str, *args: Any) -> None:
        """Bir xil muammo haqida bir marta ogohlantirish.

        Holat tuzalgach (`_read` dagi `discard`) belgisi tozalanadi va
        keyingi buzilishda yana bir marta yoziladi.
        """
        if what in self._warned:
            logger.debug("%s: " + message, what, *args)
            return
        self._warned.add(what)
        logger.warning("⚠️  %s: " + message, what, *args)
