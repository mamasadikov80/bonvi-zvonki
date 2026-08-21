"""MoyZvonki REST klienti.

Hujjat: https://www.moizvonki.ru/guide/api/

Talab qilinadigan shakl (hujjatdan aynan):
    POST https://<domen>.moizvonki.ru/api/v1
    Content-Type: application/json
    {"user_name": "...", "api_key": "...", "action": "calls.list", ...}

Hujjatda bitta ziddiyat bor: matn «Content-Type: application/json …
boshqa Content-Type bilan so'rov xato bilan tugaydi» deydi, ammo o'sha
sahifadagi jQuery misoli `$.post(url, {request_data: <json satri>})`
qiladi — bu form-urlencoded. Ikkalasi ham rasmiy sahifada bo'lgani
uchun klient avval JSON yuboradi, server uni tushunmasa (400/415/422)
bir marta `request_data` shaklida qayta uriniladi va ishlagan shakl
shu klient uchun eslab qolinadi. Taxmin qilinmagan — ikkala variant
ham hujjatdan olingan.

⚠️ Audio hech qachon diskka yozilmaydi va butunlay xotiraga
yig'ilmaydi: `open_recording()` `httpx` ning stream rejimida ishlaydi.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

from src.modules.moizvonki.domain.entities import (
    CallPage,
    MoizvonkiAuthError,
    MoizvonkiBadResponseError,
    MoizvonkiCall,
    MoizvonkiCredentials,
    MoizvonkiEmployee,
    MoizvonkiError,
    MoizvonkiUnreachableError,
    RangeNotSatisfiableError,
    RecordingNotFoundError,
    RecordingStream,
)

# Hujjat: max_results — ruxsat etilgan qiymat 1..100
log = structlog.get_logger(__name__)

MAX_RESULTS_LIMIT = 100

#: Vaqtinchalik uzilishda necha marta urinib ko'riladi.
#
# Uch marta yetarli: o'lchov ko'rsatdi, sekinlashish qisqa muddatli va
# ikkinchi urinish deyarli har doim o'tadi. Ko'proq urinish esa
# haqiqatan ishlamayotgan integratsiyada adminni bejiz kuttirardi.
RETRY_ATTEMPTS = 3

#: Birinchi kutish (soniya). Keyingilari ikki barobar: 2 → 4.
RETRY_BASE_SEC = 2.0

# Autentifikatsiya nosozligini javob matnidan taniydigan kalit so'zlar.
# MoyZvonki xatoni 200 dan farqli kod + tanadagi izoh bilan qaytaradi,
# lekin qaysi kod ekani hujjatda aytilmagan — shuning uchun matnga ham
# qaraymiz.
_AUTH_HINTS = (
    "auth",
    "api_key",
    "api key",
    "user_name",
    "login",
    "password",
    "permission",
    "forbidden",
    "авториз",
    "аутентиф",
    "ключ",
    "логин",
    "пароль",
    "доступ",
)

_STREAM_CHUNK = 64 * 1024


class MoizvonkiClient:
    """Bitta akkaunt uchun REST klienti.

    Ishlatish:
        async with MoizvonkiClient(creds) as client:
            page = await client.list_calls(since=..., until=...)
    """

    def __init__(
        self,
        credentials: MoizvonkiCredentials,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 10.0,
        stream_timeout: float = 300.0,
    ) -> None:
        self._creds = credentials
        self._stream_timeout = stream_timeout
        self._form_fallback = False  # `request_data` shakli kerakligi
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            follow_redirects=True,
            headers={"User-Agent": "BonviZvonki/1.0 (+bonvi)"},
        )

    # ── Hayot sikli ───────────────────────────────────────────

    async def __aenter__(self) -> "MoizvonkiClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── Maxfiylik ─────────────────────────────────────────────

    def _redact(self, text: str) -> str:
        """API kalit xato xabariga ham, logga ham tushmasin."""
        key = self._creds.api_key
        if key and len(key) >= 4:
            text = text.replace(key, "***")
        return text

    def _snippet(self, response: httpx.Response) -> str:
        try:
            body = response.text
        except Exception:  # noqa: BLE001 — tana o'qilmasa ham xato bermaymiz
            return ""
        return self._redact(" ".join(body.split()))[:300]

    # ── Past daraja ───────────────────────────────────────────

    def _payload(self, action: str, params: dict[str, object]) -> dict[str, object]:
        body: dict[str, object] = {
            "user_name": self._creds.user_name,
            "api_key": self._creds.api_key,
            "action": action,
        }
        body.update({k: v for k, v in params.items() if v is not None})
        return body

    async def _send(
        self, payload: dict[str, object], *, as_form: bool
    ) -> httpx.Response:
        if as_form:
            # Hujjatdagi jQuery misolining shakli
            return await self._http.post(
                self._creds.api_url,
                data={"request_data": json.dumps(payload, ensure_ascii=False)},
            )
        return await self._http.post(self._creds.api_url, json=payload)

    #: MoyZvonki'ga YUBORISH MUMKIN BO'LGAN yagona action lar.
    #
    # ⚠️ QAT'IY QOIDA: bu integratsiya FAQAT O'QIYDI. MoyZvonki —
    # mijozning ish tizimi; u yerda biror narsani o'zgartirish,
    # qo'shish yoki o'chirish bizning vakolatimizda EMAS.
    #
    # Qoida izohda emas, KODDA turadi: ro'yxatdan tashqari action
    # yuborishga urinish so'rov ketguncha xato bilan to'xtaydi.
    # Kimdir kelajakda `calls.add` yoki `company.update_employee`
    # yozib qo'ysa, u testda ham, ishlab turgan tizimda ham darhol
    # bilinadi — jimgina o'tib ketmaydi.
    #
    # MoyZvonki API si RPC uslubida: hamma so'rov HTTP `POST` bilan
    # ketadi, amal turi esa `action` maydonida. Shuning uchun «POST
    # ishlatilyapti» degan narsa yozuv degani EMAS — muhimi shu ro'yxat.
    READ_ONLY_ACTIONS = frozenset(
        {
            "calls.list",
            "company.list_group",
            "company.list_employee",
        }
    )

    async def _post(self, action: str, **params: object) -> dict:
        """So'rov yuboradi. Vaqtinchalik uzilishda QAYTA URINADI.

        ⚠️ NEGA QAYTA URINISH KERAK. Bitta sinxronizatsiya o'nlab,
        ba'zan yuzlab sahifa o'qiydi: 30 kunlik oraliqda ~250 so'rov,
        jami ~4 daqiqa. Odatda har sahifa ~1 soniyada keladi, lekin
        MoyZvonki ba'zida sekinlashadi va BITTA sahifa 30 soniyalik
        chegaradan chiqib ketadi.

        Qayta urinish bo'lmasa o'sha bitta sahifa BUTUN ishni
        yiqitadi: admin 4 daqiqa kutib, «MoyZvonki javob bermadi»
        degan xabar oladi va 20 000 qo'ng'iroq yozilmay qoladi.
        HAQIQIY sinovda aynan shunday bo'ldi — ikki marta.

        Faqat VAQT TUGASHI va tarmoq uzilishi qayta urinadi. Xato
        kalit yoki noto'g'ri javob qayta urinilmaydi: ular
        o'z-o'zidan tuzalmaydi va urinish faqat vaqt yo'qotardi.
        """
        oxirgi: Exception | None = None
        for urinish in range(RETRY_ATTEMPTS):
            try:
                return await self._post_once(action, **params)
            except MoizvonkiUnreachableError as exc:
                oxirgi = exc
                if urinish == RETRY_ATTEMPTS - 1:
                    break
                kutish = RETRY_BASE_SEC * (2**urinish)
                log.warning(
                    "moizvonki.retry",
                    action=action,
                    attempt=urinish + 1,
                    of=RETRY_ATTEMPTS,
                    sleep_sec=kutish,
                )
                await asyncio.sleep(kutish)
        assert oxirgi is not None
        raise oxirgi

    async def _post_once(self, action: str, **params: object) -> dict:
        if action not in self.READ_ONLY_ACTIONS:
            raise MoizvonkiError(
                f"MoyZvonki'ga «{action}» yuborilmadi: bu integratsiya faqat "
                "o'qish uchun. Ruxsat etilganlar: "
                f"{', '.join(sorted(self.READ_ONLY_ACTIONS))}"
            )

        payload = self._payload(action, params)

        try:
            response = await self._send(payload, as_form=self._form_fallback)
            # JSON shakli tushunilmadi — hujjatdagi ikkinchi shaklni sinaymiz
            if (
                not self._form_fallback
                and response.status_code in (400, 415, 422)
                and not self._looks_like_auth_failure(response)
            ):
                retry = await self._send(payload, as_form=True)
                if retry.status_code == 200:
                    self._form_fallback = True
                    response = retry
        except httpx.TimeoutException as exc:
            raise MoizvonkiUnreachableError(
                f"MoyZvonki javob bermadi (vaqt tugadi): {self._creds.host_label}"
            ) from exc
        except httpx.TransportError as exc:
            raise MoizvonkiUnreachableError(
                f"MoyZvonki serveriga ulanib bo'lmadi: {self._creds.host_label} "
                "— domenni va internet ulanishini tekshiring"
            ) from exc

        self._raise_for_status(response, action)

        try:
            data = response.json()
        except ValueError as exc:
            raise MoizvonkiBadResponseError(
                f"MoyZvonki JSON o'rniga tushunarsiz javob qaytardi "
                f"({action}): {self._snippet(response)}"
            ) from exc

        if not isinstance(data, dict):
            raise MoizvonkiBadResponseError(
                f"MoyZvonki javobi kutilgan shaklda emas ({action})"
            )
        return data

    def _looks_like_auth_failure(self, response: httpx.Response) -> bool:
        if response.status_code in (401, 403):
            return True
        return any(hint in self._snippet(response).lower() for hint in _AUTH_HINTS)

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        if response.status_code == 200:
            return

        if self._looks_like_auth_failure(response):
            raise MoizvonkiAuthError(
                "MoyZvonki avtorizatsiyadan o'tkazmadi — Sozlamalar → MoyZvonki "
                "bo'limidagi foydalanuvchi (email) va API kalitni tekshiring "
                f"(server javobi: {self._snippet(response)})"
            )

        if response.status_code in (502, 503, 504):
            raise MoizvonkiUnreachableError(
                f"MoyZvonki vaqtincha ishlamayapti (HTTP {response.status_code}): "
                f"{self._creds.host_label}"
            )

        raise MoizvonkiBadResponseError(
            f"MoyZvonki «{action}» so'roviga HTTP {response.status_code} qaytardi: "
            f"{self._snippet(response)}"
        )

    # ── Qo'ng'iroqlar ─────────────────────────────────────────

    async def list_calls(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        from_id: int | None = None,
        offset: int = 0,
        max_results: int = MAX_RESULTS_LIMIT,
        supervised: bool = True,
    ) -> CallPage:
        """Bir sahifa qo'ng'iroq (`calls.list`).

        Hujjat: `from_date` yoki `from_id` dan biri MAJBURIY.
        `supervised=1` — foydalanuvchi roli ko'rishga ruxsat bergan
        BARCHA xodimlarning qo'ng'iroqlari (bizga aynan shu kerak).
        """
        if since is None and from_id is None:
            raise MoizvonkiBadResponseError(
                "Qo'ng'iroqlarni olish uchun boshlanish sanasi kerak"
            )

        params: dict[str, object] = {
            "max_results": max(1, min(int(max_results), MAX_RESULTS_LIMIT)),
            "supervised": 1 if supervised else 0,
        }
        if from_id is not None:
            params["from_id"] = int(from_id)
        else:
            params["from_date"] = int(since.timestamp())  # type: ignore[union-attr]
        if until is not None:
            params["to_date"] = int(until.timestamp())
        if offset:
            params["from_offset"] = int(offset)

        data = await self._post("calls.list", **params)

        results = data.get("results")
        if results is None:
            results = []
        if not isinstance(results, list):
            raise MoizvonkiBadResponseError(
                "MoyZvonki `calls.list` javobida `results` ro'yxat emas"
            )

        calls = tuple(
            MoizvonkiCall.from_api(row) for row in results if isinstance(row, dict)
        )
        return CallPage(
            calls=calls,
            next_offset=_as_int(data.get("results_next_offset")),
            remains=_as_int(data.get("results_remains")),
            total_in_page=_as_int(data.get("results_count")) or len(calls),
        )

    async def iter_calls(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        supervised: bool = True,
        page_size: int = MAX_RESULTS_LIMIT,
        max_pages: int = 500,
    ) -> AsyncIterator[tuple[int, CallPage]]:
        """Barcha sahifalarni ketma-ket qaytaradi: `(sahifa_raqami, sahifa)`.

        Sahifalash hujjatdagidek `from_offset` / `results_next_offset`
        juftligi orqali. Cheksiz aylanishdan himoya: offset oldinga
        siljimasa yoki sahifa bo'sh kelsa — to'xtaymiz.
        """
        offset = 0
        for page_number in range(1, max_pages + 1):
            page = await self.list_calls(
                since=since,
                until=until,
                offset=offset,
                max_results=page_size,
                supervised=supervised,
            )
            yield page_number, page

            if not page.calls or not page.has_more:
                return
            if page.next_offset <= offset:
                # Server oldinga siljimadi — takrorlanishning oldini olamiz
                return
            offset = page.next_offset

    # ── Xodimlar ──────────────────────────────────────────────

    async def list_employees(
        self, *, max_results: int = MAX_RESULTS_LIMIT, max_pages: int = 50
    ) -> list[MoizvonkiEmployee]:
        """Barcha xodimlar (`company.list_employee`).

        Diqqat: hujjatga ko'ra faqat Administrator huquqi bilan ishlaydi.
        """
        employees: list[MoizvonkiEmployee] = []
        offset = 0
        for _ in range(max_pages):
            data = await self._post(
                "company.list_employee",
                max_results=max(1, min(int(max_results), MAX_RESULTS_LIMIT)),
                from_offset=offset,
            )
            rows = data.get("results") or []
            if not isinstance(rows, list):
                raise MoizvonkiBadResponseError(
                    "MoyZvonki `company.list_employee` javobi kutilgan shaklda emas"
                )
            employees.extend(
                MoizvonkiEmployee.from_api(row) for row in rows if isinstance(row, dict)
            )
            next_offset = _as_int(data.get("results_next_offset"))
            remains = _as_int(data.get("results_remains"))
            if not rows or (remains <= 0 and next_offset <= 0):
                break
            if next_offset <= offset:
                break
            offset = next_offset
        return employees

    async def ping(self) -> None:
        """Eng arzon haqiqiy so'rov — sozlama to'g'riligini tekshiradi."""
        await self._post("company.list_group", max_results=1)

    # ── Audio ─────────────────────────────────────────────────

    def absolute_recording_url(self, recording: str) -> str:
        """`recording` maydonini to'liq manzilga aylantiradi.

        Hujjatda «ссылка на запись разговора» deyilgan, lekin manzil
        mutlaqmi yoki nisbiymi aytilmagan — ikkalasi ham qo'llanadi.
        """
        value = (recording or "").strip()
        if not value:
            raise RecordingNotFoundError("Qo'ng'iroqning yozuvi yo'q")

        url = value if "://" in value else urljoin(f"{self._creds.base_url}/", value)
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise MoizvonkiBadResponseError(
                f"Yozuv manzili qo'llab-quvvatlanmaydigan turda: «{scheme}://…»"
            )
        return url

    @asynccontextmanager
    async def open_recording(
        self, recording: str, *, range_header: str | None = None
    ) -> AsyncIterator[RecordingStream]:
        """Yozuvni OQIM sifatida ochadi — diskka yozmaydi, buferlamaydi.

        `range_header` berilsa manbaga o'zgarishsiz uzatiladi. Manba
        qo'llab-quvvatlasa `206 Partial Content` + `Content-Range`
        qaytadi, aks holda manba nima bergan bo'lsa shu (odatda 200).
        """
        url = self.absolute_recording_url(recording)

        headers: dict[str, str] = {}
        if range_header:
            headers["Range"] = range_header

        request = self._http.build_request(
            "GET",
            url,
            headers=headers,
            timeout=httpx.Timeout(self._stream_timeout, connect=10.0),
        )
        try:
            response = await self._http.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise MoizvonkiUnreachableError(
                "MoyZvonki yozuvni berishga ulgurmadi (vaqt tugadi)"
            ) from exc
        except httpx.TransportError as exc:
            raise MoizvonkiUnreachableError(
                f"Yozuvni olish uchun MoyZvonki'ga ulanib bo'lmadi: "
                f"{self._creds.host_label}"
            ) from exc

        try:
            self._raise_for_recording(response)
            yield RecordingStream(
                status_code=response.status_code,
                content_type=(response.headers.get("Content-Type") or "audio/mpeg")
                .split(";")[0]
                .strip(),
                chunks=response.aiter_bytes(_STREAM_CHUNK),
                content_length=_optional_int(response.headers.get("Content-Length")),
                content_range=response.headers.get("Content-Range"),
                accept_ranges=response.headers.get("Accept-Ranges"),
            )
        finally:
            await response.aclose()

    def _raise_for_recording(self, response: httpx.Response) -> None:
        status = response.status_code
        if status in (200, 206):
            return

        if status == 404 or status == 410:
            raise RecordingNotFoundError(
                "Yozuv MoyZvonki'da topilmadi — qo'ng'iroq javobsiz bo'lgan "
                "yoki yozuv saqlash muddati o'tgan"
            )
        if status == 416:
            raise RangeNotSatisfiableError(
                "So'ralgan audio oralig'i fayl chegarasidan tashqarida"
            )
        if status in (401, 403):
            raise MoizvonkiAuthError(
                "MoyZvonki yozuvni berishdan bosh tortdi (avtorizatsiya) — "
                "Sozlamalar → MoyZvonki dagi login va API kalitni tekshiring"
            )
        if status in (502, 503, 504):
            raise MoizvonkiUnreachableError(
                f"MoyZvonki yozuv serveri javob bermadi (HTTP {status})"
            )
        raise MoizvonkiBadResponseError(f"MoyZvonki yozuvni bermadi (HTTP {status})")


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
