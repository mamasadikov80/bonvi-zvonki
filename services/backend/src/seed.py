"""Boshlang'ich va namunaviy ma'lumotlar.

Ishga tushirish:
    make seed                 — yetishmayotganini qo'shadi
    make seed-reset           — demo ma'lumotni tozalab qayta yaratadi

IDEMPOTENT: bir necha marta ishga tushirsa ham dublikat yaratmaydi.
Yangi savdo xodimi qo'shilsa — faqat unga qo'ng'iroq va baho generatsiya
qilinadi, mavjudlariga tegilmaydi.
"""

import argparse
import asyncio
import random
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import SessionFactory
from src.core.security import hash_password
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel

# ⚠️ Import SHART: `surveys` jadvali `clients` va `telegram_groups` ga
# FK bilan bog'langan, ORM esa yozishdan oldin jadvallarni bog'liqlik
# tartibida saralaydi. Modellar metadata'da bo'lmasa saralash
# `NoReferencedTableError` bilan uziladi — seed yiqiladi, uvicorn esa
# `&&` zanjiri tufayli umuman ishga tushmaydi. Sababi va tarixi:
# `src/core/models.py` dagi izoh.
from src.core import models as _models  # noqa: F401
from src.modules.scoring.domain.entities import RedFlagType, ScoreBlock, Sentiment
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.surveys.domain.entities import (
    SURVEY_PERIOD_DAYS,
    SURVEY_TOKEN_TTL_DAYS,
    Resolution,
    SurveyChannel,
    SurveyStatus,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.users.domain.entities import Role
from src.modules.users.infrastructure.models import UserModel

random.seed(42)

# Har savdo xodimiga kamida shuncha client biriktiriladi
MIN_CLIENTS_PER_AGENT = 8

# ══════════════════════════════════════════════════════════════
#  SAVDO XODIMLARI
#  Rejadagi shtat: 15 nafar, 6 ta hududga taqsimlangan.
#  (full_name, hudud, rang, o'rtacha ball, tajriba oyi)
# ══════════════════════════════════════════════════════════════

AGENTS: list[tuple[str, str, str, int, int]] = [
    # ── Toshkent (4) ──────────────────────────────────────────
    ("Sardor Yo'ldoshev",    "Toshkent",         "#6366f1", 86, 34),
    ("Otabek Nazarov",       "Toshkent",         "#ef4444", 75, 18),
    ("Kamola Rasulova",      "Toshkent",         "#a855f7", 83, 26),
    ("Javohir Abdullayev",   "Toshkent",         "#0ea5e9", 71, 9),
    # ── Farg'ona vodiysi (3) ──────────────────────────────────
    ("Aziz Rahmonov",        "Farg'ona vodiysi", "#8b5cf6", 79, 22),
    ("Sanjar Qodirov",       "Farg'ona vodiysi", "#14b8a6", 84, 30),
    ("Dilnoza Umarova",      "Farg'ona vodiysi", "#f43f5e", 77, 14),
    # ── Samarqand (2) ─────────────────────────────────────────
    ("Bekzod Tursunov",      "Samarqand",        "#10b981", 89, 41),
    ("Malika Sobirova",      "Samarqand",        "#d946ef", 80, 20),
    # ── Buxoro (2) ────────────────────────────────────────────
    ("Jasur Karimov",        "Buxoro",           "#ec4899", 62, 7),
    ("Shohruh Bobojonov",    "Buxoro",           "#f59e0b", 73, 16),
    # ── Xorazm (2) ────────────────────────────────────────────
    ("Nodir Ergashev",       "Xorazm",           "#eab308", 72, 12),
    ("Feruza Matyoqubova",   "Xorazm",           "#22c55e", 81, 24),
    # ── Surxondaryo (2) ───────────────────────────────────────
    ("Doniyor Salimov",      "Surxondaryo",      "#06b6d4", 68, 11),
    ("Ulug'bek Xolmatov",    "Surxondaryo",      "#7c3aed", 76, 19),
]

CLIENT_NAMES = [
    "Akmal aka", "Rustam aka", "Dilshod aka", "Farrux aka", "Shuhrat aka",
    "Ulug'bek aka", "Bahodir aka", "Timur aka", "Alisher aka", "Kamol aka",
    "Zafar aka", "Murod aka", "Anvar aka", "Qahramon aka", "Sherzod aka",
    "Nodira opa", "Gulnora opa", "Zulfiya opa", "Mavluda opa", "Sevara opa",
]

SHOPS = [
    "Bahor savdo", "Zamon market", "Oltin do'kon", "Yangi asr", "Marvarid",
    "Nur savdo", "Baraka market", "Chinor", "Sharq savdo", "Diyor",
    "Umid savdo", "Bir dona", "Ziyo market", "Hilol", "Obod savdo",
]

COACHING_NOTES = [
    "Mahsulotni yaxshi taqdim etdi, lekin client'ning byudjet e'tiroziga javob bermadi. Tavsiya: e'tiroz bilan ishlash treningi.",
    "Ehtiyojni aniqlash bosqichi kuchli. Yopish urinishi yetishmadi — suhbat aniq kelishuvsiz tugadi.",
    "Client'ni bir necha marta bo'ldi. Tinglash ko'nikmasiga e'tibor berish kerak.",
    "Ajoyib suhbat. Ehtiyoj aniqlandi, mos taklif berildi, keyingi qadam belgilandi.",
    "Narx haqida noaniq ma'lumot berildi. Rasmiy narxlar ro'yxatini takrorlash kerak.",
    "Upsell imkoniyati o'tkazib yuborildi — client qo'shimcha model haqida so'radi, javob berilmadi.",
    "Yetkazib berish muddati aniq aytilmadi. Client ikki marta so'radi.",
    "Client bilan ishonchli munosabat qurildi, ohang juda yaxshi. Texnik savollarda biroz qiynaldi.",
]

TRANSCRIPT = """[00:03] Xodim: Assalomu alaykum, men {agent}, Bonvi kompaniyasidan qo'ng'iroq qilyapman.
[00:08] Client: Vaalaykum assalom, xo'sh, eshitaman.
[00:12] Xodim: {client}, o'tgan haftadagi buyurtmangiz bo'yicha gaplashmoqchi edim. Mahsulot yetib bordimi?
[00:21] Client: Ha, yetib keldi, rahmat. Faqat bitta savol bor edi — {product} modelidan yana bormi?
[00:31] Xodim: Ha, omborda bor. Nechta kerak bo'lardi?
[00:36] Client: {qty} ta bo'lsa yaxshi bo'lardi. Narxi qanday?
[00:42] Xodim: {qty} ta uchun chegirma qo'llaymiz. Hozir aniq narxni aytib beraman...
[04:18] Client: Yaxshi. To'lovni qachongacha qilsam bo'ladi?
[04:25] Xodim: Odatdagidek, yetkazib berilgandan keyin bir hafta ichida.
[07:42] Xodim: Ertaga ertalab yetkazib beramiz, xotirjam bo'ling.
[08:10] Client: Mayli, kelishdik. Rahmat.
[08:15] Xodim: Sizga ham rahmat, {client}. Xayrli kun!"""

PRODUCTS = ["X-200", "X-350", "Y-50", "Y-120", "Z-900", "Z-1500"]


# ══════════════════════════════════════════════════════════════
#  CLIENT BAHOLARI (so'rovnoma javoblari)
#
#  Maqsad — sahifa bo'sh turmasin va soxta ko'rinmasin:
#    · har xodimda kamida MIN_RESPONSES_PER_AGENT ta javob
#    · baholar xodimning AI balliga bog'liq (kuchli ~4.5, zaif ~3.2)
#    · izohlar baho darajasiga qarab boshqacha yoziladi
#    · bir qism so'rovnoma javobsiz qoladi — javob darajasi 100% emas
# ══════════════════════════════════════════════════════════════

# MIN_RESPONSES_FOR_RATING = 5 dan sezilarli yuqori olinadi, aks holda
# bitta-ikkita javob yo'qolsa reyting sahifadan g'oyib bo'ladi.
MIN_RESPONSES_PER_AGENT = 12

# Javoblar shu oyna ichida tarqatiladi — sana filtri sezilarli ishlasin
SURVEY_WINDOW_DAYS = 90

# Qat'iy urug': toza bazaga qayta seed qilinsa aynan o'sha demo chiqadi.
# Xodim ismiga bog'lanadi — bosqichlar tartibi o'zgarsa ham natija bir xil.
SURVEY_RNG_SEED = "bonvi-client-ratings"

# Izohlar do'kondor yozganday: qisqa, ko'pincha kichik harf bilan,
# ba'zan aniq shikoyat, ba'zan quruq rahmat.
COMMENTS_BY_CSAT: dict[int, list[str]] = {
    5: [
        "rahmat, hammasi joyida",
        "juda yaxshi ishladi, tez javob berdi",
        "har doim vaqtida yetkazadi. rahmat",
        "muammoni darrov hal qilib berdi",
        "savolimga aniq javob oldim, savol qolmadi",
        "narxni ham tushirib berdi, xursandman",
        "gaplashish madaniyati zo'r ekan",
        "buyurtma ertasiga yetib keldi, zo'r",
        "doim shunday bo'lsin, rahmat katta",
        "ishonchli odam, ikkinchi marta ishlayapmiz",
        "hujjatlarni ham tez yubordi",
        "hech qanday e'tirozim yo'q",
    ],
    4: [
        "yaxshi, faqat yetkazish bir kun kechikdi",
        "umuman yaxshi. narxlar ro'yxatini oldindan yuborsa bo'lardi",
        "hammasi joyida, telefonga birozdan keyin javob berdi",
        "yaxshi ishladi, rahmat",
        "aytgan vaqtida qildi, kichik kamchiliklar bor",
        "qoniqarli. keyingi safar chegirma bo'lsa yaxshi bo'lardi",
        "mahsulot yaxshi keldi, hujjat kech keldi",
        "o'zi qayta qo'ng'iroq qilsa yana yaxshi bo'lardi",
        "yaxshi, lekin bir marta eslatishimga to'g'ri keldi",
    ],
    3: [
        "o'rtacha. yetkazish kechikdi",
        "javobni uzoq kutdim",
        "narx haqida aniq gapirmadi",
        "ba'zi savollarimga javob topolmadi",
        "hammasi bo'ldi, lekin sekin",
        "ikki marta qayta qo'ng'iroq qilishga to'g'ri keldi",
        "mahsulot keldi, lekin miqdori kam edi",
        "yomon emas, lekin yaxshi ham emas",
    ],
    2: [
        "ikki kun kutdim, javob bo'lmadi",
        "aytgan narxi bilan hisob-kitob mos kelmadi",
        "buyurtma to'liq kelmadi",
        "telefonni ko'tarmadi, o'zim izlab topdim",
        "va'da qilgan muddatda yetkazmadi",
        "gaplashish uslubi menga yoqmadi",
        "har safar qaytadan tushuntirishimga to'g'ri keladi",
    ],
    1: [
        "umuman javob bermadi",
        "bir hafta kutdim, hech kim qo'ng'iroq qilmadi",
        "buyurtmani bekor qildim, xizmat yomon",
        "pulni oldi, mahsulot kelmadi. juda yomon",
        "boshqa ishlamayman",
        "shikoyat qildim, hech kim e'tibor bermadi",
    ],
}

# Norozi client ko'proq yozadi — umumiy ulush ~75%
COMMENT_CHANCE: dict[int, float] = {5: 0.70, 4: 0.72, 3: 0.80, 2: 0.88, 1: 0.92}

# 2-savol ("muammoingiz hal bo'ldimi?") — baho bilan bog'liq
RESOLUTION_WEIGHTS: dict[int, tuple[int, int, int]] = {  # (ha, qisman, yo'q)
    5: (92, 8, 0),
    4: (74, 23, 3),
    3: (28, 56, 16),
    2: (8, 42, 50),
    1: (3, 17, 80),
}


# ══════════════════════════════════════════════════════════════
#  Bosqichlar
# ══════════════════════════════════════════════════════════════


async def ensure_admin(session: AsyncSession) -> None:
    exists = (
        await session.execute(
            select(UserModel).where(UserModel.email == settings.FIRST_ADMIN_EMAIL.lower())
        )
    ).scalar_one_or_none()

    if exists:
        print("  ℹ️  Admin allaqachon mavjud")
        return

    session.add(
        UserModel(
            email=settings.FIRST_ADMIN_EMAIL.lower(),
            password_hash=hash_password(settings.FIRST_ADMIN_PASSWORD),
            full_name="Bosh administrator",
            role=Role.ADMIN,
            is_active=True,
        )
    )
    await session.commit()
    print(f"  ✅ Admin yaratildi: {settings.FIRST_ADMIN_EMAIL}")


async def ensure_agents(session: AsyncSession) -> list[AgentModel]:
    """Yetishmayotgan savdo xodimlarini qo'shadi. Mavjudlariga tegmaydi."""
    existing = {
        a.full_name: a
        for a in (await session.execute(select(AgentModel))).scalars().all()
    }

    created: list[str] = []
    for full_name, region, color, _score, months in AGENTS:
        if full_name in existing:
            continue
        agent = AgentModel(
            full_name=full_name,
            region=region,
            color=color,
            phone=f"+9989{random.randint(10000000, 99999999)}",
            hired_at=(datetime.now(UTC) - timedelta(days=months * 30)).date(),
            is_active=True,
        )
        session.add(agent)
        existing[full_name] = agent
        created.append(full_name)

    await session.commit()

    if created:
        print(f"  ✅ {len(created)} ta yangi savdo xodimi qo'shildi:")
        for name in created:
            print(f"       · {name}")
    else:
        print(f"  ℹ️  Barcha {len(AGENTS)} ta savdo xodimi allaqachon mavjud")

    return [existing[name] for name, *_ in AGENTS]


async def ensure_accounts(session: AsyncSession, agents: list[AgentModel]) -> None:
    """Menejer, kuzatuvchi va bitta savdo xodimi hisobi."""
    accounts = [
        ("manager@zvonki.uz", "manager12345", "Nilufar Azizova", Role.MANAGER, None),
        ("viewer@zvonki.uz", "viewer12345", "Monitor (savdo xonasi)", Role.VIEWER, None),
        ("sardor@zvonki.uz", "sardor12345", agents[0].full_name, Role.SALES, agents[0].id),
    ]

    created = 0
    for email, password, name, role, agent_id in accounts:
        exists = (
            await session.execute(select(UserModel).where(UserModel.email == email))
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(
            UserModel(
                email=email,
                password_hash=hash_password(password),
                full_name=name,
                role=role,
                agent_id=agent_id,
                is_active=True,
            )
        )
        created += 1

    await session.commit()
    print(f"  {'✅' if created else 'ℹ️ '} Hisoblar: {created} ta yangi")


async def ensure_clients(
    session: AsyncSession, agents: list[AgentModel]
) -> dict[str, list[ClientModel]]:
    """Har xodimga 6–10 tadan client. Mavjudlari saqlanadi."""
    by_agent: dict[str, list[ClientModel]] = {}
    created = 0
    index = 0

    for agent in agents:
        rows = (
            (
                await session.execute(
                    select(ClientModel).where(ClientModel.agent_id == agent.id)
                )
            )
            .scalars()
            .all()
        )
        rows = list(rows)

        # Tasodifiy son EMAS — aks holda har ishga tushirishda
        # yangi clientlar qo'shilib ketaveradi.
        target = MIN_CLIENTS_PER_AGENT
        while len(rows) < target:
            client = ClientModel(
                name=CLIENT_NAMES[index % len(CLIENT_NAMES)],
                shop_name=f"{SHOPS[index % len(SHOPS)]} #{index + 1}",
                region=agent.region,
                phone=f"+9989{random.randint(10000000, 99999999)}",
                agent_id=agent.id,
                is_active=True,
            )
            session.add(client)
            rows.append(client)
            created += 1
            index += 1

        by_agent[str(agent.id)] = rows

    await session.commit()
    print(f"  {'✅' if created else 'ℹ️ '} Clientlar: {created} ta yangi")
    return by_agent


async def ensure_calls(
    session: AsyncSession,
    agents: list[AgentModel],
    clients_by_agent: dict[str, list[ClientModel]],
    days: int = 60,
) -> None:
    """Qo'ng'iroq va bahosi YO'Q xodimlar uchun demo tarix yaratadi."""
    base_scores = {name: score for name, _r, _c, score, _m in AGENTS}

    now = datetime.now(UTC)
    total_calls = 0
    skipped = 0

    for agent in agents:
        has_calls = (
            await session.execute(
                select(func.count(CallModel.id)).where(CallModel.agent_id == agent.id)
            )
        ).scalar_one()

        if has_calls:
            skipped += 1
            continue

        clients = clients_by_agent.get(str(agent.id), [])
        if not clients:
            continue

        base = base_scores.get(agent.full_name, 75)

        for day_offset in range(days):
            day = now - timedelta(days=day_offset)
            if day.weekday() == 6:  # yakshanba
                continue

            for _ in range(random.randint(8, 16)):
                started = day.replace(
                    hour=random.randint(9, 18),
                    minute=random.randint(0, 59),
                    second=0,
                    microsecond=0,
                )
                client = random.choice(clients)
                product = random.choice(PRODUCTS)
                qty = random.choice([10, 20, 30, 50, 100])

                call = CallModel(
                    external_id=f"demo-{secrets.token_hex(8)}",
                    agent_id=agent.id,
                    client_id=client.id,
                    direction=CallDirection.OUTBOUND,
                    status=CallStatus.COMPLETED,
                    started_at=started,
                    duration_sec=random.randint(240, 1200),
                    transcript=TRANSCRIPT.format(
                        agent=agent.full_name.split()[0],
                        client=client.name,
                        product=product,
                        qty=qty,
                    ),
                )
                session.add(call)
                await session.flush()
                total_calls += 1

                # Ball agentning bazasi atrofida, vaqt o'tishi bilan biroz o'sadi
                trend = (days - day_offset) * 0.08
                overall = int(max(25, min(98, random.gauss(base + trend, 9))))

                blocks = {
                    ScoreBlock.SCRIPT.value: _clamp(overall * 0.25, 4, 25),
                    ScoreBlock.COMMUNICATION.value: _clamp(overall * 0.25, 4, 25),
                    ScoreBlock.RESOLUTION.value: _clamp(overall * 0.25, 4, 25),
                    ScoreBlock.SALES_SKILL.value: _clamp(overall * 0.25, 4, 25),
                }

                red_flags = []
                if random.random() < (0.16 if overall < 60 else 0.03):
                    flag = random.choice(list(RedFlagType))
                    red_flags.append(
                        {
                            "type": flag.value,
                            "severity": random.choice(["medium", "high"]),
                            "timestamp": f"0{random.randint(1, 9)}:{random.randint(10, 59)}",
                            "quote": "Ertaga ertalab yetkazib beramiz",
                        }
                    )

                session.add(
                    CallScoreModel(
                        call_id=call.id,
                        model="claude-haiku-4-5",
                        rubric_version="v1",
                        overall_score=overall,
                        blocks=blocks,
                        red_flags=red_flags,
                        outcome_signal={
                            "type": random.choices(
                                ["order_agreed", "follow_up", "info_only", "rejected"],
                                weights=[35, 30, 20, 15],
                            )[0],
                            "confidence": round(random.uniform(0.6, 0.95), 2),
                        },
                        sentiment=random.choices(
                            [s.value for s in Sentiment], weights=[50, 35, 15]
                        )[0],
                        coaching_note=random.choice(COACHING_NOTES),
                        confidence=round(random.uniform(0.65, 0.98), 2),
                        needs_review=random.random() < 0.06,
                        scored_at=started + timedelta(hours=8),
                        cost_usd=round(random.uniform(0.003, 0.008), 5),
                    )
                )

        await session.commit()
        print(f"       · {agent.full_name}: qo'ng'iroqlar yaratildi")

    if skipped:
        print(f"  ℹ️  {skipped} ta xodimda tarix bor edi — tegilmadi")
    if total_calls:
        print(f"  ✅ {total_calls} ta yangi qo'ng'iroq + baho")


async def ensure_surveys(
    session: AsyncSession,
    agents: list[AgentModel],
    clients_by_agent: dict[str, list[ClientModel]],
    window_days: int = SURVEY_WINDOW_DAYS,
) -> None:
    """Har xodimda kamida MIN_RESPONSES_PER_AGENT ta javob bo'lishini ta'minlaydi.

    IDEMPOTENT: oynadagi mavjud javoblar sanaladi va faqat yetishmagani
    qo'shiladi. Ikkinchi marta ishga tushirilsa hech narsa qo'shilmaydi.
    """
    base_scores = {name: score for name, _r, _c, score, _m in AGENTS}
    now = datetime.now(UTC)
    since = now - timedelta(days=window_days)

    moved = await _pull_back_future_surveys(session, now)
    if moved:
        print(f"  🔧 {moved} ta kelajak sanali javob o'tmishga surildi")

    new_surveys = new_responses = 0
    topped: list[str] = []

    for agent in agents:
        existing = (
            await session.execute(
                select(func.count(SurveyResponseModel.id))
                .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
                .where(
                    SurveyModel.agent_id == agent.id,
                    SurveyResponseModel.responded_at >= since,
                )
            )
        ).scalar_one()

        if existing >= MIN_RESPONSES_PER_AGENT:
            continue

        clients = clients_by_agent.get(str(agent.id), [])
        if not clients:
            continue

        # Urug' xodim ismiga bog'langan — boshqa bosqichlar nechta
        # tasodifiy son "yeganidan" qat'i nazar natija bir xil chiqadi.
        rng = random.Random(f"{SURVEY_RNG_SEED}:{agent.full_name}")

        target = rng.randint(MIN_RESPONSES_PER_AGENT + 4, MIN_RESPONSES_PER_AGENT + 10)
        need = target - existing
        # Javob berish darajasi 55–72% — qolganlari javobsiz qoladi
        unanswered = max(4, round(need / rng.uniform(0.55, 0.72)) - need)

        mean = _csat_mean(base_scores.get(agent.full_name, 75))

        # ── Javob berilgan so'rovnomalar ──────────────────────
        for _ in range(need):
            survey = _make_survey(agent, rng.choice(clients), rng, now, window_days)
            session.add(survey)
            await session.flush()
            new_surveys += 1

            csat = max(1, min(5, round(rng.gauss(mean, 0.6))))
            opened_at = survey.sent_at + timedelta(
                hours=rng.randint(1, 30), minutes=rng.randint(0, 59)
            )
            response_time = rng.randint(15, 210)
            completed_at = opened_at + timedelta(seconds=response_time)

            survey.status = SurveyStatus.COMPLETED
            survey.opened_at = opened_at
            survey.completed_at = completed_at

            comment = (
                rng.choice(COMMENTS_BY_CSAT[csat])
                if rng.random() < COMMENT_CHANCE[csat]
                else None
            )
            session.add(
                SurveyResponseModel(
                    survey_id=survey.id,
                    csat=csat,
                    resolution=rng.choices(
                        [Resolution.YES, Resolution.PARTIAL, Resolution.NO],
                        weights=RESOLUTION_WEIGHTS[csat],
                    )[0],
                    comment=comment,
                    comment_sentiment=_sentiment_of(csat) if comment else None,
                    responded_at=completed_at,
                    response_time_sec=response_time,
                )
            )
            new_responses += 1

        # ── Javobsiz qolganlar ────────────────────────────────
        for index in range(unanswered):
            # Kamida ikkitasi yaqin kunlarda — tokeni tirik qoladi,
            # /surveys/{token}/open ni sinab ko'rish uchun kerak.
            survey = _make_survey(
                agent, rng.choice(clients), rng, now, window_days, live=index < 2
            )
            if survey.expires_at < now:
                survey.status = SurveyStatus.EXPIRED
            else:
                survey.status = rng.choices(
                    [SurveyStatus.SENT, SurveyStatus.OPENED], weights=[70, 30]
                )[0]
                if survey.status is SurveyStatus.OPENED:
                    survey.opened_at = survey.sent_at + timedelta(
                        hours=rng.randint(1, 20)
                    )
            session.add(survey)
            new_surveys += 1

        await session.commit()
        topped.append(f"{agent.full_name}: {existing} → {existing + need}")

    if topped:
        print(f"  ✅ So'rovnomalar: +{new_surveys} ta, javoblar: +{new_responses} ta")
        for line in topped:
            print(f"       · {line}")
    else:
        print(
            f"  ℹ️  Barcha xodimda {MIN_RESPONSES_PER_AGENT}+ ta javob bor — "
            "yangisi qo'shilmadi"
        )


def _csat_mean(base_score: int) -> float:
    """AI bazaviy balini (62..89) client bahosiga (3.2..4.5) o'giradi.

    Tasodifiy baho dashboardni soxta ko'rsatadi va "AI bahosi ↔ client
    bahosi" solishtiruvini ma'nosiz qilib qo'yadi — shuning uchun bog'lanadi.
    """
    low, high = 62, 89
    ratio = (min(high, max(low, base_score)) - low) / (high - low)
    return 3.2 + ratio * 1.3


def _sentiment_of(csat: int) -> str:
    if csat >= 4:
        return "positive"
    return "neutral" if csat == 3 else "negative"


def _make_survey(
    agent: AgentModel,
    client: ClientModel,
    rng: random.Random,
    now: datetime,
    window_days: int,
    *,
    live: bool = False,
) -> SurveyModel:
    """Bitta so'rovnoma. `live=True` — tokeni hali amal qiladi."""
    if live:
        day_offset = rng.randint(1, SURVEY_TOKEN_TTL_DAYS - 2)
    else:
        day_offset = rng.randint(2, window_days - 5)

    sent_at = now - timedelta(days=day_offset, hours=rng.randint(0, 9))
    return SurveyModel(
        client_id=client.id,
        agent_id=agent.id,
        # Hudud nusxasi — demo ma'lumot ham haqiqiy oqim bilan bir xil
        # shaklda bo'lsin, aks holda hisobot demo'da boshqacha ishlardi
        region=agent.region,
        token=secrets.token_urlsafe(16),
        period_start=sent_at - timedelta(days=SURVEY_PERIOD_DAYS),
        period_end=sent_at,
        channel=SurveyChannel.TELEGRAM_GROUP,
        sent_at=sent_at,
        expires_at=sent_at + timedelta(days=SURVEY_TOKEN_TTL_DAYS),
        status=SurveyStatus.SENT,
    )


async def _pull_back_future_surveys(session: AsyncSession, now: datetime) -> int:
    """Eski seed kelajak sanali javoblar yaratardi — ularni orqaga suradi.

    Idempotent: bir marta tuzatilgach mos qator qolmaydi.
    """
    rows = (
        await session.execute(
            select(SurveyResponseModel, SurveyModel)
            .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
            .where(SurveyResponseModel.responded_at > now)
        )
    ).all()
    if not rows:
        return 0

    shift = timedelta(days=3)
    for response, survey in rows:
        response.responded_at -= shift
        survey.period_start -= shift
        survey.period_end -= shift
        survey.expires_at -= shift
        if survey.sent_at:
            survey.sent_at -= shift
        if survey.opened_at:
            survey.opened_at -= shift
        if survey.completed_at:
            survey.completed_at -= shift

    await session.commit()
    return len(rows)


async def reset_demo(session: AsyncSession) -> None:
    """Demo ma'lumotni tozalaydi (hisoblar va sozlamalar saqlanadi)."""
    for model in (SurveyResponseModel, SurveyModel, CallScoreModel, CallModel, ClientModel):
        await session.execute(delete(model))
    await session.commit()
    print("  🧹 Demo ma'lumot tozalandi (qo'ng'iroq, baho, client, so'rovnoma)")


def _clamp(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, value + random.gauss(0, 2))))


