"""So'rovnoma servisi — token orqali ochish va baho qabul qilish.

Bu oqim **ochiq** (avtorizatsiyasiz): mijoz — do'kon egasi, u hech qachon
dashboardga kirmaydi. Kalit rolini tokenning o'zi bajaradi.

MAXFIYLIK QOIDASI (PLAN.md D1 — buzilmasin):
  Javob anonim. Servis mijozning kimligini (client_id, telefon, Telegram
  identifikatori) HECH QACHON qaytarmaydi va saqlamaydi. Savdo xodimi
  "bu bahoni kim qo'ydi" degan savolga javob topa olmasligi kerak —
  aks holda mijoz rostini aytmaydi.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.settings.application.services import SettingsService
from src.modules.surveys.domain.entities import (
    MIN_RESPONSES_FOR_RATING,
    SURVEY_MESSAGE_TTL_HOURS,
    SURVEY_PERIOD_DAYS,
    SURVEY_SUPPRESSION_DAYS,
    TELEGRAM_DELETE_LIMIT_HOURS,
    Resolution,
    SurveyStatus,
    new_survey_token,
    normalize_red_flags,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel

logger = logging.getLogger(__name__)


async def resolve_min_responses(session: AsyncSession) -> int:
    """Reyting ko'rsatish uchun minimal javoblar soni.

    YAGONA MANBA. Ilgari har joyda `MIN_RESPONSES_FOR_RATING` konstantasi
    ishlatilardi, sozlamalar sahifasidagi `survey.min_responses` esa
    saqlanardi-yu, hech kim uni o'qimasdi — admin qiymatni o'zgartirib,
    hech qanday o'zgarish ko'rmasdi. Endi hamma joy shu funksiyadan o'tadi.

    Ustuvorlik: baza > `.env` > kodda yozilgan standart qiymat
    (`SettingsService.get_value` shu tartibda qaytaradi).

    Noto'g'ri qiymat (matn, 0, manfiy son) kelsa konstantaga qaytamiz:
    sozlamada xato bo'lgani uchun reyting 1 ta javobdan chiqib ketishi
    ham, umuman ko'rinmay qolishi ham yomon.
    """
    raw = await SettingsService(session).get_value("survey.min_responses")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return MIN_RESPONSES_FOR_RATING
    return value if value > 0 else MIN_RESPONSES_FOR_RATING


async def _resolve_positive_int(
    session: AsyncSession, key: str, fallback: int
) -> int:
    """Musbat butun sonli sozlamani o'qiydi, noto'g'ri bo'lsa standartga qaytadi."""
    raw = await SettingsService(session).get_value(key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _as_bool(raw: Any) -> bool:
    """Sozlama qiymatini mantiqiy qiymatga keltiradi.

    Baza JSONB da haqiqiy `true`/`false` saqlaydi, `.env` esa matn beradi
    ("true", "1", "yes"). Ikkalasi ham shu yerdan o'tadi.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    return str(raw or "").strip().lower() in {"true", "1", "yes", "on", "ha"}


async def resolve_survey_enabled(session: AsyncSession) -> bool:
    """BOSH kalit: so'rovnoma umuman yaratilsinmi?

    ⚠️ Ilgari bu sozlama saqlanardi-yu, hech kim uni O'QIMASDI — admin
    «yuborish o'chirilgan» deb turib, tugmani bosganda so'rovnoma
    baribir ketardi. Endi yaratishning har ikkala yo'li ham shu
    yerdan o'tadi.
    """
    return _as_bool(await SettingsService(session).get_value("survey.enabled"))


async def resolve_auto_send(session: AsyncSession) -> bool:
    """Kadans bo'yicha avtomatik yuborish yoqilganmi?

    Alohida kalit: `survey.enabled` — «umuman yuborish mumkinmi»,
    bu esa «odam aralashmasdan o'zi yuborsinmi». Haqiqiy mijoz
    guruhlariga avtomatik yozish — ataylab tanlanadigan qadam,
    shuning uchun standart qiymat `false`.
    """
    return _as_bool(await SettingsService(session).get_value("survey.auto_send"))


