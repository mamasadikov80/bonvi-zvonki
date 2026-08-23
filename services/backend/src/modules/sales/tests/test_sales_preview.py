"""Import oldidagi hisob-kitob — `POST /sales/import/preview`.

ENG MUHIM TEKSHIRUV BITTA: preview BAZAGA HECH NARSA YOZMAYDI.
Qolgan hamma narsa (turlar, kunlar, ogohlantirishlar) foydali, lekin
ular xato bo'lsa foydalanuvchi buni ko'radi. Yozib yuborish esa
JIMGINA bo'ladi va aynan shuning uchun bu bo'lim yozilgan.

Shuning uchun `test_preview_bazaga_yozmaydi` uch jadvalning ham
qatorlarini oldin va keyin sanaydi — `sales`, `sale_partners` va
`sale_branches`. Uchinchisi ataylab: import filialni topolmasa ham
uni jadvalga QO'SHADI (`_resolve_branches`), preview esa qo'shmasligi
kerak.

Testlar HAQIQIY dev bazasida ishlaydi — har biri `pytest-` prefiksli
noyob kalitlardan foydalanadi va o'zidan keyin tozalaydi.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from src.core.database import SessionFactory
from src.modules.sales.application.importer import import_catalog, import_register
from src.modules.sales.application.preview import build_preview
from src.modules.sales.application.reader import SalesFileError
from src.modules.sales.infrastructure.models import (
    SaleBranchModel,
    SaleModel,
    SalePartnerModel,
)
from src.modules.sales.tests.test_sales_import import (
    BALANCE_HEADER,
    CATALOG_HEADER,
    MARK,
    REGISTER_HEADER,
    _register_row,
    _uniq,
    _xlsx,
)


@pytest_asyncio.fixture
async def cleanup() -> AsyncIterator[Callable[..., None]]:
    """`pytest-` bilan boshlanadigan hamma narsani oxirida o'chiradi."""
    branches: set[str] = set()

    def _track(branch: str) -> None:
        branches.add(branch)

    yield _track

    async with SessionFactory() as session:
        await session.execute(
            delete(SaleModel).where(SaleModel.external_id.like(f"{MARK}%"))
        )
        await session.execute(
            delete(SalePartnerModel).where(SalePartnerModel.code.like(f"{MARK}%"))
        )
        if branches:
            await session.execute(
                delete(SaleBranchModel).where(SaleBranchModel.branch.in_(branches))
            )
        await session.commit()


async def _counts() -> list[int]:
    """Uch jadvaldagi qatorlar soni — «yozilmadi» ni shu bilan o'lchaymiz."""
    async with SessionFactory() as session:
        return [
            (
                await session.execute(select(func.count()).select_from(model))
            ).scalar_one()
            for model in (SaleModel, SalePartnerModel, SaleBranchModel)
        ]


def _catalog_row(code: str, *, phone: str | None, branch: str) -> list[Any]:
    return (
        ["Тест мижоз", code, "0", "Клиенты", phone, branch]
        + [None] * 4
        + ["Да", "Нет", None, None, None, None]
    )


# ══════════════════════════════════════════════════════════════
#  ⚠️ ASOSIY SHART: hech narsa yozilmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_preview_bazaga_yozmaydi(cleanup: Callable[..., None]) -> None:
    """Preview dan oldin va keyin qatorlar soni BIR XIL.

    ⚠️ Filial ATAYLAB yangi: import uni `sale_branches` ga qo'shardi,
    preview esa qo'shmasligi kerak. Aks holda foydalanuvchi bekor
    qilsa ham bazada iz qolardi.
    """
    branch = f"{MARK}Ховос-{_uniq()}"
    cleanup(branch)

    book = _xlsx(
        REGISTER_HEADER,
        [
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=f"{MARK}{_uniq()}",
                branch=branch,
            )
        ],
    )

    before = await _counts()
    async with SessionFactory() as session:
        preview = await build_preview(session, book, filename="savdo kunlik.xlsx")
    after = await _counts()

    assert before == after
    # Hisob-kitobning o'zi ishlagan bo'lishi kerak — bo'sh javob
    # «yozmadim» degan shartni arzon yo'l bilan bajarardi
    assert preview.rows == 1
    assert preview.new_rows == 1
    assert branch in preview.unmatched_branches

    async with SessionFactory() as session:
        yozildimi = (
            await session.execute(
                select(func.count())
                .select_from(SaleBranchModel)
                .where(SaleBranchModel.branch == branch)
            )
        ).scalar_one()
    assert yozildimi == 0