# ══════════════════════════════════════════════════════════════


async def main(reset: bool = False, agents_only: bool = False) -> None:
    async with SessionFactory() as session:
        await ensure_admin(session)

        if reset:
            await reset_demo(session)

        # ⚠️ Tekshiruv XODIM YARATISHDAN OLDIN. Ilgari keyin turardi va
        # bayroq `false` bo'lsa ham `AGENTS` ro'yxatidagi 15 xodim har
        # ishga tushishda qayta tiklanardi: bazadan o'chirilgan xodim
        # keyingi `docker compose up` da qaytib kelar, unga qo'ng'iroq
        # ham generatsiya qilinardi. Ya'ni bayroq o'z vazifasini
        # bajarmasdi — "demo ma'lumot" xodimning o'zidan boshlanadi.
        if not settings.SEED_DEMO_DATA:
            print("  ℹ️  SEED_DEMO_DATA=false — demo xodim va ma'lumot yaratilmadi")
            return

        agents = await ensure_agents(session)

        await ensure_accounts(session, agents)
        clients = await ensure_clients(session, agents)

        if agents_only:
            print("  ℹ️  --agents-only: qo'ng'iroq va so'rovnoma yaratilmadi")
            return

        await ensure_calls(session, agents, clients)
        await ensure_surveys(session, agents, clients)

        # Yakuniy hisobot
        counts = {
            "Savdo xodimlari": AgentModel,
            "Clientlar": ClientModel,
            "Qo'ng'iroqlar": CallModel,
            "Baholar": CallScoreModel,
            "So'rovnomalar": SurveyModel,
            "Javoblar": SurveyResponseModel,
        }
        print("\n  ── Bazadagi holat " + "─" * 26)
        for label, model in counts.items():
            total = (await session.execute(select(func.count(model.id)))).scalar_one()
            print(f"  {label:<18} {total:>7}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BonviZvonki — ma'lumot yuklash")
    parser.add_argument(
        "--reset", action="store_true", help="demo ma'lumotni tozalab qayta yaratish"
    )
    parser.add_argument(
        "--agents-only", action="store_true", help="faqat xodim va clientlarni qo'shish"
    )
    args = parser.parse_args()

    print("\n  Bonvi — ma'lumot yuklash\n  " + "─" * 40)
    asyncio.run(main(reset=args.reset, agents_only=args.agents_only))
