"""RUXSATLAR MATRITSASI — sof unit test, bazasiz.

`ROLE_PERMISSIONS` — butun tizimning xavfsizlik chegarasi. Router'lar,
frontend menyusi va servis qatlamidagi filtrlar hammasi shu lug'atdan
kelib chiqadi.

Shuning uchun bu yerda kutilgan to'plam HARFMA-HARF yozilgan va
taqqoslash AYNIYAT (`==`) bo'yicha, «ichida bormi» bo'yicha emas.
Refaktoring paytida tasodifan qo'shilib qolgan bitta ruxsat ham
(masalan menejerga `users:write`) shu yerda darhol ushlanadi.

Test kodni takrorlamasligi uchun hech qanday qiymat `entities.py` dan
hisoblab olinmagan — hammasi qo'lda yozilgan.
"""

from __future__ import annotations

import pytest

from src.modules.users.domain.entities import (
    ROLE_PERMISSIONS,
    SALES_RATING_FULL,
    SALES_RATING_HIDDEN,
    SALES_RATING_SCORE_ONLY,
    Role,
    User,
    has_permission,
    resolve_permissions,
)

# ══════════════════════════════════════════════════════════════
#  Kutilgan matritsa — YAGONA HAQIQAT MANBAI
# ══════════════════════════════════════════════════════════════

KUTILGAN: dict[Role, set[str]] = {
    Role.ADMIN: {
        "users:read", "users:write",
        "agents:read", "agents:write", "agents:sync",
        "clients:read", "clients:write",
        "calls:read",
        "groups:read", "groups:write",
        "regions:read", "regions:write",
        "scores:read", "scores:write",
        "surveys:read", "surveys:write",
        "analytics:read", "analytics:read_all",
        "rubric:read", "rubric:write",
        "settings:read", "settings:write",
        # «Savdo nazorati» — xodim ustidan tekshiruv, shuning uchun
        # faqat ADMIN va MANAGER da (`docs/savdo-nazorati.md`, 7.1)
        "sales:read", "sales:review", "sales:import",
    },
    Role.MANAGER: {
        "agents:read",
        "clients:read",
        "calls:read",
        "groups:read",
        "regions:read",
        "scores:read", "scores:write",
        "surveys:read",
        "analytics:read", "analytics:read_all",
        "rubric:read",
        "settings:read",
        "sales:read", "sales:review", "sales:import",
    },
    Role.SALES: {
        "calls:read:own",
        "scores:read:own",
        "analytics:read:own",
        "regions:read",
    },
    Role.VIEWER: {
        "analytics:read",
        "regions:read",
    },
}


# ══════════════════════════════════════════════════════════════
#  Rollar ro'yxati
# ══════════════════════════════════════════════════════════════


def test_tizimda_aynan_tortta_rol_bor() -> None:
    """Yangi rol qo'shilsa — bu test yiqiladi va matritsani yangilashga majbur qiladi."""
    assert {r.value for r in Role} == {"admin", "manager", "sales", "viewer"}


def test_har_bir_rolning_ozbekcha_nomi_bor() -> None:
    assert Role.ADMIN.label_uz == "Administrator"
    assert Role.MANAGER.label_uz == "Menejer"
    assert Role.SALES.label_uz == "Savdo xodimi"
    assert Role.VIEWER.label_uz == "Kuzatuvchi"


def test_matritsada_har_bir_rol_uchun_yozuv_bor() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)


# ══════════════════════════════════════════════════════════════
#  Har bir rolning ANIQ to'plami
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", list(Role), ids=lambda r: r.value)
def test_rolning_bazaviy_ruxsatlari_aynan_kutilganday(role: Role) -> None:
    haqiqiy = ROLE_PERMISSIONS[role]
    kutilgan = KUTILGAN[role]

    ortiqcha = haqiqiy - kutilgan
    yetishmayotgan = kutilgan - haqiqiy

    assert not ortiqcha, f"{role.value}: ortiqcha ruxsat berilgan → {sorted(ortiqcha)}"
    assert not yetishmayotgan, (
        f"{role.value}: ruxsat yo'qolgan → {sorted(yetishmayotgan)}"
    )


# ══════════════════════════════════════════════════════════════
#  Chegaralar — nima UMUMAN bo'lmasligi kerak
# ══════════════════════════════════════════════════════════════