# ══════════════════════════════════════════════════════════════
#  Registr hisob-kitobi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_registr_hisob_kitobi(cleanup: Callable[..., None]) -> None:
    """Turlar, kunlar, davr va telefonsiz qatorlar."""
    branch = f"{MARK}Хива-{_uniq()}"
    cleanup(branch)
    telefonli = f"{MARK}{_uniq()}"
    telefonsiz = f"{MARK}{_uniq()}"

    async with SessionFactory() as session:
        await import_catalog(
            session,
            _xlsx(
                CATALOG_HEADER,
                [_catalog_row(telefonli, phone="(+99890) 2913923", branch=branch)],
            ),
            filename="wb3.xlsx",
        )

    book = _xlsx(
        REGISTER_HEADER,
        [
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=telefonli,
                branch=branch,
                credit_usd="1 000,000",
                occurred="10.08.2026",
            ),
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=telefonli,
                branch=branch,
                credit_usd="500,000",
                occurred="10.08.2026",
            ),
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=telefonsiz,
                branch=branch,
                op_type="Входящие платежи",
                credit_usd="250,000",
                occurred="12.08.2026",
            ),
        ],
    )

    async with SessionFactory() as session:
        preview = await build_preview(session, book, filename="savdo kunlik.xlsx")

    assert preview.kind == "register"
    assert preview.rows == 3
    assert (str(preview.date_from), str(preview.date_to)) == ("2026-08-10", "2026-08-12")

    turlar = {row.type: row for row in preview.by_type}
    # ⚠️ `"500,000"` matn, ya'ni 500 $ — Excel raqamga aylantirgan
    # katak esa 1000 barobar kichrayadi (`parse_amount` izohi)
    assert (turlar["sale"].count, turlar["sale"].amount_usd) == (2, 1500.0)
    assert turlar["sale"].label == "Продажа"
    assert turlar["payment_in"].count == 1
    # Ko'pi birinchi — ekranda «Продажа» yuqorida tursin
    assert preview.by_type[0].type == "sale"

    kunlar = {str(row.day): row.count for row in preview.by_day}
    assert kunlar == {"2026-08-10": 2, "2026-08-12": 1}

    # Kodi katalogda yo'q — bitta qator nazoratdan tashqarida
    assert preview.unknown_partners == [telefonsiz]
    assert preview.unknown_partner_count == 1
    assert preview.without_phone == 1
    assert branch in preview.unmatched_branches


@pytest.mark.asyncio
async def test_takroriy_fayl_yangi_qator_bermaydi(
    cleanup: Callable[..., None],
) -> None:
    """Import qilingan fayl qayta yuklansa — `new_rows=0`.

    Foydalanuvchi ekranda aynan shuni ko'rishi kerak: «bu fayl
    allaqachon yuklangan». Ilgari buni bilish uchun importni
    BAJARISH kerak edi.
    """
    branch = f"{MARK}Термиз-{_uniq()}"
    cleanup(branch)
    code = f"{MARK}{_uniq()}"
    ops = [f"{MARK}{_uniq()}" for _ in range(3)]

    def _book() -> Any:
        return _xlsx(
            REGISTER_HEADER,
            [
                _register_row(op_number=op, partner_code=code, branch=branch)
                for op in ops
            ],
        )

    async with SessionFactory() as session:
        oldin = await build_preview(session, _book(), filename="savdo.xlsx")
    assert (oldin.new_rows, oldin.existing_rows) == (3, 0)

    async with SessionFactory() as session:
        await import_register(session, _book(), filename="savdo.xlsx")

    async with SessionFactory() as session:
        keyin = await build_preview(session, _book(), filename="savdo.xlsx")

    assert (keyin.new_rows, keyin.existing_rows) == (0, 3)
    assert keyin.rows == 3


