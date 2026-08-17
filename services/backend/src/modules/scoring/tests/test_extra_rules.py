"""Admin yozadigan qo'shimcha baholash qoidalari.

NEGA BU IMKONIYAT BOR. Rubrika bloklar va red flag'lar bilan
cheklangan: «mahsulotni belgilangan narxdan qimmatga sotish» yoki
«mijozni shaxsiy raqamga o'g'dirish» kabi kompaniyaga xos qoidalarni
faqat sarlavha va jarima bilan ifodalab bo'lmaydi — modelga NIMANI
qanday izlashni aytish kerak. Ilgari bu matn kodda qotib turardi, ya'ni
har o'zgarish uchun dasturchi kerak edi.

BU FAYL UCHTA NARSANI QULFLAYDI:

  1. matn promptga TUSHADI va kerakli joyda turadi (format shartnomasi
     undan KEYIN — aks holda bexosdan yozilgan bitta gap JSON ni buzib,
     butun baholashni to'xtatardi);
  2. bo'sh bo'lganda prompt AVVALGIDEK qoladi (bayt-barqarorlik —
     prompt caching shuni talab qiladi);
  3. `build_system_prompt` va `split_system_prompt` BIR XIL matnni
     beradi. Ular ajralib ketsa admin panelda bir narsa ko'rinardi, AI
     ga boshqasi ketardi — hech qanday belgisi bo'lmagan xato.
"""

import pytest
import pytest_asyncio

from src.core.database import SessionFactory
from src.core.exceptions import ValidationError
from src.modules.scoring.application.prompt import (
    MAX_EXTRA_RULES,
    build_schema,
    build_system_prompt,
    split_system_prompt,
)
from src.modules.scoring.application.rubric_service import RubricService
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

#: ⚠️ Bazaga yozadigan testlar TRANZAKSIYA ichida ishlaydi va oxirida
#: `rollback()` qiladi. Aks holda har yurish yangi rubrika versiyasini
#: yaratib, mijozning FAOL rubrikasini almashtirib qo'yardi — ya'ni test
#: ishlab turgan tizimni buzardi.
BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]

QOIDA = (
    "Xodim mijozni ish telefonidan o'z shaxsiy raqamiga o'tishga "
    "undasa — bu jiddiy qoidabuzarlik."
)


@pytest_asyncio.fixture
async def session():
    """Tranzaksiya — oxirida ROLLBACK.

    ⚠️ `commit()` QILINMAYDI. Rubrika saqlash mavjud faol versiyani
    o'chiradi va yangisini faol qiladi. Test commit qilsa, har yurish
    mijozning haqiqiy rubrikasini almashtirib qo'yardi — ya'ni test
    ishlab turgan tizimni buzardi.
    """
    async with SessionFactory() as s:
        try:
            yield s
        finally:
            await s.rollback()


# ══════════════════════════════════════════════════════════════
#  Promptga tushishi
# ══════════════════════════════════════════════════════════════


def test_qoida_promptga_tushadi() -> None:
    assert QOIDA in build_system_prompt(BLOCKS, FLAGS, QOIDA)


def test_bosh_qoida_promptni_ozgartirmaydi() -> None:
    """⚠️ BAYT-BARQARORLIK. Tizim prompti o'zgarmagan bo'lsa vendor uni
    keshdan oladi va rubrika tokenlari qayta to'lanmaydi. Bo'sh maydon
    promptga bo'sh sarlavha qo'shsa, kesh har safar buzilardi."""
    asosiy = build_system_prompt(BLOCKS, FLAGS)
    for bosh in (None, "", "   ", "\n\n"):
        assert build_system_prompt(BLOCKS, FLAGS, bosh) == asosiy


def test_format_qismi_qoidadan_KEYIN_turadi() -> None:
    """⚠️ ASOSIY XAVFSIZLIK SHARTI.

    LLM ziddiyatda odatda keyingi ko'rsatmaga amal qiladi. Admin matni
    oxirga qo'yilsa, bexosdan yozilgan «javobni tushuntirib ber» degan
    gap JSON ni buzib, har bir baho validatsiyadan o'tmasdi — ya'ni
    bitta tahrir butun tizimni to'xtatardi."""
    prompt = build_system_prompt(BLOCKS, FLAGS, QOIDA)
    assert prompt.index(QOIDA) < prompt.index("## BALL QO'YISH QOIDALARI")
    assert prompt.index(QOIDA) < prompt.index("## JAVOB SHAKLI")


def test_ustunlik_ochiq_aytiladi() -> None:
    """Matn joylashuvi yetmaydi — modelga ochiq aytilishi ham kerak."""
    prompt = build_system_prompt(BLOCKS, FLAGS, QOIDA)
    assert "PASTDAGISI ustun turadi" in prompt


# ══════════════════════════════════════════════════════════════
#  Bo'laklarga ajratish — admin panel shu bilan ishlaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("qoida", [None, QOIDA])
def test_bolaklar_yigindisi_toliq_promptga_teng(qoida) -> None:
    """⚠️ Admin panelda ko'ringan matn AI ga ketganidan farq qilmasligi
    kerak. Ikki funksiya alohida yozilsa, ular vaqt o'tib ajralib
    ketardi va buni hech narsa ko'rsatmasdi."""
    bolaklar = split_system_prompt(BLOCKS, FLAGS, qoida)
    assert "".join(b["text"] for b in bolaklar) == build_system_prompt(
        BLOCKS, FLAGS, qoida
    )


def test_faqat_bitta_bolak_tahrirlanadi() -> None:
    bolaklar = split_system_prompt(BLOCKS, FLAGS, QOIDA)
    tahrirlanadigan = [b["key"] for b in bolaklar if b["editable"]]
    assert tahrirlanadigan == ["extra_rules"]


