"""AI PROVAYDERLARI REYESTRI.

══════════════════════════════════════════════════════════════════
  YANGI PROVAYDER QO'SHISH = SHU RO'YXATGA BITTA YOZUV QO'SHISH.
══════════════════════════════════════════════════════════════════

Bitta yozuvdan avtomatik hosil bo'ladi:
  • Sozlamalar sahifasidagi provayder tanlovi (`ai.asr_provider` / `ai.llm_provider`)
  • Shu provayderning API kalit maydoni (`ai.<key>_api_key`)
  • Zaxira model ro'yxati (asosiysi vendordan JONLI olinadi)
  • Fabrikadagi klient (client_kind orqali)

OpenAI protokoliga mos vendorlar (DeepSeek, Together, Fireworks, xAI,
Cerebras, Mistral…) uchun `client_kind="openai_compat"` va `base_url`
yetarli — kodning boshqa hech qayeriga tegilmaydi.
"""

from src.modules.ai.domain.entities import (
    AI_ROLES,
    ROLE_ASR,
    ROLE_LLM,
    AIProvider,
)

#
# ⚠️ GROQ (Whisper) OLIB TASHLANDI — O'ZBEK TILI UCHUN YAROQSIZ.
#
# Haqiqiy qo'ng'iroqlarda sinaldi (5 ta, 3–5 daqiqalik):
#   · `whisper-large-v3-turbo`, til ko'rsatilmagan → matn inglizchaga
#     «tarjima» bo'lib chiqdi yoki turkcha deb o'qildi;
#   · `language="uz"` berilganda AHVOL YOMONLASHDI — bema'ni bo'g'inlar,
#     hatto tibet yozuvi aralashdi;
#   · `whisper-large-v3` (to'liq model) ham xuddi shunday.
# Beshta qo'ng'iroqning beshtasi ham 0 ball oldi.
#
# Sabab modelda: Whisper oilasida o'zbek tili amalda qoplanmagan.
# Sozlama bilan tuzatib bo'lmaydi, shuning uchun ro'yxatda saqlash
# faqat adminni noto'g'ri tanlovga boshlardi.
#
# ⚠️ ELEVENLABS ham olib tashlandi — mijozning qarori. Uni bu yerda
# SINAB KO'RILMADI (kalit yo'q edi), ya'ni sifatiga oid dalilimiz yo'q.
#
# Ikkalasi ham kerak bo'lsa: yozuvni qaytarish yetarli, kodning boshqa
# joyiga tegilmaydi (fayl boshidagi izohga qarang).
#
AI_PROVIDERS: list[AIProvider] = [
    AIProvider(
        key="openai",
        label="OpenAI (ChatGPT)",
        roles=frozenset({ROLE_ASR, ROLE_LLM}),
        api_key_setting="ai.openai_api_key",
        key_label_uz="OpenAI API kaliti",
        # Bu ro'yxatlar — ZAXIRA. Asosiy manba: vendorning `GET /v1/models`
        # javobi (`ai/application/catalog.py`). Bu yerdagilar faqat vendor
        # javob bermaganda va ro'yxat tartibida tepaga chiqarish uchun.
        models={
            ROLE_ASR: ["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"],
            ROLE_LLM: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
        },
        defaults={ROLE_ASR: "gpt-4o-transcribe", ROLE_LLM: "gpt-4.1-mini"},
        docs_url="https://platform.openai.com/docs",
        client_kind="openai_compat",
        sdk_package="openai",
        env_var="OPENAI_API_KEY",
        hint_uz="Ikkala rol uchun ham ishlaydi. O'zbek tilida sifati o'rtacha.",
    ),
    AIProvider(
        key="gemini",
        label="Google Gemini",
        roles=frozenset({ROLE_ASR, ROLE_LLM}),
        api_key_setting="ai.gemini_api_key",
        key_label_uz="Google Gemini API kaliti",
        # ⚠️ 2.x oilasi (`gemini-2.5-flash`, `gemini-2.5-pro`,
        # `gemini-2.0-flash`) ATAYLAB olib tashlandi. Ular `models.list`
        # da hamon ko'rinadi, lekin YANGI akkauntlarda chaqirilganda
        # «no longer available to new users» qaytadi — ya'ni taklif
        # ro'yxatidagi va standart qiymatdagi model ishlamas edi va
        # xato faqat birinchi baholashda ma'lum bo'lardi.
        # Tartib TAVSIYA tartibi — birinchisi standart bo'ladi.
        #
        # `gemini-3.1-flash-lite` oldinda, chunki bepul tarifda kunlik
        # chegarasi 500 so'rov (flash oilasida 20 — ya'ni 25 barobar
        # kam, atigi 10 ta qo'ng'iroq). Sifati sinovda tekshirildi:
        # o'zbek nutqini aniq yozadi, gapiruvchilarni ajratadi va
        # vaqt belgilarini so'ralgan shaklda beradi.
        #
        # `gemini-3.7-flash` rubrika arifmetikasida bir oz ishonchliroq
        # (baholashda kamroq adashadi), lekin kunlik chegarasi juda tor.
        models={
            ROLE_ASR: [
                "gemini-3.1-flash-lite",
                "gemini-3.7-flash",
                "gemini-3.6-flash",
                "gemini-flash-latest",
            ],
            ROLE_LLM: [
                "gemini-3.1-flash-lite",
                "gemini-3.7-flash",
                "gemini-3.6-flash",
                "gemini-flash-latest",
            ],
        },
        defaults={
            ROLE_ASR: "gemini-3.1-flash-lite",
            ROLE_LLM: "gemini-3.1-flash-lite",
        },
        docs_url="https://ai.google.dev/gemini-api/docs",
        client_kind="gemini",
        sdk_package="google-genai",
        env_var="GEMINI_API_KEY",
        hint_uz=(
            "Audioni to'g'ridan-to'g'ri qabul qiladi va o'zbek tilini "
            "ishonchli yozadi — sinovdan o'tgan yagona ASR."
        ),
    ),
    AIProvider(
        key="anthropic",
        label="Anthropic Claude",
        roles=frozenset({ROLE_LLM}),
        api_key_setting="ai.anthropic_api_key",
        key_label_uz="Anthropic API kaliti",
        # Zaxira ro'yxat — asosiysi vendorning `GET /v1/models` javobi
        models={
            ROLE_LLM: ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
        },
        defaults={ROLE_LLM: "claude-haiku-4-5"},
        docs_url="https://platform.claude.com/docs",
        client_kind="anthropic",
        sdk_package="anthropic",
        env_var="ANTHROPIC_API_KEY",
        legacy_key_settings=("llm.anthropic_api_key",),
        hint_uz="Rejadagi asosiy baholovchi. Faqat matn — audio qabul qilmaydi.",
    ),
]