@pytest.mark.asyncio
async def test_nuqsonli_qatorlar_ogohlantirishga_tushadi(
    cleanup: Callable[..., None],
) -> None:
    """Sanasiz qator, takroriy raqam va tanilmagan tur — hammasi aytiladi."""
    branch = f"{MARK}Гулистон-{_uniq()}"
    cleanup(branch)
    code = f"{MARK}{_uniq()}"
    takror = f"{MARK}{_uniq()}"

    book = _xlsx(
        REGISTER_HEADER,
        [
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=code,
                branch=branch,
                occurred="",
            ),
            _register_row(
                op_number=f"{MARK}{_uniq()}",
                partner_code=code,
                branch=branch,
                op_type="Янги тур",
            ),
            _register_row(op_number=takror, partner_code=code, branch=branch),
            _register_row(op_number=takror, partner_code=code, branch=branch),
        ],
    )

    async with SessionFactory() as session:
        preview = await build_preview(session, book, filename="savdo.xlsx")

    assert preview.rows == 4
    # 4 qator, lekin noyob raqam 3 ta
    assert preview.new_rows + preview.existing_rows == 3

    matn = " | ".join(preview.warnings)
    assert "sana o'qilmadi" in matn
    assert "takrorlangan" in matn
    assert "tanilmadi" in matn


# ══════════════════════════════════════════════════════════════
#  Katalog va balans
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_katalog_uchun_ham_ishlaydi(cleanup: Callable[..., None]) -> None:
    """Katalogda sana yo'q — `by_day` bo'sh, kesim GURUH bo'yicha."""
    branch = f"{MARK}Бухоро-{_uniq()}"
    cleanup(branch)
    bor = f"{MARK}{_uniq()}"
    yangi = f"{MARK}{_uniq()}"

    async with SessionFactory() as session:
        await import_catalog(
            session,
            _xlsx(
                CATALOG_HEADER,
                [_catalog_row(bor, phone="(+99890) 2913923", branch=branch)],
            ),
            filename="wb3.xlsx",
        )

    before = await _counts()
    async with SessionFactory() as session:
        preview = await build_preview(
            session,
            _xlsx(
                CATALOG_HEADER,
                [
                    _catalog_row(bor, phone="(+99890) 2913923", branch=branch),
                    # Telefoni yo'q — nazoratga kirmaydi
                    _catalog_row(yangi, phone=None, branch=branch),
                ],
            ),
            filename="Workbook3.xlsx",
        )
    after = await _counts()

    assert before == after
    assert preview.kind == "catalog"
    assert preview.rows == 2
    assert (preview.new_rows, preview.existing_rows) == (1, 1)
    assert preview.date_from is None and preview.by_day == []
    assert preview.without_phone == 1
    assert [(row.type, row.count) for row in preview.by_type] == [("Клиенты", 2)]


