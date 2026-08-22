"""Barcha ORM modellarini metadata'ga ro'yxatdan o'tkazadi.

NEGA BU MODUL BOR
  SQLAlchemy yozishdan oldin jadvallarni bog'liqlik tartibida saralaydi
  va buning uchun FK ko'rsatayotgan jadval `Base.metadata` da BO'LISHI
  shart. Bir modul faqat o'ziga keragini import qilsa, o'sha jarayonda
  metadata to'liq bo'lmaydi va birinchi `flush` da shunday xato chiqadi:

      NoReferencedTableError: Foreign key associated with column
      'surveys.client_id' could not find table 'clients'

  Xato IMPORTDA emas, ISHLASH PAYTIDA chiqadi — ya'ni testda emas,
  haqiqiy yozuvda. Va faqat ma'lum yo'l bosib o'tilganda: masalan
  so'rovnoma yaratilganda. Shu sababli u uzoq vaqt sezilmay turishi
  mumkin.

  Bu tuzoq loyihada ikki marta ishga tushgan:
    · `seed.py` — `telegram_groups` import qilinmagani uchun seed
      yiqilgan, `&&` zanjiri esa uvicorn'ni ishga tushirmagan
      (konteyner qayta ishga tushaverardi);
    · `worker.py` — cadence vazifasi `clients` siz yiqilardi.

  Shuning uchun jarayon boshlanadigan HAR BIR joy (`main.py`,
  `bootstrap.py`, `seed.py`, `worker.py`) shu bitta modulni import
  qiladi. Yangi modul qo'shilganda faqat shu ro'yxat yangilanadi.

Modullar ataylab `_` bilan nomlangan va `noqa: F401` bilan belgilangan:
ular ishlatilmaydi, faqat import qilingani uchun kerak.
"""

from src.modules.agents.infrastructure import models as _agents  # noqa: F401
from src.modules.calls.infrastructure import models as _calls  # noqa: F401
from src.modules.clients.infrastructure import models as _clients  # noqa: F401
from src.modules.groups.infrastructure import models as _groups  # noqa: F401
from src.modules.pipeline.infrastructure import models as _pipeline  # noqa: F401
from src.modules.regions.infrastructure import models as _regions  # noqa: F401
from src.modules.sales.infrastructure import models as _sales  # noqa: F401
from src.modules.scoring.infrastructure import models as _scoring  # noqa: F401
from src.modules.scoring.infrastructure import rubric_models as _rubric  # noqa: F401
from src.modules.settings.infrastructure import models as _settings  # noqa: F401
from src.modules.surveys.infrastructure import models as _surveys  # noqa: F401
from src.modules.users.infrastructure import models as _users  # noqa: F401

__all__: list[str] = []