def test_format_boligi_tahrirlanmaydi() -> None:
    """Buzilsa har bir baho validatsiyadan o'tmay qoladi."""
    bolaklar = {b["key"]: b for b in split_system_prompt(BLOCKS, FLAGS, QOIDA)}
    assert bolaklar["format"]["editable"] is False
    assert bolaklar["rules"]["editable"] is False
    assert "JAVOB SHAKLI" in bolaklar["format"]["text"]


# ══════════════════════════════════════════════════════════════
#  Uzunlik chegarasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_juda_uzun_qoida_rad_etiladi(session) -> None:
    """Chegara PULGA bog'liq: bu matn har bir qo'ng'iroqda yuboriladi."""
    with pytest.raises(ValidationError, match="juda uzun"):
        await RubricService(session).create_version(
            blocks=BLOCKS, red_flags=FLAGS, extra_rules="a" * (MAX_EXTRA_RULES + 1)
        )


@pytest.mark.asyncio
async def test_chegaradagi_uzunlik_qabul_qilinadi(session) -> None:
    row = await RubricService(session).create_version(
        blocks=BLOCKS, red_flags=FLAGS, extra_rules="a" * MAX_EXTRA_RULES
    )
    assert row.extra_rules is not None
    assert len(row.extra_rules) == MAX_EXTRA_RULES


@pytest.mark.asyncio
async def test_bosh_satr_null_ga_aylanadi(session) -> None:
    """Bo'sh satr va `NULL` bir xil ma'noda — ikkisini ajratish promptda
    bo'sh sarlavha qoldirardi."""
    row = await RubricService(session).create_version(
        blocks=BLOCKS, red_flags=FLAGS, extra_rules="   \n  "
    )
    assert row.extra_rules is None


# ══════════════════════════════════════════════════════════════
#  Admin qo'shgan YANGI red flag
# ══════════════════════════════════════════════════════════════

YANGI = {
    "type": "shaxsiy_raqamga_ogdirish",
    "label": "Mijozni shaxsiy raqamga o'g'dirish",
    "penalty": -40,
    "zeroes_score": False,
    "description": "Ish telefonidan shaxsiy raqamga o'tishga undash",
}


def test_yangi_red_flag_promptga_va_sxemaga_tushadi() -> None:
    """⚠️ IKKI JOY BIR VAQTDA. Promptda ruxsat etilgan kalitlar sanaladi,
    JSON sxemasida esa `enum` bor. Biri yangilanib ikkinchisi qolsa,
    model kalitni qaytara olmaydi (sxema to'sadi) yoki qaytargani rad
    etiladi (prompt to'sadi) — ikki holatda ham yangi qoida JIMGINA
    ishlamaydi."""
    flags = [*FLAGS, YANGI]
    prompt = build_system_prompt(BLOCKS, flags)
    assert f"`{YANGI['type']}`" in prompt

    # Ruxsat etilgan kalitlar qatorida ham bo'lishi shart
    qoidalar = prompt[prompt.index("kalitlardan biri bo'lishi mumkin") :]
    assert YANGI["type"] in qoidalar[:400]

    # Sxemadagi `enum` da ham
    matn = str(build_schema(BLOCKS, flags))
    assert YANGI["type"] in matn


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kalit", ["Shaxsiy Raqam!", "", "  ", "shaxsiy raqam", "ШАХСИЙ", "A_B", "x", "1abc"]
)
async def test_notogri_kalit_rad_etiladi(session, kalit) -> None:
    """Kalit promptga va sxemaga tushadi. Bo'sh joy yoki kirill harf
    bo'lsa model uni takrorlay olmaydi va BUTUN javob rad etiladi."""
    with pytest.raises(ValidationError, match="red flag kaliti"):
        await RubricService(session).create_version(
            blocks=BLOCKS,
            red_flags=[*FLAGS, {**YANGI, "type": kalit}],
        )


@pytest.mark.asyncio
async def test_takroriy_kalit_rad_etiladi(session) -> None:
    """Bir xil kalit ikki marta bo'lsa jarima ikki xil bo'lib qolardi."""
    with pytest.raises(ValidationError, match="takrorlangan"):
        await RubricService(session).create_version(
            blocks=BLOCKS, red_flags=[*FLAGS, FLAGS[0]]
        )


@pytest.mark.asyncio
async def test_togri_kalit_qabul_qilinadi(session) -> None:
    row = await RubricService(session).create_version(
        blocks=BLOCKS, red_flags=[*FLAGS, YANGI]
    )
    assert any(f["type"] == YANGI["type"] for f in row.red_flags)


# ══════════════════════════════════════════════════════════════
#  Versiyalanish
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qoida_versiya_bilan_birga_qaytadi(session) -> None:
    """⚠️ NEGA MATN RUBRIKA ICHIDA, SOZLAMADA EMAS.

    Sozlamada bo'lsa versiyalanmasdi: eski baholar qanday ko'rsatma
    bilan qo'yilganini bilib bo'lmasdi va noto'g'ri tahrirni qaytarish
    yo'li ham bo'lmasdi. Rubrika ichida «Eski versiyaga qaytish» matnni
    ham qaytaradi."""
    service = RubricService(session)
    birinchi = await service.create_version(
        blocks=BLOCKS, red_flags=FLAGS, extra_rules="Birinchi qoida."
    )
    ikkinchi = await service.create_version(
        blocks=BLOCKS, red_flags=FLAGS, extra_rules="Ikkinchi qoida."
    )
    assert ikkinchi.version > birinchi.version

    qaytgan = await service.activate(birinchi.version)
    assert qaytgan.extra_rules == "Birinchi qoida."
