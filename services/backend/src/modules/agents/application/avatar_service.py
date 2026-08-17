"""Profil rasmi (avatar) bilan ishlash.

Yuklangan rasm normallashtiriladi:
  • kvadrat qilib markazdan kesiladi
  • 256×256 ga kichraytiriladi
  • WebP formatiga o'giriladi

Sabab: brauzerga har xil formatdagi 5 MB'lik rasmlar tushmasin —
avatar hamma joyda 32–44 px ko'rsatiladi, katta fayl keraksiz.
Natijada har avatar ~8–15 KB bo'ladi.
"""

import io
from pathlib import Path
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from src.core.exceptions import ValidationError

# Konteyner ichidagi yo'l — docker volume bilan saqlanadi
MEDIA_ROOT = Path("/app/media")
AVATAR_DIR = MEDIA_ROOT / "avatars"

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
OUTPUT_SIZE = 256
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _ensure_dir() -> None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)


def save_avatar(agent_id: UUID, raw: bytes, content_type: str | None) -> str:
    """Rasmni saqlaydi va nisbiy URL qaytaradi.

    Eski rasm bo'lsa ustiga yoziladi — agent uchun bitta fayl.
    """
    if content_type and content_type.lower() not in ALLOWED_MIME:
        raise ValidationError(
            "Faqat JPG, PNG, WebP yoki GIF rasm yuklash mumkin"
        )

    if len(raw) > MAX_BYTES:
        size_mb = len(raw) / 1024 / 1024
        raise ValidationError(
            f"Rasm hajmi {size_mb:.1f} MB — maksimal 5 MB bo'lishi kerak"
        )

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Fayl rasm sifatida o'qilmadi") from exc

    # Shaffoflikni oq fonga qo'yamiz (WebP'da artefakt bo'lmasin)
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        converted = image.convert("RGBA")
        background.paste(converted, mask=converted.split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    # Markazdan kvadrat kesish
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))

    image = image.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)

    _ensure_dir()
    path = AVATAR_DIR / f"{agent_id}.webp"
    image.save(path, "WEBP", quality=88, method=5)

    # Brauzer keshini yangilash uchun versiya qo'shamiz
    return f"/media/avatars/{agent_id}.webp?v={path.stat().st_mtime_ns}"


def delete_avatar(agent_id: UUID) -> None:
    path = AVATAR_DIR / f"{agent_id}.webp"
    path.unlink(missing_ok=True)
