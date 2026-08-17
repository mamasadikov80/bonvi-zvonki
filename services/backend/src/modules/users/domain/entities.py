"""Foydalanuvchi domeni — sof Python, framework'ga bog'liq emas."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    """Tizimdagi 4 ta rol.

    ADMIN   — hamma narsani boshqaradi (foydalanuvchilar, sozlamalar, rubrika)
    MANAGER — barcha ma'lumotni filtrlar bilan ko'radi va tahlil qiladi (Power BI kabi)
    SALES   — savdo xodimi. Faqat O'ZINING ballarini ko'radi.
              Akkaunti o'zi tomonidan boshqarilmaydi — tizim baholarni yozib boradi.
    VIEWER  — faqat ko'rish. Savdo xonasidagi monitor uchun (login talab qilmaydigan
              cheklangan ko'rinish).
    """

    ADMIN = "admin"
    MANAGER = "manager"
    SALES = "sales"
    VIEWER = "viewer"

    @property
    def label_uz(self) -> str:
        return {
            Role.ADMIN: "Administrator",
            Role.MANAGER: "Menejer",
            Role.SALES: "Savdo xodimi",
            Role.VIEWER: "Kuzatuvchi",
        }[self]


# ── Ruxsatlar matritsasi ──────────────────────────────────────
# Bitta joyda saqlanadi — router'larda tarqalib ketmasin.

ROLE_PERMISSIONS: dict[Role, set[str]] = {
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
    },
    Role.MANAGER: {
        "agents:read",
        "clients:read",
        "calls:read",
        "groups:read",
        "regions:read",
        "scores:read", "scores:write",   # menejer izoh qo'sha oladi
        "surveys:read",
        "analytics:read", "analytics:read_all",
        "rubric:read",
        "settings:read",
        # agents:write / agents:sync / groups:write / regions:write — sozlamalar
        # orqali beriladi (access.manager_manages_agents), pastdagi
        # resolve_permissions() ga qarang
    },
    Role.SALES: {
        # Faqat o'z ma'lumoti — filtrlash servis qatlamida bajariladi
        "calls:read:own",
        "scores:read:own",
        "analytics:read:own",
        # Hudud filtri hamma rolda kerak, nomlar maxfiy emas
        "regions:read",
        # surveys:read:own — sozlamalar orqali beriladi
        # (access.sales_client_rating)
    },
    Role.VIEWER: {
        "analytics:read",
        "regions:read",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


# ── Dinamik ruxsatlar ─────────────────────────────────────────
# Ba'zi ruxsatlar rolga qattiq bog'lanmagan — admin ularni
# dashboard → Sozlamalar → Ruxsatlar bo'limidan yoqadi/o'chiradi.

SALES_RATING_HIDDEN = "hidden"
SALES_RATING_SCORE_ONLY = "score_only"
SALES_RATING_FULL = "full"


def resolve_permissions(role: Role, access: dict[str, str | bool]) -> set[str]:
    """Rolning bazaviy ruxsatlariga sozlamalardan kelganini qo'shadi.

    `access` — sozlamalardan olingan qiymatlar:
      access.sales_client_rating    hidden | score_only | full
      access.manager_manages_agents bool
    """
    permissions = set(ROLE_PERMISSIONS.get(role, set()))

    if role is Role.SALES:
        rating = access.get("access.sales_client_rating", SALES_RATING_SCORE_ONLY)
        if rating in (SALES_RATING_SCORE_ONLY, SALES_RATING_FULL):
            permissions.add("surveys:read:own")
        if rating == SALES_RATING_FULL:
            permissions.add("surveys:read:own:comments")

    if role is Role.MANAGER and access.get("access.manager_manages_agents"):
        # Guruhni xodimga biriktirish — aslida xodimni boshqarish,
        # shuning uchun `groups:write` shu bayroqqa qo'shiladi.
        # `regions:write` ham shu yerda: hududlar ro'yxati xodim va guruh
        # formalarining tanlov manbai, ikkalasini boshqargan uni ham boshqaradi.
        permissions |= {
            "agents:write",
            "agents:sync",
            "groups:write",
            "regions:write",
        }

    return permissions


@dataclass(slots=True)
class User:
    id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    agent_id: UUID | None = None  # SALES roli uchun — qaysi agentga bog'langan
    created_at: datetime | None = None

    @property
    def can_manage_users(self) -> bool:
        return has_permission(self.role, "users:write")

    @property
    def sees_all_agents(self) -> bool:
        return has_permission(self.role, "analytics:read_all")