# ── Indekslar ─────────────────────────────────────────────────

PROVIDERS_BY_KEY: dict[str, AIProvider] = {p.key: p for p in AI_PROVIDERS}


def _assert_unique() -> None:
    if len(PROVIDERS_BY_KEY) != len(AI_PROVIDERS):
        raise ValueError("Reyestrda takrorlangan provayder kaliti bor")
    settings_seen: dict[str, str] = {}
    for provider in AI_PROVIDERS:
        owner = settings_seen.get(provider.api_key_setting)
        if owner:
            raise ValueError(
                f"{provider.api_key_setting} sozlamasi ikki marta: {owner} va {provider.key}"
            )
        settings_seen[provider.api_key_setting] = provider.key


_assert_unique()


def get_provider(key: str) -> AIProvider | None:
    return PROVIDERS_BY_KEY.get((key or "").strip())


def providers_for_role(role: str) -> list[AIProvider]:
    """Shu rolni qo'llab-quvvatlaydigan provayderlar (reyestr tartibida)."""
    return [p for p in AI_PROVIDERS if p.supports(role)]


def default_provider_key(role: str) -> str:
    """Sozlama bo'sh bo'lsa ishlatiladigan provayder."""
    candidates = providers_for_role(role)
    if not candidates:  # pragma: no cover — reyestr bo'sh bo'lishi mumkin emas
        raise ValueError(f"'{role}' roli uchun provayder yo'q")
    # ASR uchun Gemini: haqiqiy qo'ng'iroqlarda o'zbekchani ishonchli
    # taniydigan va gapiruvchilarni ajratadigan yagona sinalgan variant
    preferred = {ROLE_ASR: "gemini", ROLE_LLM: "anthropic"}.get(role)
    for provider in candidates:
        if provider.key == preferred:
            return provider.key
    return candidates[0].key


def select_options(role: str) -> list[dict[str, str]]:
    """`select` turidagi sozlama uchun variantlar — DINAMIK, qo'lda yozilmaydi."""
    return [
        {"value": p.key, "label": f"{p.label} — {p.hint_uz}" if p.hint_uz else p.label}
        for p in providers_for_role(role)
    ]


def api_key_settings() -> list[tuple[AIProvider, str]]:
    """Har bir provayderning maxfiy kalit sozlamasi."""
    return [(p, p.api_key_setting) for p in AI_PROVIDERS]


def roles_summary() -> dict[str, list[str]]:
    """Diagnostika uchun: rol → provayderlar."""
    return {role: [p.key for p in providers_for_role(role)] for role in AI_ROLES}
