"""Guruh statistikasi va daraxt — sonlar aynan to'g'ri chiqishi kerak.

Bu yerdagi hamma test COMMIT QILINMAYDIGAN sessiyada ishlaydi
(`conftest.rollback_session`), shuning uchun dev bazasida iz qolmaydi.

Ishga tushirish:
    docker exec zvonki-backend python -m pytest src/modules/groups -q
"""

import pytest

from src.modules.groups.application.services import GroupService
from src.modules.groups.tests.conftest import (
    MARK,
    build_agent,
    build_group,
    build_response,
    build_survey,
)

# ══════════════════════════════════════════════════════════════
#  survey_count / response_count
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sorovnoma_va_javob_sonlari_join_dublikatisiz(rollback_session):
    """Bitta guruhda 3 so'rovnoma va 5 javob.

    ⚠️ Bu testning butun mazmuni JOIN dublikatida. Agar so'rovnomalar
    javoblar bilan bitta JOIN da sanalsa, `survey_count` 5 bo'lib
    chiqardi: har javob so'rovnoma qatorini takrorlaydi. Sonlar
    ataylab har xil (3 va 5), teng bo'lsa xato ko'rinmay qolardi.
    """
    session = rollback_session
    agent = build_agent()
    session.add(agent)
    await session.flush()

    group = build_group(agent_id=agent.id, region=f"{MARK}-hudud")
    session.add(group)
    await session.flush()

    uchta_javobli = build_survey(agent_id=agent.id, group_id=group.id)
    ikkita_javobli = build_survey(agent_id=agent.id, group_id=group.id)
    javobsiz = build_survey(agent_id=agent.id, group_id=group.id)
    session.add_all([uchta_javobli, ikkita_javobli, javobsiz])
    await session.flush()

    for _ in range(3):
        session.add(build_response(survey_id=uchta_javobli.id))
    for _ in range(2):
        session.add(build_response(survey_id=ikkita_javobli.id))
    await session.flush()

    service = GroupService(session)

    bitta = await service.get_one(group.id)
    assert bitta["survey_count"] == 3
    assert bitta["response_count"] == 5

    # Ro'yxat sahifasi ham AYNAN shu sonlarni beradi — u boshqa
    # so'rovlardan foydalanadi, ikkalasi ham tekshirilishi kerak
    sahifa = await service.list_groups(agent_id=agent.id, page_size=200)
    qator = next(item for item in sahifa["items"] if item["id"] == group.id)
    assert qator["survey_count"] == 3
    assert qator["response_count"] == 5


@pytest.mark.asyncio
async def test_sorovnomasiz_guruhda_sonlar_nol(rollback_session):
    """Statistikasi yo'q guruh `null` emas, `0` beradi."""
    session = rollback_session
    agent = build_agent()
    session.add(agent)
    await session.flush()
    group = build_group(agent_id=agent.id, region=f"{MARK}-hudud")
    session.add(group)
    await session.flush()

    bitta = await GroupService(session).get_one(group.id)
    assert bitta["survey_count"] == 0
    assert bitta["response_count"] == 0


# ══════════════════════════════════════════════════════════════
#  GET /groups/tree
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_daraxt_xodim_hudud_va_sanoqlarni_togri_yigadi(rollback_session):
    """Xodim → hudud → sanoqlar.

    Tekshiriladigan qoidalar:
      · bir hududdagi bir nechta guruh bitta tugunga yig'iladi
      · hududsiz guruh ALOHIDA tugun (`region: null`) va u ENG OXIRIDA
      · javoblar hudud bo'yicha to'g'ri taqsimlanadi
      · faolsiz guruh umuman hisoblanmaydi
    """
    session = rollback_session
    service = GroupService(session)

    agent = build_agent()
    session.add(agent)
    await session.flush()

    # Nomlar ataylab shunday: alifboda "a" < "b", ya'ni tartib kutilgan
    birinchi_hudud = f"{MARK}-a-hudud"
    ikkinchi_hudud = f"{MARK}-b-hudud"

    ikkitadan_1 = build_group(agent_id=agent.id, region=birinchi_hudud)
    ikkitadan_2 = build_group(agent_id=agent.id, region=birinchi_hudud)
    bittalik = build_group(agent_id=agent.id, region=ikkinchi_hudud)
    hududsiz = build_group(agent_id=agent.id, region=None)
    faolsiz = build_group(
        agent_id=agent.id, region=birinchi_hudud, is_active=False
    )
    session.add_all([ikkitadan_1, ikkitadan_2, bittalik, hududsiz, faolsiz])
    await session.flush()

    birinchi_sorovnoma = build_survey(agent_id=agent.id, group_id=ikkitadan_1.id)
    ikkinchi_sorovnoma = build_survey(agent_id=agent.id, group_id=bittalik.id)
    session.add_all([birinchi_sorovnoma, ikkinchi_sorovnoma])
    await session.flush()
    for _ in range(3):
        session.add(build_response(survey_id=birinchi_sorovnoma.id))
    session.add(build_response(survey_id=ikkinchi_sorovnoma.id))
    await session.flush()

    tree = await service.tree()
    tugun = next(row for row in tree["agents"] if row["agent_id"] == agent.id)

    assert tugun["full_name"] == agent.full_name
    assert tugun["group_count"] == 4  # faolsizi hisoblanmaydi
    assert tugun["regions"] == [
        {"region": birinchi_hudud, "group_count": 2, "response_count": 3},
        {"region": ikkinchi_hudud, "group_count": 1, "response_count": 1},
        # Hududsiz tugun ENG OXIRIDA: u «bajarilishi kerak» ro'yxati,
        # haqiqiy hududlarni pastga surib yubormasligi kerak
        {"region": None, "group_count": 1, "response_count": 0},
    ]


@pytest.mark.asyncio
async def test_xodimi_yoq_guruh_unassigned_da(rollback_session):
    """Xodimi aniqlanmagan guruh — alohida to'plamda, xodimlarda emas."""
    session = rollback_session
    service = GroupService(session)

    boshlangich = (await service.tree())["unassigned"]["group_count"]

    session.add_all(
        [
            build_group(agent_id=None, region=None),
            build_group(agent_id=None, region=f"{MARK}-hudud"),
            # Faolsizi sanalmaydi
            build_group(agent_id=None, region=None, is_active=False),
        ]
    )
    await session.flush()

    tree = await service.tree()
    assert tree["unassigned"]["group_count"] == boshlangich + 2


@pytest.mark.asyncio
async def test_faolsiz_xodim_daraxtda_korinmaydi(rollback_session):
    """Ishdan ketgan xodim daraxtni to'ldirib turmasin."""
    session = rollback_session
    agent = build_agent(is_active=False)
    session.add(agent)
    await session.flush()
    session.add(build_group(agent_id=agent.id, region=f"{MARK}-hudud"))
    await session.flush()

    tree = await GroupService(session).tree()
    assert agent.id not in [row["agent_id"] for row in tree["agents"]]
