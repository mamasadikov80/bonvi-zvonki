"""Backend'dagi sozlamalar bilan aloqa (bot konfiguratsiyasi).

Ikkita ichki endpoint ishlatiladi — ikkalasi ham `X-Internal-Token`
sarlavhasi bilan himoyalangan:

    GET  /api/v1/settings/bot-config    → {"bot_token", "bot_username",
                                           "miniapp_name"}
    POST /api/v1/settings/bot-identity  → {"username": "..."}

Endpointlar backend'ning port'i hostga chiqarilgani uchun ochiq emas:
kalit `.env` → `INTERNAL_API_TOKEN` da turadi.

`miniapp_name` (`telegram.miniapp_name` sozlamasi) — Mini App'ning
BotFather'dagi qisqa nomi. U KELMASLIGI mumkin: sozlama hali
qo'shilmagan yoki to'ldirilmagan bo'lsa maydon umuman bo'lmaydi.
Bu xato emas — bo'sh qiymat «eski oqimda ishla» degani.
"""

import logging
from dataclasses import dataclass

import httpx

from src.core.config import mask_secret, settings
from src.views.groups import is_valid_miniapp_name

logger = logging.getLogger(__name__)

# Backend maydonni qaysi nom bilan berishi mumkin. Birinchi topilgani
# olinadi — bot va backend parallel yozilgani uchun nom biroz boshqacha
# bo'lsa ham oqim buzilmasin.
MINIAPP_KEYS = ("miniapp_name", "bot_miniapp_name", "telegram.miniapp_name")