async def resolve_message_ttl_hours(session: AsyncSession) -> int:
    """Guruhdagi xabar necha soatdan keyin o'chiriladi. `0` — hech qachon.

    Yuqori chegara 48: Telegram botga o'z xabarini shundan keyin
    o'chirishga ruxsat bermaydi. Kattaroq qiymat qo'yilsa jimgina
    48 ga tushiriladi — aks holda admin «o'chadi» deb o'ylab turadi,
    xabar esa guruhda abadiy qolib ketadi.
    """
    raw = await SettingsService(session).get_value("survey.message_ttl_hours")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return SURVEY_MESSAGE_TTL_HOURS
    if value <= 0:
        return 0
    return min(value, TELEGRAM_DELETE_LIMIT_HOURS)


async def resolve_period_days(session: AsyncSession) -> int:
    """So'rovnoma qamrab oladigan davr (kun).

    `resolve_min_responses` bilan bir xil sabab: sozlama panelda bor edi,
    lekin kod `SURVEY_PERIOD_DAYS` konstantasini ishlatardi.
    """
    return await _resolve_positive_int(session, "survey.period_days", SURVEY_PERIOD_DAYS)


async def resolve_suppression_days(session: AsyncSession) -> int:
    """Ikki so'rovnoma orasidagi eng kam tanaffus (kun).

    Diqqat: bu qiymat majburiy yuborishga (`force=true`) ta'sir qilmaydi —
    admin «barchasiga yuborish» tugmasini bosganda tanaffus e'tiborga
    olinmaydi, bu ataylab shunday.
    """
    return await _resolve_positive_int(
        session, "survey.suppression_days", SURVEY_SUPPRESSION_DAYS
    )


class SurveyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Domen yordamchisi shu yerdan ham chaqirilsin — chaqiruvchi
    # `domain.entities` ni alohida import qilmasligi uchun.
    new_token = staticmethod(new_survey_token)

    # ── Ichki yordamchilar ────────────────────────────────────

    async def _by_token(self, token: str) -> tuple[SurveyModel, AgentModel]:
        """So'rovnoma + savdo xodimi. Topilmasa — 404."""
        row = (
            await self._session.execute(
                select(SurveyModel, AgentModel)
                .join(AgentModel, AgentModel.id == SurveyModel.agent_id)
                .where(SurveyModel.token == token)
            )
        ).first()
        if row is None:
            raise NotFoundError("So'rovnoma topilmadi yoki havola noto'g'ri")
        return row[0], row[1]

    # ── Ochish ────────────────────────────────────────────────

    async def open(self, token: str, telegram_user_id: int | None = None) -> dict[str, Any]:
        """Tokenni tekshiradi va so'rovnomani "ochilgan" deb belgilaydi.

        `telegram_user_id` qabul qilinadi, lekin ATAYLAB SAQLANMAYDI.
        Uni ustunga yozish mijozni deanonimlashtiradi: bitta `JOIN` bilan
        "bu 2 yulduzni kim qo'ydi" aniqlanib qoladi. Kelajakda kimdir buni
        "kamchilik" deb tuzatmasligi uchun izoh shu yerda qoldirilgan.
        Kerak bo'lsa — faqat debug log, bazaga emas.
        """
        survey, agent = await self._by_token(token)
        now = datetime.now(UTC)

        if telegram_user_id is not None:
            logger.debug("So'rovnoma ochildi (tg id saqlanmaydi): %s", token)

        # Muddati o'tgan — holatni yangilab qo'yamiz, cron kutib o'tirmaydi
        if survey.expires_at < now:
            # `completed` tegilmaydi — javob berilgan so'rovnoma tugagan
            # hisoblanadi, muddati o'tishi uning tarixini o'zgartirmaydi.
            # Aks holda eski havola ochilganda `response_rate` pasayardi.
            if survey.status not in (SurveyStatus.COMPLETED, SurveyStatus.EXPIRED):
                survey.status = SurveyStatus.EXPIRED
                await self._session.commit()
            raise ConflictError(
                "So'rovnoma muddati o'tgan", code="survey_expired"
            )

        # Guruh so'rovnomasi ko'p kishilik: birinchi baho tushishi bilan
        # `completed` bo'ladi, lekin qolganlar uchun ochiq turishi kerak.
        # Shuning uchun "allaqachon baholangan" faqat eski client oqimida.
        if survey.status is SurveyStatus.COMPLETED and survey.group_id is None:
            raise ConflictError(
                "Bu so'rovnoma allaqachon baholangan", code="survey_completed"
            )

        # `opened_at` — birinchi ochilish vaqti. Qayta ochilsa ustiga
        # yozilmaydi, aks holda javob berish tezligi buzilib ketadi.
        if survey.opened_at is None:
            survey.opened_at = now
        if survey.status is not SurveyStatus.OPENED:
            survey.status = SurveyStatus.OPENED
        await self._session.commit()

        # Faqat bot ekranga chiqaradigan narsa qaytadi — client kimligi yo'q.
        return {
            "agent_name": agent.full_name,
            "period_start": survey.period_start,
            "period_end": survey.period_end,
            "status": survey.status.value,
        }

    # ── Baho qabul qilish ─────────────────────────────────────

    async def submit(
        self,
        token: str,
        csat: int,
        resolution: Resolution | str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Bahoni saqlaydi va so'rovnomani yopadi."""
        survey, agent = await self._by_token(token)
        now = datetime.now(UTC)

        if survey.expires_at < now:
            # `completed` tegilmaydi — javob berilgan so'rovnoma tugagan
            # hisoblanadi, muddati o'tishi uning tarixini o'zgartirmaydi.
            # Aks holda eski havola ochilganda `response_rate` pasayardi.
            if survey.status not in (SurveyStatus.COMPLETED, SurveyStatus.EXPIRED):
                survey.status = SurveyStatus.EXPIRED
                await self._session.commit()
            raise ConflictError(
                "So'rovnoma muddati o'tgan", code="survey_expired"
            )

        # `survey_responses.survey_id` UNIQUE — ikkinchi javob toza 409
        # bo'lishi kerak, IntegrityError traceback emas.
        exists = (
            await self._session.execute(
                select(SurveyResponseModel.id).where(
                    SurveyResponseModel.survey_id == survey.id
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise ConflictError(
                "Bu so'rovnoma allaqachon baholangan", code="survey_completed"
            )

        comment = (comment or "").strip() or None
        response = SurveyResponseModel(
            survey_id=survey.id,
            csat=csat,
            resolution=Resolution(resolution) if resolution else None,
            comment=comment,
            responded_at=now,
            # Ochilgandan javobgacha o'tgan vaqt. Ochilmasdan (masalan
            # to'g'ridan-to'g'ri API orqali) kelsa — o'lchash mumkin emas.
            response_time_sec=(
                int((now - survey.opened_at).total_seconds())
                if survey.opened_at
                else None
            ),
        )
        self._session.add(response)

        survey.status = SurveyStatus.COMPLETED
        survey.completed_at = now

        try:
            await self._session.commit()
        except IntegrityError:
            # Ikkita xabar bir vaqtda kelsa (poyga) — baribir toza 409
            await self._session.rollback()
            raise ConflictError(
                "Bu so'rovnoma allaqachon baholangan", code="survey_completed"
            ) from None

        return {
            "agent_name": agent.full_name,
            "csat": csat,
            "status": survey.status.value,
        }

    # ══════════════════════════════════════════════════════════
    #  Guruh oqimi — bir so'rovnoma, ko'p javob
    #
    #  Bu yerdagi metodlar Telegram identifikatorini KO'RMAYDI.
    #  Bot `sha256(token + ":" + telegram_user_id)` ni o'zi hisoblab,
    #  faqat hash yuboradi. Ya'ni backendda "kim baho qo'ydi" degan
    #  savolga javob beradigan ma'lumot jismonan mavjud emas —
    #  bu ehtiyotkorlik emas, arxitektura qarori.
    # ══════════════════════════════════════════════════════════

    # Holati o'zgartirilmaydigan yakuniy holatlar
    _TERMINAL = (SurveyStatus.COMPLETED, SurveyStatus.EXPIRED)

    async def _ensure_not_expired(self, survey: SurveyModel, now: datetime) -> None:
        """Muddati o'tgan bo'lsa holatni yangilab, 409 chiqaradi.

        Holat shu yerda yangilanadi — cron kutib o'tirmasin, aks holda
        muddati o'tgan so'rovnoma bazada `sent` bo'lib turaveradi.

        ⚠️ `completed` HECH QACHON `expired` ga o'tkazilmaydi. Ilgari
        shunday bo'lardi va bu statistikani jimgina buzardi: `response_rate`
        `status == completed` bo'yicha hisoblanadi, ya'ni kimdir eski
        havolani ochsa, allaqachon javob berilgan so'rovnoma «muddati
        o'tgan» ga aylanib, javob berish darajasi pasayib ketardi.
        Javob berilgan so'rovnoma — tugagan so'rovnoma, muddati o'tishi
        uning tarixini o'zgartirmaydi.
        """
        if survey.expires_at >= now:
            return
        if survey.status not in self._TERMINAL:
            survey.status = SurveyStatus.EXPIRED
            await self._session.commit()
        raise ConflictError("So'rovnoma muddati o'tgan", code="survey_expired")

    async def _survey_by_token(self, token: str) -> SurveyModel:
        survey = (
            await self._session.execute(
                select(SurveyModel).where(SurveyModel.token == token)
            )
        ).scalar_one_or_none()
        if survey is None:
            raise NotFoundError("So'rovnoma topilmadi yoki havola noto'g'ri")
        return survey

    async def mark_sent(self, token: str, chat_message_id: int) -> dict[str, Any]:
        """Bot guruhga xabar tashlagach chaqiradi.

        `chat_message_id` saqlanadi — bot keyin o'sha xabarni tahrirlab
        "12 kishi baho berdi" sonini yangilaydi.
        """
        survey = await self._survey_by_token(token)
        survey.chat_message_id = chat_message_id
        if survey.sent_at is None:
            survey.sent_at = datetime.now(UTC)
        if survey.status is SurveyStatus.PENDING:
            survey.status = SurveyStatus.SENT
        await self._session.commit()
        return {"status": SurveyStatus.SENT.value}

    async def rate(
        self, token: str, respondent_hash: str, csat: int
    ) -> dict[str, Any]:
        """Guruhdagi tugmadan kelgan bahoni qabul qiladi.

        Takroriy hash — XATO EMAS, oddiy holat: odam ikkinchi marta bosdi.
        Shuning uchun 409 emas, `accepted=false, already_rated=true` bilan
        200 qaytadi — bot unga do'stona oyna ko'rsatadi.
        """
        survey = await self._survey_by_token(token)
        now = datetime.now(UTC)

        if survey.expires_at < now:
            # `completed` tegilmaydi — javob berilgan so'rovnoma tugagan
            # hisoblanadi, muddati o'tishi uning tarixini o'zgartirmaydi.
            # Aks holda eski havola ochilganda `response_rate` pasayardi.
            if survey.status not in (SurveyStatus.COMPLETED, SurveyStatus.EXPIRED):
                survey.status = SurveyStatus.EXPIRED
                await self._session.commit()
            raise ConflictError("So'rovnoma muddati o'tgan", code="survey_expired")

        already = (
            await self._session.execute(
                select(SurveyResponseModel.id).where(
                    SurveyResponseModel.survey_id == survey.id,
                    SurveyResponseModel.respondent_hash == respondent_hash,
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            return {
                "accepted": False,
                "response_count": survey.response_count,
                "already_rated": True,
            }

        # ── Tartib muhim ──────────────────────────────────────
        # Avval JAVOB yoziladi (`uq_response_per_respondent` ni ushlaydi),
        # keyin hisoblagich. Teskarisi bo'lsa bir vaqtda kelgan so'rovlar
        # so'rovnoma qatorining qulfida navbatga tizilib, bekorga kutardi.
        self._session.add(
            SurveyResponseModel(
                survey_id=survey.id,
                respondent_hash=respondent_hash,
                csat=csat,
                comment=None,
                red_flags=[],
                responded_at=now,
                response_time_sec=None,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            # Poyga: bir odam tez-tez ikki marta bosdi. Bu ham oddiy holat —
            # 500 emas, o'sha "allaqachon baho berdingiz" javobi.
            await self._session.rollback()
            count = (
                await self._session.execute(
                    select(SurveyModel.response_count).where(
                        SurveyModel.token == token
                    )
                )
            ).scalar_one()
            return {
                "accepted": False,
                "response_count": count,
                "already_rated": True,
            }

        # Hisoblagichni bazaning o'zi oshiradi — Python'da o'qib-yozsak
        # parallel so'rovlar bir-birining natijasini yo'q qilardi.
        count = (
            await self._session.execute(
                update(SurveyModel)
                .where(SurveyModel.id == survey.id)
                .values(response_count=SurveyModel.response_count + 1)
                .returning(SurveyModel.response_count)
                .execution_options(synchronize_session=False)
            )
        ).scalar_one()

        # Birinchi javob tushishi bilan so'rovnoma "javob oldi" hisoblanadi.
        # Guruh uchun bu yopilish emas — `open()` guruh so'rovnomasini
        # `completed` holatida ham ochaveradi.
        if survey.status is not SurveyStatus.COMPLETED:
            survey.status = SurveyStatus.COMPLETED
            survey.completed_at = now
        await self._session.commit()

        return {"accepted": True, "response_count": count, "already_rated": False}

    async def detail(
        self,
        token: str,
        respondent_hash: str,
        comment: str | None = None,
        red_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Shaxsiy chatdagi izoh va red flag'larni mavjud javobga qo'shadi.

        Guruhda yozilgan matnni hamma ko'radi — anonimlik buziladi, shuning
        uchun izoh faqat bot bilan shaxsiy chatda so'raladi.
        """
        survey = await self._survey_by_token(token)

        try:
            flags = normalize_red_flags(red_flags)
        except ValueError as exc:
            raise ValidationError(f"Noma'lum red flag kaliti: {exc}") from None

        response = (
            await self._session.execute(
                select(SurveyResponseModel).where(
                    SurveyResponseModel.survey_id == survey.id,
                    SurveyResponseModel.respondent_hash == respondent_hash,
                )
            )
        ).scalar_one_or_none()
        if response is None:
            raise ConflictError(
                "Avval guruhda ball qo'ying, keyin izoh qoldirishingiz mumkin",
                code="rating_required",
            )

        response.comment = (comment or "").strip() or None
        response.red_flags = flags
        await self._session.commit()

        return {"ok": True}

    # ══════════════════════════════════════════════════════════
    #  Mini App oqimi — bitta sahifada ball + izoh + red flag
    #
    #  Bu metodlar ham Telegram identifikatorini KO'RMAYDI: imzo
    #  presentation qatlamida tekshiriladi va servisga faqat tayyor
    #  `respondent_hash` uzatiladi. Ya'ni "kim baho qo'ydi" degan
    #  ma'lumot bu qatlamgacha yetib ham kelmaydi.
    # ══════════════════════════════════════════════════════════

    async def webapp_open(
        self, token: str, respondent_hash: str
    ) -> dict[str, Any]:
        """Mini App sahifasi ochilganda ko'rsatiladigan ma'lumot.

        Nega eski `open()` qayta ishlatilmadi? U guruhga tegishli bo'lmagan
        so'rovnoma baholangan bo'lsa 409 qaytaradi. Mini App'da esa
        "allaqachon baholadingiz" — XATO EMAS, sahifaning oddiy holati:
        shartnoma bo'yicha bu `already_rated` MAYDONI orqali beriladi va
        409 faqat muddat o'tganda chiqadi. Ikkinchi farq — holat: bu yerda
        `completed` so'rovnoma qayta `opened` ga TUSHIRILMAYDI (guruhda
        allaqachon baho bor, uni "hali baholanmagan" holatiga qaytarish
        hisobotlarni chalg'itadi).
        """
        survey, agent = await self._by_token(token)
        # ORM obyektidan kerakli qiymat DARROV olinadi: pastda `commit()`
        # bo'ladi va obyekt "expired" bo'lib, keyingi murojaat baza bilan
        # yana gaplashishga urinadi.
        agent_name = agent.full_name
        now = datetime.now(UTC)

        await self._ensure_not_expired(survey, now)

        already = (
            await self._session.execute(
                select(SurveyResponseModel.id).where(
                    SurveyResponseModel.survey_id == survey.id,
                    SurveyResponseModel.respondent_hash == respondent_hash,
                )
            )
        ).scalar_one_or_none()

        # `opened_at` — BIRINCHI ochilish vaqti, ustiga yozilmaydi.
        if survey.opened_at is None:
            survey.opened_at = now
        if survey.status in (SurveyStatus.PENDING, SurveyStatus.SENT):
            survey.status = SurveyStatus.OPENED
        await self._session.commit()

        return {
            "token": token,
            "agent_name": agent_name,
            "period_start": survey.period_start,
            "period_end": survey.period_end,
            "already_rated": already is not None,
        }

    async def webapp_submit(
        self,
        token: str,
        respondent_hash: str,
        csat: int,
        comment: str | None = None,
        red_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Sahifadan kelgan to'liq javob: ball + izoh + red flag'lar.

        Guruh oqimi bilan BIR XIL yo'ldan yuradi — `rate()` ballni va
        hisoblagichni, `detail()` esa izoh va red flag'larni yozadi. Shu
        sababli `response_count` ikkala oqimda ham bir xil hisoblanadi va
        guruhdagi «12 kishi baho berdi» xabari to'g'ri qoladi.
        """
        # Red flag kalitlari JAVOB YOZILGUNGA QADAR tekshiriladi.
        # Aks holda noma'lum kalit kelganda ball allaqachon saqlangan
        # bo'lardi-yu, 422 qaytardik: odam qayta yuborsa endi 409 olardi
        # va izohini umuman qoldira olmasdi.
        try:
            flags = normalize_red_flags(red_flags)
        except ValueError as exc:
            raise ValidationError(f"Noma'lum red flag kaliti: {exc}") from None

        _survey, agent = await self._by_token(token)  # noma'lum token — 404
        agent_name = agent.full_name

        result = await self.rate(token, respondent_hash=respondent_hash, csat=csat)
        if not result["accepted"]:
            # `rate()` takroriy hash uchun 200 qaytaradi (guruhda tugmani
            # ikki marta bosish — oddiy hol). Sahifada esa forma bir marta
            # yuboriladi, shuning uchun shartnoma bo'yicha bu 409.
            # Poyga holati ham SHU YERGA tushadi: `rate()` `IntegrityError`
            # ni ushlab `accepted=false` qaytaradi, ya'ni bir vaqtda kelgan
            # so'rovlar 500 emas, toza 409 oladi.
            raise ConflictError(
                "Siz bu so'rovnomaga allaqachon baho bergansiz",
                code="already_rated",
            )

        await self.detail(
            token,
            respondent_hash=respondent_hash,
            comment=comment,
            red_flags=flags,
        )

        return {
            "ok": True,
            "agent_name": agent_name,
            "response_count": result["response_count"],
        }
