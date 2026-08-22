"""Sozlamalar domeni.

Maqsad: AI provayderlari, kalitlar va chegaralar dashboard'dan
o'zgartirilsin — kodga tegmasdan, qayta deploy qilmasdan.

Ustuvorlik: bazadagi qiymat > .env qiymati > standart qiymat.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from src.modules.ai.domain.entities import ROLE_ASR, ROLE_LLM
from src.modules.ai.domain.registry import (
    AI_PROVIDERS,
    default_provider_key,
    select_options,
)


class SettingCategory(StrEnum):
    ACCESS = "access"  # rollar nima ko'radi
    AI = "ai"  # provayder, model, kalit — YAGONA AI sozlamasi
    TELEGRAM = "telegram"  # bot
    MOIZVONKI = "moizvonki"  # qo'ng'iroq manbai
    SMS = "sms"  # Eskiz zaxira kanali
    STORAGE = "storage"  # audio arxiv
    SCORING = "scoring"  # rubrika chegaralari
    SURVEY = "survey"  # so'rovnoma kadansi
    SALES = "sales"  # savdo nazorati qoidalari


CATEGORY_LABEL_UZ: dict[SettingCategory, str] = {
    SettingCategory.ACCESS: "Ruxsatlar — kim nimani ko'radi",
    SettingCategory.AI: "Sun'iy intellekt (provayder va kalitlar)",
    SettingCategory.TELEGRAM: "Telegram bot",
    SettingCategory.MOIZVONKI: "MoyZvonki integratsiyasi",
    SettingCategory.SMS: "SMS (Eskiz.uz)",
    SettingCategory.STORAGE: "Audio arxiv",
    SettingCategory.SCORING: "Baholash qoidalari",
    SettingCategory.SURVEY: "Client so'rovnomasi",
    SettingCategory.SALES: "Savdo nazorati",
}

FieldType = Literal["string", "secret", "number", "boolean", "select"]


@dataclass(slots=True)
class SettingSpec:
    """Bitta sozlama tavsifi — UI shu asosda forma quradi."""

    key: str
    category: SettingCategory
    label_uz: str
    type: FieldType
    default: Any = None
    options: list[dict[str, str]] = field(default_factory=list)
    hint_uz: str | None = None
    # .env dagi mos o'zgaruvchi (fallback uchun)
    env_var: str | None = None

    @property
    def is_secret(self) -> bool:
        return self.type == "secret"


# ══════════════════════════════════════════════════════════════
#  SOZLAMALAR REYESTRI
#  Yangi sozlama qo'shish = shu ro'yxatga bitta qator qo'shish.
#  UI, validatsiya va API avtomatik moslashadi.
# ══════════════════════════════════════════════════════════════

SETTINGS_REGISTRY: list[SettingSpec] = [
    # ── Ruxsatlar ─────────────────────────────────────────────
    SettingSpec(
        key="access.sales_client_rating",
        category=SettingCategory.ACCESS,
        label_uz="Savdo xodimi client bahosini ko'radimi?",
        type="select",
        default="score_only",
        options=[
            {"value": "hidden", "label": "Yo'q — faqat menejerlar ko'radi"},
            {"value": "score_only", "label": "Faqat o'rtacha ball (izohlarsiz)"},
            {"value": "full", "label": "Ball + client izohlari (anonim)"},
        ],
        hint_uz=(
            "Xodim hech qachon kim baho qo'yganini bilmaydi. "
            "Izohlar sifati tasdiqlangach 'Ball + izohlar' ga o'tish tavsiya etiladi — "
            "shaffoflik tizimga ishonchni oshiradi."
        ),
    ),
    SettingSpec(
        key="access.manager_manages_agents",
        category=SettingCategory.ACCESS,
        label_uz="Menejer savdo xodimlarini boshqara oladimi?",
        type="boolean",
        default=False,
        hint_uz=(
            "Yoqilsa — menejer xodim qo'sha, tahrirlay va MoyZvonki'dan "
            "sinxronlashtira oladi. Foydalanuvchi hisoblari va sozlamalar "
            "baribir faqat adminda qoladi."
        ),
    ),
    # ── AI ga tegishli, lekin provayderdan MUSTAQIL sozlamalar ──
    #
    # ⚠️ Bu yerda ilgari ikkita butun blok turardi: `asr.*` (provayder
    # tanlovi + ElevenLabs/Groq/Kotib kalitlari, VAD tugmasi) va
    # `llm.*` (provayder, model, eskalatsiya modeli, batch, audit
    # sampli). Ularning HECH BIRI o'qilmasdi — haqiqiy tanlov `ai.*`
    # da. Ya'ni admin ikkita bir xil ko'rinadigan ro'yxatni ko'rar,
    # eskisiga tegsa hech narsa o'zgarmasdi va «nega ishlamayapti?»
    # degan savol tug'ilardi. Ikkalasi ham butunlay olib tashlandi.
    #
    # Quyidagi ikkitasi TIRIK va quvur ularni haqiqatan o'qiydi.
    SettingSpec(
        key="ai.min_duration_sec",
        category=SettingCategory.AI,
        label_uz="Minimal davomiylik (soniya)",
        type="number",
        default=45,
        hint_uz=(
            "Bundan qisqa qo'ng'iroqlar umuman qayta ishlanmaydi — "
            "ular baholashga arzimaydi va pul yeydi."
        ),
    ),
    SettingSpec(
        key="moizvonki.internal_numbers",
        category=SettingCategory.MOIZVONKI,
        label_uz="Qo'shimcha ichki raqamlar",
        type="string",
        hint_uz=(
            "Kompaniyaning MoyZvonki'da xodim sifatida ro'yxatdan o'tmagan "
            "raqamlari: ombor, logistika, buxgalteriya, rejalashtirish. "
            "Shu raqamlar bilan bo'lgan suhbat «ichki» deb belgilanadi va "
            "savdo rubrikasi bilan baholanmaydi. Vergul yoki yangi qator "
            "bilan ajrating. "
            "Raqamlar bloki bo'lsa QOIDA yozing: «*700» — oxiri 700 bilan "
            "tugagan har qanday raqam bizniki (kamida uch raqam). "
            "Xodimlarning o'z raqamlari bu yerga KERAK EMAS — ular "
            "qo'ng'iroqlardan avtomatik o'rganiladi."
        ),
    ),
    # ── Telegram ──────────────────────────────────────────────
    SettingSpec(
        key="telegram.bot_token",
        category=SettingCategory.TELEGRAM,
        label_uz="Bot tokeni",
        type="secret",
        hint_uz="@BotFather dan oling.",
        env_var="TELEGRAM_BOT_TOKEN",
    ),
    SettingSpec(
        key="telegram.bot_username",
        category=SettingCategory.TELEGRAM,
        label_uz="Bot username",
        type="string",
        hint_uz="@ belgisisiz. Deep-link uchun kerak.",
        env_var="TELEGRAM_BOT_USERNAME",
    ),
    SettingSpec(
        key="telegram.miniapp_name",
        category=SettingCategory.TELEGRAM,
        label_uz="Mini App short name",
        type="string",
        hint_uz="BotFather → /newapp da kiritilgan qisqa nom, masalan: survey",
        env_var="TELEGRAM_MINIAPP_NAME",
    ),
    # ── MoyZvonki ─────────────────────────────────────────────
    SettingSpec(
        key="moizvonki.domain",
        category=SettingCategory.MOIZVONKI,
        label_uz="Domen",
        type="string",
        hint_uz="Masalan: kompaniya.moizvonki.ru",
        env_var="MOIZVONKI_DOMAIN",
    ),
    SettingSpec(
        key="moizvonki.user",
        category=SettingCategory.MOIZVONKI,
        label_uz="Foydalanuvchi (email)",
        type="string",
        env_var="MOIZVONKI_USER",
    ),
    SettingSpec(
        key="moizvonki.api_key",
        category=SettingCategory.MOIZVONKI,
        label_uz="API kaliti",
        type="secret",
        env_var="MOIZVONKI_API_KEY",
    ),
    # ── SMS ───────────────────────────────────────────────────
    SettingSpec(
        key="sms.eskiz_email",
        category=SettingCategory.SMS,
        label_uz="Eskiz.uz email",
        type="string",
        env_var="ESKIZ_EMAIL",
    ),
    SettingSpec(
        key="sms.eskiz_password",
        category=SettingCategory.SMS,
        label_uz="Eskiz.uz paroli",
        type="secret",
        env_var="ESKIZ_PASSWORD",
    ),
    # ── Baholash ──────────────────────────────────────────────
    SettingSpec(
        key="scoring.rubric_version",
        category=SettingCategory.SCORING,
        label_uz="Rubrika versiyasi",
        type="string",
        default="v1",
    ),
    SettingSpec(
        key="scoring.review_confidence_threshold",
        category=SettingCategory.SCORING,
        label_uz="Qayta ko'rish chegarasi",
        type="number",
        default=0.7,
        hint_uz="Ishonch shu qiymatdan past bo'lsa, baho odam tekshiruviga yuboriladi.",
    ),
    SettingSpec(
        key="scoring.low_score_alert",
        category=SettingCategory.SCORING,
        label_uz="Past ball ogohlantirishi",
        type="number",
        default=50,
        hint_uz="Shu balldan past baho menejerga darhol xabar qiladi.",
    ),
    # ── Savdo nazorati ────────────────────────────────────────
    SettingSpec(
        key="sales.window_days",
        category=SettingCategory.SALES,
        label_uz="Savdo oldidan qo'ng'iroq qidiriladigan kunlar soni",
        type="number",
        default=3,
        hint_uz=(
            "Savdo rasmiy kelishuv bilan bo'lganini shu oyna aniqlaydi: "
            "savdo kuni va undan oldingi shuncha kun ichida mijoz bilan "
            "suhbat bo'lgan bo'lsa — savdo «toza». SAP savdo VAQTINI "
            "bermaydi (faqat sana), shuning uchun oyna soat bilan emas, "
            "kun bilan o'lchanadi. Oyna kattalashsa shubhali savdo "
            "kamayadi, lekin haqiqiy chetlanish ham yashirinadi."
        ),
    ),
    # ── Kunlik Telegram xabari ────────────────────────────────
    #
    # ⚠️ BOSH KALIT SUKUT BO'YICHA O'CHIQ va shunday qolishi SHART.
    # Bu tashqariga — begona Telegram chatiga — ketadigan yagona amal:
    # noto'g'ri guruhga tushgan xabarni qaytarib bo'lmaydi. Shuning
    # uchun tizim o'z-o'zidan hech qachon yubormaydi; rahbar avval
    # kalitni yoqadi, guruhni ko'rsatadi va sinov tugmasi bilan
    # matnni o'z ko'zi bilan ko'radi.
    SettingSpec(
        key="sales.digest_enabled",
        category=SettingCategory.SALES,
        label_uz="Kunlik Telegram xabari yoqilgan",
        type="boolean",
        default=False,
        hint_uz=(
            "BOSH KALIT. O'chirilgan bo'lsa hech qanday xabar "
            "YUBORILMAYDI — na kechasi, na boshqa paytda. "
            "Yoqishdan oldin quyidagi «Chat ID» ni to'ldiring va "
            "«Sinov xabari» tugmasi bilan matnni ko'rib oling: xabar "
            "guruhga ketgach uni qaytarib bo'lmaydi."
        ),
    ),
    SettingSpec(
        key="sales.digest_chat_id",
        category=SettingCategory.SALES,
        label_uz="Qaysi Telegram chatga yuborilsin (Chat ID)",
        type="string",
        default="",
        hint_uz=(
            "Guruh yoki shaxsiy chat identifikatori. Guruhniki manfiy "
            "son bo'ladi: -1001234567890. Bot o'sha guruhda bo'lishi "
            "shart. Bo'sh qoldirilsa xabar YUBORILMAYDI — kalit yoqilgan "
            "bo'lsa ham: manzilsiz xabar yuborishning iloji yo'q."
        ),
    ),
    SettingSpec(
        key="sales.digest_min_amount",
        category=SettingCategory.SALES,
        label_uz="Xabarga tushadigan eng kichik savdo (dollarda)",
        type="number",
        default=0,
        hint_uz=(
            "Shu summadan past savdolar kunlik xabarga umuman kirmaydi "
            "— sonlarga ham, ro'yxatga ham. 0 (sukut) — hammasi kiradi. "
            "⚠️ Bu FAQAT Telegram xabariga tegishli: paneldagi ro'yxat "
            "va sonlar o'zgarmaydi, ya'ni chegara hech narsani "
            "yashirmaydi, faqat kechasi keladigan xabarni qisqartiradi. "
            "Summasi noma'lum savdolar chegaradan qat'i nazar QOLADI."
        ),
    ),
    # ── So'rovnoma ────────────────────────────────────────────
    SettingSpec(
        key="survey.mode",
        category=SettingCategory.SURVEY,
        label_uz="So'rovnoma qanday yuborilsin?",
        type="select",
        default="miniapp",
        options=[
            {
                "value": "miniapp",
                "label": "Mini App — Telegram ichida sahifa (ball + sabab + izoh)",
            },
            {
                "value": "buttons",
                "label": "Oddiy tugmalar — guruhning o'zida 1–5, izohsiz",
            },
        ],
        hint_uz=(
            "«Oddiy tugmalar» — mijoz guruhdan umuman chiqmaydi: 1–5 dan birini "
            "bosadi va tamom. Izoh ham, sabab ham, botga o'tish ham so'ralmaydi — "
            "faqat ball yig'iladi. "
            "«Mini App» — Telegram ichida sahifa ochiladi va u yerda ball bilan "
            "birga sabab va izoh ham so'raladi; buning uchun quyidagi «Mini App "
            "short name» to'ldirilgan bo'lishi shart. To'ldirilmagan bo'lsa bot "
            "xavfsizlik uchun o'zi tugmalar rejimiga tushadi."
        ),
    ),
    SettingSpec(
        key="survey.period_days",
        category=SettingCategory.SURVEY,
        label_uz="Kadans (kun)",
        type="number",
        default=14,
        hint_uz="Har necha kunda bir marta client'dan baho so'ralsin.",
    ),
    SettingSpec(
        key="survey.suppression_days",
        category=SettingCategory.SURVEY,
        label_uz="Takror so'ramaslik oynasi (kun)",
        type="number",
        default=10,
        hint_uz="Oxirgi so'rovdan shuncha kun o'tmaguncha qayta so'ralmaydi.",
    ),
    SettingSpec(
        key="survey.min_responses",
        category=SettingCategory.SURVEY,
        label_uz="Reyting ko'rsatish uchun minimal javob",
        type="number",
        default=5,
        hint_uz="Shundan kam javob bo'lsa dashboardda reyting o'rniga 'yig'ilmoqda' yoziladi.",
    ),
    SettingSpec(
        key="survey.enabled",
        category=SettingCategory.SURVEY,
        label_uz="So'rovnoma yuborish yoqilgan",
        type="boolean",
        default=False,
        hint_uz=(
            "BOSH kalit. O'chirilgan bo'lsa hech qanday so'rovnoma yaratilmaydi — "
            "«Barchasiga so'rovnoma» tugmasi ham, bitta guruhga yuborish ham "
            "ishlamaydi. Pilot tugagunicha o'chirib turing."
        ),
    ),
    SettingSpec(
        key="survey.auto_send",
        category=SettingCategory.SURVEY,
        label_uz="Avtomatik yuborish (kadans bo'yicha)",
        type="boolean",
        default=False,
        hint_uz=(
            "Yoqilsa tizim har kuni ish vaqtida guruhlarni o'zi ko'rib chiqadi va "
            "oxirgi so'rovnomadan «Kadans» da ko'rsatilgan kun o'tganlariga yangisini "
            "navbatga qo'yadi — admin tugma bosishi shart emas. "
            "O'chirilgan bo'lsa so'rovnoma FAQAT qo'lda yuboriladi."
        ),
    ),
    SettingSpec(
        key="survey.message_ttl_hours",
        category=SettingCategory.SURVEY,
        label_uz="Guruhdagi xabar necha soatdan keyin o'chirilsin?",
        type="number",
        default=24,
        hint_uz=(
            "Muddat tugagach bot guruhga yuborgan so'rovnoma xabarini o'zi "
            "o'chiradi — guruh reklama taxtasiga aylanmasin. "
            "Faqat SHU xabar o'chadi: bot boshqa xabarlarga umuman tegmaydi. "
            "0 — hech qachon o'chirilmasin. "
            "Telegram botga o'z xabarini 48 soat ichidagina o'chirishga ruxsat "
            "beradi, shuning uchun 48 dan katta qiymat ishlamaydi."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════
#  AI SOZLAMALARI — REYESTRDAN AVTOMATIK HOSIL BO'LADI
#
#  Bu blokda birorta provayder nomi QO'LDA yozilmagan. Tanlov
#  variantlari ham, kalit maydonlari ham
#  `src/modules/ai/domain/registry.py` dagi yozuvlardan quriladi:
#  o'sha reyestrga bitta qator qo'shilsa, bu yerda ham, UI'da ham
#  yangi provayder o'zi paydo bo'ladi.
#
#  ⚠️ AI SOZLAMALARIDA `env_var` YO'Q — bu ATAYLAB.
#
#  Sozlamalarning umumiy ustuvorligi «baza > .env > standart». Ya'ni
#  `env_var` berilgan maydonda admin qiymatni O'CHIRSA, tizim jimgina
#  `.env` dagi eskisiga qaytadi. AI uchun bu qabul qilib bo'lmaydi:
#  admin panelda «Gemini» ko'rinib turadi, tizim esa `.env` dagi
#  boshqa provayderda ishlayveradi va buni hech kim sezmaydi.
#
#  Shuning uchun AI da yagona haqiqat manbai — ADMIN PANEL. Ekranda
#  nima tanlangan bo'lsa, quvur aynan shuni ishlatadi.
# ══════════════════════════════════════════════════════════════


def _ai_settings() -> list[SettingSpec]:
    specs: list[SettingSpec] = []
    role_labels = {ROLE_ASR: "Nutqni matnga (ASR)", ROLE_LLM: "AI baholovchi (LLM)"}
    for role in (ROLE_ASR, ROLE_LLM):
        specs.append(
            SettingSpec(
                key=f"ai.{role}_provider",
                category=SettingCategory.AI,
                label_uz=f"{role_labels[role]} — provayder",
                type="select",
                default=default_provider_key(role),
                options=select_options(role),
                hint_uz=(
                    "Tanlangan provayder darhol ishlay boshlaydi — qayta "
                    "deploy qilish shart emas. Kalitni pastdan kiriting va "
                    "«Tekshirish» tugmasini bosing."
                ),
            )
        )
        specs.append(
            SettingSpec(
                key=f"ai.{role}_model",
                category=SettingCategory.AI,
                label_uz=f"{role_labels[role]} — model",
                type="string",
                default="",
                hint_uz=(
                    "Ro'yxat provayderning o'z API'sidan jonli olinadi — "
                    "vendor yangi model chiqarsa o'zi paydo bo'ladi."
                ),
            )
        )
    # ── Audio tili ────────────────────────────────────────────
    #
    # ⚠️ WHISPER OILASI UCHUN BU MAYDON HAL QILUVCHI. Til
    # ko'rsatilmasa Whisper uni o'zi topmoqchi bo'ladi va o'zbek
    # nutqini muntazam ravishda TURKCHA yoki INGLIZCHA deb o'qiydi —
    # natijada transkript o'rniga tarjimaga o'xshash bema'ni matn
    # keladi, baho esa 0 bo'lib chiqadi. Gemini bu ko'rsatmasiz ham
    # o'zbekchani taniydi, lekin ko'rsatilgani unga ham zarar qilmaydi.
    specs.append(
        SettingSpec(
            key="ai.asr_language",
            category=SettingCategory.AI,
            label_uz="Audio tili",
            type="string",
            default="uz",
            hint_uz=(
                "ISO kodi: uz — o'zbek, ru — rus, en — ingliz. "
                "Whisper (Groq, OpenAI) uchun MAJBURIY: ko'rsatilmasa "
                "o'zbek nutqini turkcha deb o'qiydi. Bo'sh qoldirilsa "
                "provayder tilni o'zi aniqlaydi."
            ),
        )
    )

    for provider in AI_PROVIDERS:
        roles = ", ".join(sorted(provider.roles))
        specs.append(
            SettingSpec(
                key=provider.api_key_setting,
                category=SettingCategory.AI,
                label_uz=provider.key_label_uz,
                type="secret",
                # `env_var` YO'Q — yuqoridagi izohga qarang
                hint_uz=f"Rollar: {roles}. Hujjat: {provider.docs_url}",
            )
        )
    return specs


SETTINGS_REGISTRY.extend(_ai_settings())

SETTINGS_BY_KEY: dict[str, SettingSpec] = {s.key: s for s in SETTINGS_REGISTRY}

if len(SETTINGS_BY_KEY) != len(SETTINGS_REGISTRY):
    raise ValueError("SETTINGS_REGISTRY da takrorlangan kalit bor")

SECRET_MASK = "••••••••"