#: Admin panelidagi «So'rovnoma qanday yuborilsin?» tanlovi
#: (`survey.mode`). Faqat shu ikki qiymat ma'no beradi.
MODE_MINIAPP = "miniapp"
MODE_BUTTONS = "buttons"


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Backend hisoblab bergan haqiqiy qiymatlar (baza > .env > standart)."""

    token: str
    username: str
    # Mini App qisqa nomi. Bo'sh = Mini App sozlanmagan.
    miniapp_name: str = ""
    # Admin tanlagan rejim. Noma'lum qiymat — `miniapp` deb qaraladi:
    # sozlama hali qo'shilmagan eski backend bilan ham oqim buzilmasin.
    survey_mode: str = MODE_MINIAPP

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    @property
    def has_miniapp(self) -> bool:
        return bool(self.effective_miniapp_name)

    @property
    def effective_miniapp_name(self) -> str:
        """Xabar chizishda ISHLATILADIGAN qisqa nom.

        Ikki shart: admin «Mini App» rejimini tanlagan BO'LSA va qisqa
        nom to'ldirilgan bo'lsa. Aks holda bo'sh — `views/groups.py`
        buni «oddiy tugmalar» deb tushunadi.

        Nega tanlov shu yerda, chizuvchi funksiyada emas: qisqa nom
        `pending`, `throttle` va callback handlerida uch marta
        ishlatiladi. Qaror bitta joyda turmasa, uchtasining biri
        boshqacha xabar chizib qo'yardi.
        """
        if self.survey_mode == MODE_BUTTONS:
            return ""
        return self.miniapp_name


class ConfigClient:
    """`/settings/bot-config` va `/settings/bot-identity` uchun yupqa klient.

    Tarmoq xatosi — kutilgan holat (backend hali ko'tarilmagan bo'lishi
    mumkin), shuning uchun xatolik ko'tarilmaydi: `None` qaytariladi va
    chaqiruvchi zaxira qiymatga o'tadi.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=(base_url or settings.API_BASE_URL) + "/api/v1",
            timeout=8.0,
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        self._warned_auth = False
        # Oxirgi MUVAFFAQIYATLI javob. Backend bir zumga yiqilsa ham
        # so'rovnoma to'g'ri ko'rinishda ketishi uchun eslab qolinadi.
        self._last: BotConfig | None = None
        # Yaroqsiz qisqa nom haqida bir marta ogohlantiramiz
        self._warned_miniapp = ""
        # Noma'lum rejim haqida ham — har aylanishda takrorlanmasin
        self._warned_mode = ""

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def miniapp_name(self) -> str:
        """Xabar chizish uchun AMALDAGI qisqa nom (so'rovsiz, keshdan).

        Rejim hisobga olingan: admin «Oddiy tugmalar» ni tanlagan bo'lsa
        bu yerdan bo'sh satr qaytadi va butun oqim — yangi xabar ham,
        hisoblagich tahriri ham — tugmalar shaklida chiziladi.

        Nima uchun kesh: guruhga xabar yuborayotgan vazifa har safar
        HTTP kutib turmasin, lekin sozlama panelda to'ldirilganda
        BOT QAYTA ISHGA TUSHIRILMASDAN yangi shaklga o'tsin. Keshni
        `fetch()` yangilaydi — uni token kuzatuvchisi har
        CONFIG_POLL_SECONDS da chaqiradi.
        """
        return self._last.effective_miniapp_name if self._last else ""

    async def fetch(self) -> BotConfig | None:
        """Backend'dan konfiguratsiyani oladi. Muvaffaqiyatsiz bo'lsa — None."""
        try:
            response = await self._client.get("/settings/bot-config")
        except httpx.HTTPError as exc:
            logger.debug("bot-config so'rovi muvaffaqiyatsiz: %s", exc)
            return None

        if response.status_code == 401:
            if not self._warned_auth:
                logger.error(
                    "❌ Backend ichki tokenni qabul qilmadi (401). "
                    ".env dagi INTERNAL_API_TOKEN backend va bot uchun bir xil bo'lsin. "
                    "Hozircha .env dagi zaxira token ishlatiladi."
                )
                self._warned_auth = True
            return None

        if response.status_code != 200:
            logger.warning("bot-config: kutilmagan javob %s", response.status_code)
            return None

        self._warned_auth = False
        try:
            data = response.json()
        except ValueError:
            logger.warning("bot-config: javob JSON emas")
            return None

        if not isinstance(data, dict):
            logger.warning("bot-config: javob kutilgan shaklda emas")
            return None

        config = BotConfig(
            token=str(data.get("bot_token") or "").strip(),
            username=str(data.get("bot_username") or "").strip().lstrip("@"),
            miniapp_name=self._read_miniapp(data),
            survey_mode=self._read_mode(data),
        )
        # Taqqoslash AMALDAGI qiymat bo'yicha: rejim almashsa qisqa nom
        # o'zgarmagan bo'lsa ham log'da yangi holat ko'rinishi kerak.
        if config.effective_miniapp_name != self.miniapp_name:
            logger.info(
                "🔗 So'rovnoma shakli: %s",
                (
                    f"Mini App (/{config.effective_miniapp_name})"
                    if config.effective_miniapp_name
                    else "guruhdagi 1–5 tugmalari"
                ),
            )
        self._last = config
        return config

    def _read_mode(self, data: dict) -> str:
        """`survey.mode` — noma'lum qiymat Mini App deb qaraladi.

        Maydon umuman bo'lmasligi ham mumkin (backend eskiroq bo'lsa).
        O'sha holda ham avvalgi xatti-harakat saqlanadi: qisqa nom
        to'ldirilgan bo'lsa Mini App ishlaydi.
        """
        raw = str(data.get("survey_mode") or "").strip().lower()
        if raw == MODE_BUTTONS:
            return MODE_BUTTONS
        if raw and raw != MODE_MINIAPP and self._warned_mode != raw:
            self._warned_mode = raw
            logger.warning(
                "⚠️  Noma'lum so'rovnoma rejimi «%s» — Mini App deb qabul qilindi",
                raw,
            )
        return MODE_MINIAPP

    @staticmethod
    def _pick_miniapp(data: dict) -> str:
        for key in MINIAPP_KEYS:
            value = data.get(key)
            if value:
                return str(value).strip()
        return ""

    def _read_miniapp(self, data: dict) -> str:
        """Qisqa nomni o'qiydi va yaroqliligini tekshiradi.

        Yaroqsiz qiymatdan buzuq havola quriladi va u HAQIQIY guruhga
        tushadi — shuning uchun shubhali qiymat bo'sh deb hisoblanadi
        va bot eski, ishlashi tekshirilgan oqimda qoladi.
        """
        raw = self._pick_miniapp(data)
        if not raw or is_valid_miniapp_name(raw):
            self._warned_miniapp = ""
            return raw

        if self._warned_miniapp != raw:
            self._warned_miniapp = raw
            logger.warning(
                "⚠️  «%s» Mini App qisqa nomiga o'xshamaydi "
                "(3–30 belgi, faqat a–z, 0–9 va «_»). "
                "Sozlama e'tiborsiz qoldirildi — eski oqim ishlayveradi.",
                raw,
            )
        return ""

    async def report_identity(self, username: str) -> bool:
        """`get_me()` topgan username'ni backend'ga yozib qo'yadi.

        Shundan keyin admin panelida haqiqiy username ko'rinadi va
        deep-link (`t.me/<username>?start=srv_<token>`) ishlaydi.
        """
        try:
            response = await self._client.post(
                "/settings/bot-identity", json={"username": username}
            )
        except httpx.HTTPError as exc:
            logger.warning("bot-identity yuborilmadi: %s", exc)
            return False

        if response.status_code == 200:
            logger.info("↪️  Username backend'ga yozildi: @%s", username)
            return True

        logger.warning("bot-identity: %s", response.status_code)
        return False

    def describe_auth(self) -> str:
        """Diagnostika uchun — kalit borligini (maskalangan holda) ko'rsatadi."""
        return mask_secret(settings.INTERNAL_API_TOKEN)