@pytest.mark.asyncio
async def test_balans_kod_boyicha_hisoblanadi(cleanup: Callable[..., None]) -> None:
    """Balans faylidan kontragent yaratilmaydi — bu aytib qo'yiladi."""
    branch = f"{MARK}Денов-{_uniq()}"
    cleanup(branch)
    bor = f"{MARK}{_uniq()}"
    yoq = f"{MARK}{_uniq()}"

    async with SessionFactory() as session:
        await import_catalog(
            session,
            _xlsx(CATALOG_HEADER, [_catalog_row(bor, phone=None, branch=branch)]),
            filename="wb3.xlsx",
        )

    async with SessionFactory() as session:
        preview = await build_preview(
            session,
            _xlsx(
                BALANCE_HEADER,
                [
                    [1, branch, "ВЕЛО", bor, "Bor", "(+99893) 4773322"] + ["0,000"] * 9,
                    [2, branch, "ВЕЛО", yoq, "Yo'q", "(+99893) 4773323"] + ["0,000"] * 9,
                ],
            ),
            filename="Workbook1.xlsx",
        )

    assert preview.kind == "balance"
    assert (preview.new_rows, preview.existing_rows) == (1, 1)
    assert preview.unknown_partners == [yoq]
    assert any("katalogda yo'q" in text for text in preview.warnings)


# ══════════════════════════════════════════════════════════════
#  HTTP qatlami
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_notogri_fayl_422(admin_client: httpx.AsyncClient) -> None:
    """Tanilmagan fayl hisob-kitob bosqichida rad etiladi.

    ⚠️ Aynan SHU YERDA to'xtatish muhim: aks holda noto'g'ri fayl
    tasdiqlash tugmasigacha yetib borardi.
    """
    response = await admin_client.post(
        "/api/v1/sales/import/preview",
        files={
            "file": (
                "xodimlar.xlsx",
                _xlsx(["Ism", "Familiya"], [["A", "B"]]).getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 422
    assert "tanilmadi" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_faqat_xlsx_qabul_qilinadi(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/v1/sales/import/preview",
        files={"file": ("savdo.csv", b"a;b\n1;2\n", "text/csv")},
    )
    assert response.status_code == 422
    assert ".xlsx" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_http_javob_shakli(
    admin_client: httpx.AsyncClient, cleanup: Callable[..., None]
) -> None:
    """Frontend tayanadigan maydonlar — hammasi joyida va baza tegilmagan."""
    branch = f"{MARK}Наманган-{_uniq()}"
    cleanup(branch)

    before = await _counts()
    response = await admin_client.post(
        "/api/v1/sales/import/preview",
        files={
            "file": (
                "savdo kunlik.xlsx",
                _xlsx(
                    REGISTER_HEADER,
                    [
                        _register_row(
                            op_number=f"{MARK}{_uniq()}",
                            partner_code=f"{MARK}{_uniq()}",
                            branch=branch,
                        )
                    ],
                ).getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    after = await _counts()

    assert response.status_code == 200
    assert before == after

    body = response.json()
    assert set(body) == {
        "kind",
        "filename",
        "rows",
        "date_from",
        "date_to",
        "by_type",
        "by_day",
        "new_rows",
        "existing_rows",
        "unknown_partners",
        "unknown_partner_count",
        "unmatched_branches",
        "without_phone",
        "warnings",
    }
    assert body["kind"] == "register"
    assert body["filename"] == "savdo kunlik.xlsx"
    assert body["new_rows"] == 1
    assert body["by_day"] == [
        {"day": "2026-08-10", "count": 1, "amount_usd": 1950.0}
    ]


@pytest.mark.asyncio
async def test_ruxsatsiz_kirish_yopiq(anon_client: httpx.AsyncClient) -> None:
    """`sales:import` yo'q — hisob-kitob ham ko'rinmaydi.

    Hisob-kitob fayl ichidagi mijoz kodlarini va summalarni ochadi,
    ya'ni u importning «zararsiz» ko'rinishi EMAS.
    """
    response = await anon_client.post(
        "/api/v1/sales/import/preview",
        files={"file": ("savdo.xlsx", b"x", "application/octet-stream")},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_bosh_fayl_rad_etiladi() -> None:
    """Bo'sh baytlar `openpyxl` ga umuman berilmaydi."""
    async with SessionFactory() as session:
        with pytest.raises(SalesFileError):
            await build_preview(session, b"", filename="savdo.xlsx")
