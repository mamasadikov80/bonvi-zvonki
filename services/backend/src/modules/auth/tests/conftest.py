"""Auth testlari uchun fixture'lar.

Kirish oqimini tekshirish uchun PAROLI BIZGA MA'LUM hisob kerak. Uni
yaratadigan `make_user` fixture'i `users` modulida turadi (hisob —
o'sha modulning obyekti), bu yerda faqat ko'rinadigan qilinadi.

`from ... import make_user` — pytest uchun yetarli: conftest'ga
import qilingan fixture shu papkadagi barcha testlarga ochiladi.
"""

from src.modules.users.tests.conftest import (  # noqa: F401
    TempUser,
    UserFactory,
    make_user,
    yangi_email,
)

__all__ = ["TempUser", "UserFactory", "make_user", "yangi_email"]