def test_hisoblarni_faqat_admin_boshqaradi() -> None:
    """`users:*` — hech qachon boshqa rolga o'tmasin."""
    for role in Role:
        if role is Role.ADMIN:
            continue
        users_ruxsatlari = {p for p in ROLE_PERMISSIONS[role] if p.startswith("users:")}
        assert users_ruxsatlari == set(), f"{role.value} da {users_ruxsatlari}"


def test_sozlamalarni_faqat_admin_yozadi() -> None:
    for role in Role:
        assert has_permission(role, "settings:write") is (role is Role.ADMIN)


def test_rubrikani_faqat_admin_ozgartiradi() -> None:
    """Rubrika — baholash qoidasi. O'zgarsa barcha ballar ma'nosi o'zgaradi."""
    for role in Role:
        assert has_permission(role, "rubric:write") is (role is Role.ADMIN)


def test_savdo_xodimi_faqat_oz_malumotini_koradi() -> None:
    """SALES dagi har bir «ma'lumot» ruxsati `:own` bilan tugaydi.

    Yagona istisno — `regions:read`: hudud NOMLARI maxfiy emas, ular
    formadagi tanlov ro'yxati uchun kerak.
    """
    ochiq = {"regions:read"}
    for ruxsat in ROLE_PERMISSIONS[Role.SALES] - ochiq:
        assert ruxsat.endswith(":own"), f"{ruxsat} — savdo xodimida `:own` bo'lishi kerak"


def test_savdo_xodimi_va_kuzatuvchi_hech_narsa_yozmaydi() -> None:
    for role in (Role.SALES, Role.VIEWER):
        yozuvchilar = {p for p in ROLE_PERMISSIONS[role] if ":write" in p or ":sync" in p}
        assert yozuvchilar == set(), f"{role.value} da {yozuvchilar}"


def test_barcha_malumotni_faqat_admin_va_manager_koradi() -> None:
    for role in Role:
        kutilgan = role in (Role.ADMIN, Role.MANAGER)
        assert has_permission(role, "analytics:read_all") is kutilgan


def test_kuzatuvchi_qongiroq_va_ballarni_kormaydi() -> None:
    """VIEWER — savdo xonasidagi monitor. Faqat umumiy ko'rsatkich."""
    assert not has_permission(Role.VIEWER, "calls:read")
    assert not has_permission(Role.VIEWER, "scores:read")
    assert not has_permission(Role.VIEWER, "clients:read")
    assert not has_permission(Role.VIEWER, "analytics:read_all")


def test_has_permission_nomalum_ruxsat_va_rol_uchun_false() -> None:
    assert has_permission(Role.ADMIN, "yulduzlarni:ochirish") is False
    assert has_permission(Role.SALES, "calls:read") is False, (
        "`calls:read` va `calls:read:own` — bu ikki xil ruxsat"
    )


def test_ruxsat_nomlari_qat_iy_formatda() -> None:
    """`resurs:harakat[:doira]` — frontend shu shaklga tayanadi."""
    for role, ruxsatlar in ROLE_PERMISSIONS.items():
        for ruxsat in ruxsatlar:
            bolaklar = ruxsat.split(":")
            assert 2 <= len(bolaklar) <= 3, f"{role.value}: {ruxsat}"
            assert all(b and b == b.lower() for b in bolaklar), f"{role.value}: {ruxsat}"


# ══════════════════════════════════════════════════════════════
#  `User` domen obyektining qulayliklari
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("role", "boshqaradi", "hammasini_koradi"),
    [
        (Role.ADMIN, True, True),
        (Role.MANAGER, False, True),
        (Role.SALES, False, False),
        (Role.VIEWER, False, False),
    ],
    ids=lambda v: str(v),
)
def test_user_xossalari(role: Role, boshqaradi: bool, hammasini_koradi: bool) -> None:
    from uuid import uuid4

    user = User(
        id=uuid4(),
        email="a@b.uz",
        full_name="Test",
        role=role,
        is_active=True,
    )
    assert user.can_manage_users is boshqaradi
    assert user.sees_all_agents is hammasini_koradi


# ══════════════════════════════════════════════════════════════
#  DINAMIK RUXSATLAR — `resolve_permissions()`
# ══════════════════════════════════════════════════════════════


