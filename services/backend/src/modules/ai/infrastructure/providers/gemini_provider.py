"""Google Gemini — rasmiy `google-genai` SDK bilan.

Gemini audioni to'g'ridan-to'g'ri qabul qiladi, shuning uchun bitta
provayder ikkala rolni ham bajaradi. Strukturali javob uchun
`response_mime_type="application/json"` ishlatiladi va sxema tizim
ko'rsatmasiga qo'shiladi — bu SDK versiyasiga bog'liq emas.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from src.modules.ai.domain.entities import Transcript
from src.modules.ai.domain.errors import sdk_missing
from src.modules.ai.infrastructure.providers.base import (
    BaseClient,
    ClientConfig,
    collect_audio,
    guess_mime,
    silence_wav,
)

#: Har qator AYNAN shu shaklda so'raladi: «[MM:SS] SPEAKER_0: matn».
#
#: Vaqt belgisi bezak emas — qo'ng'iroq sahifasida transkript qatoriga
#: bosilganda audio o'sha soniyadan davom etadi va qoidabuzarlik
#: belgilari vaqt chizig'ida shu vaqtlar bo'yicha qo'yiladi. Vaqtsiz
#: transkriptda bu ikkalasi ham ishlamaydi.
#
#: Model vaqtni bermasa ham hech narsa buzilmaydi: frontend vaqtsiz
#: qatorni ham chizadi, shunchaki u bosilmaydigan bo'ladi.
#: ⚠️ NEGA BU QADAR BATAFSIL. Qisqa ko'rsatma («har qatorni shunday
#: yoz») YETMADI: model dastlabki 8-10 qatorda gapiruvchini yozdi,
#: keyin uni tashlab, faqat vaqt qoldirdi. 151 qatorli transkriptdan
#: atigi 9 tasida yorliq bor edi va sahifada suhbat ikki tomonga
#: bo'linmay qoldi. Namuna va «istisnosiz» so'zi shu sababdan.
_TRANSCRIBE_PROMPT = (
    "Ushbu telefon suhbatini so'zma-so'z matnga o'gir.\n\n"
    "QAT'IY SHAKL — har bir qator ISTISNOSIZ shunday bo'lsin:\n"
    "[MM:SS] SPEAKER_0: gap matni\n\n"
    "Namuna:\n"
    "[00:00] SPEAKER_0: Allo, assalomu alaykum.\n"
    "[00:03] SPEAKER_1: Vaalaykum assalom, eshitaman.\n"
    "[00:05] SPEAKER_0: Balon narxini bilmoqchi edim.\n"
    "[00:09] SPEAKER_0: Yuz ellik talikdan bormi?\n\n"
    "Qoidalar:\n"
    "1. HAR QATORDA vaqt ham, gapiruvchi ham bo'lishi SHART. "
    "Bitta odam ketma-ket bir necha gap aytsa ham, har qatorda uning "
    "yorlig'ini QAYTA yoz — yuqoridagi namunadagi oxirgi ikki qatorga "
    "qara.\n"
    "2. Gapiruvchilar faqat SPEAKER_0 va SPEAKER_1 (uchinchi ovoz "
    "bo'lsa SPEAKER_2). Ism o'rniga shu yorliqlarni ishlat.\n"
    "3. Vaqt — qator boshlangan payt, daqiqa:soniya.\n"
    "4. Faqat transkriptni qaytar: sarlavha, izoh, xulosa yozma."
)


class _GeminiBase(BaseClient):
    sdk_package = "google-genai"

    def __init__(self, config: ClientConfig) -> None:
        super().__init__(config)
        self._types: Any = None

    def _build_sdk(self) -> Any:
        try:
            from google import genai
            from google.genai import types
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise sdk_missing(self.label, self.sdk_package) from exc

        self._types = types
        http_options: dict[str, Any] = {"timeout": int(self._config.timeout * 1000)}
        if self._config.provider.base_url:
            http_options["base_url"] = self._config.provider.base_url
        if self._config.http_args:
            # Test uchun: httpx transport'ini almashtirish
            http_options["async_client_args"] = dict(self._config.http_args)
            http_options["client_args"] = dict(self._config.http_args)
        return genai.Client(
            api_key=self._config.api_key,
            http_options=types.HttpOptions(**http_options),
        )

    #: Ro'yxatdan chiqarib tashlanadigan modellar — nomiga qarab.
    #: Ular `generateContent` ni qo'llasa ham bizga yaramaydi: rasm,
    #: video, ovoz sintezi, o'rnatish (embedding), robototexnika,
    #: brauzer boshqaruvi va agent rejimlari. Admin ro'yxatda faqat
    #: SUHBAT modellarini ko'rishi kerak — «deep-research» yoki
    #: «imagen» tanlansa quvur birinchi chaqiruvdayoq yiqilardi.
    _SKIP = (
        "embedding", "imagen", "veo", "lyria", "tts", "image",
        "robotics", "computer-use", "aqa", "antigravity",
        "deep-research", "live", "native-audio", "gemma",
        "nano-banana",  # rasm modeli, nomida «image» yo'q
    )

    #: ⚠️ ESKI AVLODLAR — `models.list` ularni HAMON qaytaradi, lekin
    #: yangi akkauntda chaqirilganda «This model is no longer available
    #: to new users» keladi. Ya'ni Google ro'yxatiga ishonib bo'lmaydi:
    #: u «bor» deydi, chaqiruv esa yiqiladi. Buni o'z ko'zimiz bilan
    #: ko'rdik — `gemini-2.5-pro` shu sababdan ishlamagan edi.
    _RETIRED = ("gemini-1.", "gemini-2.")

    async def list_models(self) -> list[str]:
        client = self._build_sdk()
        names: list[str] = []
        try:
            for model in await client.aio.models.list():
                name = (getattr(model, "name", "") or "").split("/")[-1]
                low = name.lower()
                if not name or any(word in low for word in self._SKIP):
                    continue
                if low.startswith(self._RETIRED):
                    continue
                # `supported_actions` — Google'ning O'ZI aytgan imkoniyat.
                # Taxmin qilmaymiz: `generateContent` bo'lmasa, bizning
                # chaqiruv shaklimiz bu modelda umuman ishlamaydi
                # (masalan Live API modellari faqat `bidiGenerateContent`).
                actions = getattr(model, "supported_actions", None) or []
                if "generateContent" not in actions:
                    continue
                names.append(name)
        except Exception:  # noqa: BLE001 — ro'yxat olinmasa zaxiraga qaytamiz
            return []
        return names

    async def _generate(self, contents: Any, config: Any) -> str:
        client = self._build_sdk()
        try:
            response = await client.aio.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 — o'zbekchaga tarjima qilinadi
            raise self._fail(exc) from None
        return (getattr(response, "text", None) or "").strip()


class GeminiASRClient(_GeminiBase):
    async def transcribe(
        self,
        audio: AsyncIterator[bytes],
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript:
        payload = await collect_audio(audio)
        return await self._transcribe_bytes(payload, filename, language)

    async def _transcribe_bytes(
        self, payload: bytes, filename: str, language: str | None
    ) -> Transcript:
        self._build_sdk()  # `types` ni tayyorlaydi
        types = self._types
        prompt = _TRANSCRIBE_PROMPT
        if language:
            prompt += f" Audio tili: {language}."
        contents = [
            types.Part.from_bytes(data=payload, mime_type=guess_mime(filename)),
            prompt,
        ]
        text = await self._generate(
            contents, types.GenerateContentConfig(temperature=0.0)
        )
        return Transcript(
            text=text,
            provider=self.provider_key,
            model=self.model,
            language=language,
        )

    async def ping(self) -> str:
        transcript = await self._transcribe_bytes(silence_wav(), "ping.wav", None)
        return transcript.text or "(jimlik)"


class GeminiLLMClient(_GeminiBase):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        self._build_sdk()
        types = self._types
        instruction = system
        options: dict[str, Any] = {
            "system_instruction": instruction,
            "max_output_tokens": max_tokens,
        }
        if schema:
            options["response_mime_type"] = "application/json"
            options["system_instruction"] = (
                f"{instruction}\n\nJavobni AYNAN shu JSON sxemasi bo'yicha qaytar:\n"
                + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            )
        return await self._generate(user, types.GenerateContentConfig(**options))

    async def ping(self) -> str:
        self._build_sdk()
        types = self._types
        text = await self._generate(
            "Javob: OK", types.GenerateContentConfig(max_output_tokens=64)
        )
        return text or "OK"
