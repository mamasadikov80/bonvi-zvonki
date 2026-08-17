"""Bazani ishga tayyorlash.

Dev muhitida jadvallarni modellar asosida yaratadi (idempotent).
Migratsiyalar mavjud bo'lsa — ular ustun turadi.

Ishlab chiqarishda faqat `alembic upgrade head` ishlatilsin.
"""

import asyncio
from pathlib import Path

from sqlalchemy import text

from src.core.database import Base, engine

# Barcha modellar metadata'ga tushishi uchun — YAGONA ro'yxat
from src.core import models as _models  # noqa: F401
from src.modules.regions.application.population import populate_initial_regions

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"

# ══════════════════════════════════════════════════════════════
# Mavjud jadvalga ustun qo'shish
#
# `create_all` faqat YANGI jadval yaratadi — mavjudiga ustun qo'shmaydi.
# Shuning uchun modelga ustun qo'shsangiz, shu yerga ham bir qator
# yozing. Hammasi `IF NOT EXISTS` — necha marta ishlatilsa ham xavfsiz.
#
# Bu vaqtinchalik yechim: haqiqiy migratsiyalar paydo bo'lgach
# (`migrations/versions/` bo'shamay qolganda) bu blok o'tkazib yuboriladi.
# ══════════════════════════════════════════════════════════════
COLUMN_PATCHES: list[str] = [
    # Admin yozadigan qo'shimcha baholash ko'rsatmalari
    "ALTER TABLE rubrics ADD COLUMN IF NOT EXISTS extra_rules TEXT",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255)",
    # ── Guruh asosidagi so'rovnoma ────────────────────────────
    # `surveys` — guruhga bog'lanish, guruhdagi xabar id va keshlangan son
    "ALTER TABLE surveys ADD COLUMN IF NOT EXISTS group_id UUID",
    "ALTER TABLE surveys ADD COLUMN IF NOT EXISTS chat_message_id BIGINT",
    "ALTER TABLE surveys ADD COLUMN IF NOT EXISTS response_count INTEGER "
    "NOT NULL DEFAULT 0",
    # Guruh so'rovnomasida client yo'q — ustun bo'sh qolishi kerak
    "ALTER TABLE surveys ALTER COLUMN client_id DROP NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_surveys_group_id ON surveys (group_id)",
    # FK ni `IF NOT EXISTS` bilan qo'shib bo'lmaydi — `pg_constraint` dan
    # qaraymiz. `telegram_groups` shu paytda `create_all` tomonidan
    # yaratilgan bo'ladi (COLUMN_PATCHES undan keyin ishlaydi).
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'surveys_group_id_fkey'
        ) THEN
            ALTER TABLE surveys ADD CONSTRAINT surveys_group_id_fkey
            FOREIGN KEY (group_id) REFERENCES telegram_groups(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
    # `survey_responses` — anonim dedup hash va red flag'lar
    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS "
    "respondent_hash VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_survey_responses_respondent_hash "
    "ON survey_responses (respondent_hash)",
    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS red_flags JSONB "
    "NOT NULL DEFAULT '[]'::jsonb",
    # ⚠️ `survey_id` dagi YAKKA UNIQUE olib tashlanadi: endi bitta
    # so'rovnomaga o'nlab mijoz javob beradi. SQLAlchemy uni UNIQUE INDEX
    # sifatida yaratgan (`unique=True, index=True`), eski bazalarda esa
    # CONSTRAINT bo'lishi mumkin — ikkalasi ham tekshiriladi.
    "ALTER TABLE survey_responses DROP CONSTRAINT IF EXISTS "
    "survey_responses_survey_id_key",
    "DROP INDEX IF EXISTS ix_survey_responses_survey_id",
    "CREATE INDEX IF NOT EXISTS ix_survey_responses_survey_id "
    "ON survey_responses (survey_id)",
    # O'rniga birgalikdagi unique: bir odam bitta so'rovnomaga bir marta.
    # `respondent_hash` NULL bo'lgan eski javoblarga ta'sir qilmaydi.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_response_per_respondent "
    "ON survey_responses (survey_id, respondent_hash)",
    # ── Avtomatik biriktirish ─────────────────────────────────
    # `agents` — xodimning Telegram identifikatori. Bir martalik
    # ro'yxatdan o'tishda (`POST /agents/enroll`) to'ldiriladi.
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT",
    # UNIQUE: bitta Telegram akkaunti ikkita xodimga tegishli bo'lolmaydi.
    # `CREATE UNIQUE INDEX` — `ADD CONSTRAINT` da `IF NOT EXISTS` yo'q.
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_agents_telegram_user_id "
    "ON agents (telegram_user_id)",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS enrolled_at "
    "TIMESTAMP WITH TIME ZONE",
    # `telegram_groups` — biriktirishni kim qilgani.
    # NULL — hech kim biriktirmagan. 'manual' bo'lsa avtomatika tegmaydi.
    "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS bound_by VARCHAR(16)",
    # Sahifalash va daraxt uchun: 1000 ta guruhda `agent_id + region`
    # bo'yicha yig'ish har safar to'liq skan qilmasin.
    "CREATE INDEX IF NOT EXISTS ix_telegram_groups_agent_region "
    "ON telegram_groups (agent_id, region)",
    # ── AI quvuri ─────────────────────────────────────────────
    # `needs_review` bayrog'ining SABABI. Bo'sh ro'yxat = tekshiruv
    # kerak emas. Busiz menejer navbatda «nega bu qo'ng'iroq shu
    # yerda?» degan savolga javob topa olmaydi.
    "ALTER TABLE call_scores ADD COLUMN IF NOT EXISTS review_reasons JSONB "
    "NOT NULL DEFAULT '[]'::jsonb",
    # ── So'rovnoma xabarini guruhdan olib tashlash ────────────
    # Muddat tugagach bot xabarni o'chiradi va shu ustunni to'ldiradi.
    # Busiz o'chirilgan xabar har aylanishda navbatga qaytib turardi.
    "ALTER TABLE surveys ADD COLUMN IF NOT EXISTS message_deleted_at "
    "TIMESTAMP WITH TIME ZONE",
    # Navbat so'rovi: «yuborilgan, hali o'chirilmagan» xabarlar.
    # Qisman indeks — jadvalning katta qismi (o'chirilganlar) tushmaydi.
    "CREATE INDEX IF NOT EXISTS ix_surveys_message_pending "
    "ON surveys (sent_at) "
    "WHERE chat_message_id IS NOT NULL AND message_deleted_at IS NULL",
    # ── Baho dalillari alohida ustunga ────────────────────────
    # `call_scores.blocks` endi TEKIS `{blok: ball}` — analitika razrezi
    # va tafsilot sahifasi shuni kutadi. Kriteriya dalillari va hisob-kitob
    # izohi esa shu ustunga tushadi, aks holda ular yo'qolardi.
    "ALTER TABLE call_scores ADD COLUMN IF NOT EXISTS block_details JSONB",
    # ── Faol rubrika — bittadan ortiq bo'lolmaydi ─────────────
    # Eski `ix_rubrics_is_active` oddiy indeks edi: ikkita `is_active = true`
    # qatori paydo bo'lsa `RubricService.get_active()` `MultipleResultsFound`
    # bilan butun baholashni to'xtatardi. Qisman unikal indeks buni bazaning
    # o'zida taqiqlaydi (`false` tarixiy versiyalarga tegmaydi).
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_rubrics_single_active "
    "ON rubrics (is_active) WHERE is_active",
    "DROP INDEX IF EXISTS ix_rubrics_is_active",
    # ── So'rovnomaning HUDUD NUSXASI (arxiv) ──────────────────
    # Hisobot ilgari hududni tirik `telegram_groups.region` dan
    # o'qirdi, shuning uchun guruh hududi o'zgarsa O'TGAN oylarning
    # bahosi ham boshqa hududga ko'chib ketardi. Endi so'rovnoma
    # o'z nusxasini saqlaydi.
    "ALTER TABLE surveys ADD COLUMN IF NOT EXISTS region VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_surveys_region ON surveys (region)",
    # Mavjud yozuvlarni bir martalik to'ldirish: hozirgi tirik qiymat
    # — bizda bor yagona haqiqat. `IS NULL` sharti tufayli takroriy
    # ishga tushirishda hech narsa o'zgarmaydi (idempotent).
    """
    UPDATE surveys s
       SET region = COALESCE(
               (SELECT g.region FROM telegram_groups g WHERE g.id = s.group_id),
               (SELECT a.region FROM agents a WHERE a.id = s.agent_id)
           )
     WHERE s.region IS NULL;
    """,
    # ── MoyZvonki'dagi mijoz nomi va raqami ───────────────────
    # `calls.client_id` faqat raqam bizning katalogimizda topilganda
    # to'ladi — qolgan hamma qatorda mijoz ustuni bo'sh turardi.
    # Endi MoyZvonki bergan nom va raqam qo'ng'iroqning o'zida saqlanadi.
    "ALTER TABLE calls ADD COLUMN IF NOT EXISTS client_name VARCHAR(255)",
    "ALTER TABLE calls ADD COLUMN IF NOT EXISTS client_phone VARCHAR(32)",
    "CREATE INDEX IF NOT EXISTS ix_calls_client_phone ON calls (client_phone)",
    # ── «Til» ustuni butunlay olib tashlandi ──────────────────
    # Qo'ng'iroqlarning deyarli hammasi o'zbek/rus aralash — ustun
    # hech narsani ajratmasdi, filtri esa allaqachon ishlatilmasdi.
    # Indeks ustundan oldin tushadi (`DROP COLUMN` uni o'zi ham
    # olib tashlaydi, lekin tartib aniq bo'lgani yaxshi).
    # ── Xodim arxivi ──────────────────────────────────────────
    # Ma'lumoti bor xodim O'CHIRILMAYDI — arxivga o'tadi. `calls` da
    # `ON DELETE CASCADE` bor, ya'ni qator o'chsa baholar ham ketardi.
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_at "
    "TIMESTAMP WITH TIME ZONE",
    "CREATE INDEX IF NOT EXISTS ix_agents_archived_at ON agents (archived_at)",
    # ── Qo'ng'iroq turi ───────────────────────────────────────
    # Baholash faqat savdo qo'ng'iroqlariga qo'llanadi — ichki va
    # shaxsiy suhbatlar xodimning o'rtachasini pasaytirmasin.
    "ALTER TABLE calls ADD COLUMN IF NOT EXISTS call_type VARCHAR(16)",
    "ALTER TABLE calls ADD COLUMN IF NOT EXISTS call_type_reason VARCHAR(300)",
    "ALTER TABLE calls ADD COLUMN IF NOT EXISTS call_type_confidence NUMERIC(3,2)",
    "CREATE INDEX IF NOT EXISTS ix_calls_call_type ON calls (call_type)",
    "DROP INDEX IF EXISTS ix_calls_language",
    "ALTER TABLE calls DROP COLUMN IF EXISTS language",
    # ── Eski ASR sozlamalarini tozalash ───────────────────────
    # `asr.provider` va vendor kalitlari REYESTRDAN olib tashlandi:
    # ular hech qayerda o'qilmasdi, haqiqiy tanlov `ai.*` da. Bazada
    # qolgan qatorlar `get_all_values()` javobini ifloslantiradi va
    # kelajakda «bu qayerdan keldi?» degan savol tug'diradi.
    #
    # ⚠️ `asr.min_duration_sec` ATAYLAB QOLDIRILDI — u tirik sozlama.
    # `asr.min_duration_sec` → `ai.min_duration_sec`: sozlama AI
    # kategoriyasiga ko'chdi, kalit prefiksi ham ergashishi kerak
    # (kategoriya kalitdan ajratib olinadi). Admin qo'ygan qiymat
    # yo'qolmasin — avval ko'chiriladi, keyin eskisi o'chiriladi.
    """
    INSERT INTO app_settings (id, key, category, value)
    SELECT gen_random_uuid(), 'ai.min_duration_sec', 'ai', value
      FROM app_settings
     WHERE key = 'asr.min_duration_sec'
    ON CONFLICT (key) DO NOTHING;
    """,
    """
    DELETE FROM app_settings
     WHERE key IN ('asr.provider', 'asr.enable_vad', 'asr.min_duration_sec',
                   'asr.elevenlabs_api_key', 'asr.groq_api_key',
                   'asr.kotib_api_key',
                   'ai.groq_api_key', 'ai.elevenlabs_api_key',
                   'llm.provider', 'llm.model', 'llm.escalation_model',
                   'llm.use_batch', 'llm.audit_sample_percent',
                   'llm.anthropic_api_key');
    """,
]


async def main() -> None:
    if VERSIONS_DIR.exists() and any(VERSIONS_DIR.glob("*.py")):
        print("  ℹ️  Migratsiyalar mavjud — bootstrap o'tkazib yuborildi")
        return

    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
        await conn.run_sync(Base.metadata.create_all)

        for statement in COLUMN_PATCHES:
            await conn.execute(text(statement))

        # Hududlar ro'yxati bo'sh bo'lsa — mavjud xodim/mijoz/guruhlardagi
        # qiymatlardan to'ldiriladi. Busiz birinchi ishga tushirishda har bir
        # xodimning hududi ro'yxatdan tashqarida qolardi. Idempotent.
        added_regions = await populate_initial_regions(conn)

    tables = ", ".join(sorted(Base.metadata.tables))
    print(f"  ✅ Jadvallar tayyor: {tables}")
    if COLUMN_PATCHES:
        print(f"  ✅ Ustun tuzatishlari: {len(COLUMN_PATCHES)} ta")
    if added_regions:
        print(f"  ✅ Hududlar qo'shildi: {', '.join(added_regions)}")
    else:
        print("  ℹ️  Hududlar allaqachon to'ldirilgan")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