def test_resolve_bosh_sozlama_bilan_bazaviy_toplamni_qaytaradi() -> None:
    """Sozlama umuman berilmasa ham ish to'xtamaydi.

    SALES uchun standart `score_only` — shuning uchun `surveys:read:own`
    baribir qo'shiladi.
    """
    assert resolve_permissions(Role.ADMIN, {}) == KUTILGAN[Role.ADMIN]
    assert resolve_permissions(Role.MANAGER, {}) == KUTILGAN[Role.MANAGER]
    assert resolve_permissions(Role.VIEWER, {}) == KUTILGAN[Role.VIEWER]
    assert resolve_permissions(Role.SALES, {}) == KUTILGAN[Role.SALES] | {
        "surveys:read:own"
    }


@pytest.mark.parametrize(
    ("rating", "qoshimcha"),
    [
        (SALES_RATING_HIDDEN, set()),
        (SALES_RATING_SCORE_ONLY, {"surveys:read:own"}),
        (SALES_RATING_FULL, {"surveys:read:own", "surveys:read:own:comments"}),
    ],
    ids=["hidden", "score_only", "full"],
)
def test_sales_client_bahosi_sozlamasi(rating: str, qoshimcha: set[str]) -> None:
    natija = resolve_permissions(
        Role.SALES, {"access.sales_client_rating": rating}
    )
    assert natija == KUTILGAN[Role.SALES] | qoshimcha


def test_sales_notogri_qiymatda_hech_narsa_qoshilmaydi() -> None:
    """Sozlamaga qo'lda axlat yozilsa — ruxsat BERILMAYDI (fail-closed)."""
    natija = resolve_permissions(
        Role.SALES, {"access.sales_client_rating": "hammasi-ochiq"}
    )
    assert natija == KUTILGAN[Role.SALES]


@pytest.mark.parametrize("bayroq", [True, False], ids=["yoqilgan", "ochirilgan"])
def test_manager_xodim_boshqarish_bayrogi(bayroq: bool) -> None:
    qoshimcha = (
        {"agents:write", "agents:sync", "groups:write", "regions:write"}
        if bayroq
        else set()
    )
    natija = resolve_permissions(
        Role.MANAGER, {"access.manager_manages_agents": bayroq}
    )
    assert natija == KUTILGAN[Role.MANAGER] | qoshimcha


def test_manager_bayrogi_yoqilsa_ham_hisob_va_sozlama_yopiq() -> None:
    """Eng muhim chegara: menejer hech qachon admin bo'lib qolmaydi."""
    natija = resolve_permissions(
        Role.MANAGER, {"access.manager_manages_agents": True}
    )
    assert "users:write" not in natija
    assert "users:read" not in natija
    assert "settings:write" not in natija
    assert "rubric:write" not in natija


def test_sozlamalar_notegishli_rolga_tasir_qilmaydi() -> None:
    """Ikkala bayroq ham eng «ochiq» holatda — admin va viewer o'zgarmaydi."""
    ochiq = {
        "access.sales_client_rating": SALES_RATING_FULL,
        "access.manager_manages_agents": True,
    }
    assert resolve_permissions(Role.ADMIN, ochiq) == KUTILGAN[Role.ADMIN]
    assert resolve_permissions(Role.VIEWER, ochiq) == KUTILGAN[Role.VIEWER]


def test_resolve_matritsani_ozgartirib_yubormaydi() -> None:
    """Funksiya nusxa bilan ishlaydi — global lug'at buzilmasin.

    `permissions = set(...)` o'rniga havola olinsa, bitta so'rov butun
    jarayon uchun menejerga xodim boshqarishni ochib qo'yardi.
    """
    oldingi = {role: set(perms) for role, perms in ROLE_PERMISSIONS.items()}

    resolve_permissions(Role.MANAGER, {"access.manager_manages_agents": True})
    resolve_permissions(Role.SALES, {"access.sales_client_rating": SALES_RATING_FULL})

    assert {role: set(p) for role, p in ROLE_PERMISSIONS.items()} == oldingi


def test_resolve_nomalum_sozlama_kalitlarini_eutiborsiz_qoldiradi() -> None:
    natija = resolve_permissions(
        Role.VIEWER, {"access.allakachon_yoq_sozlama": True, "boshqa": "narsa"}
    )
    assert natija == KUTILGAN[Role.VIEWER]
