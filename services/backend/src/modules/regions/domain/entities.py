"""Hudud domeni — sof Python, bazani ham, FastAPI'ni ham bilmaydi.

Hudud — bu savdo bo'linmasi, viloyat EMAS. Bonvi bitta viloyatni bir nechta
mustaqil hududga bo'lishi mumkin («Samarqand shimol», «Samarqand janub»),
shuning uchun kodda qat'iy viloyatlar ro'yxati YO'Q — ro'yxatni admin
boshqaradi, yagona manba `regions` jadvali.

Diqqat: `agents.region`, `clients.region`, `telegram_groups.region` — matn
bo'lib qoladi, FK ga aylantirilmaydi (analitikadagi o'nlab `GROUP BY region`
qayta yozilmasin). Buning evaziga nom o'zgarganda kaskad yangilanish
MAJBURIY — `RegionService.update` ga qarang.
"""

# Nom uzunligi — `regions.name`, shuningdek `telegram_groups.region` ham
# `String(64)`. Undan uzun nom kaskad yangilashda kesilib qolardi.
REGION_NAME_MAX = 64

# Izoh uzunligi — «qaysi viloyatga kiradi» kabi qisqa matn uchun
REGION_NOTE_MAX = 255

# Boshlang'ich to'ldirishda tartib raqamlari shu qadam bilan beriladi.
# Oraliq ataylab bo'sh qoldiriladi: admin ikkita hudud orasiga
# yangisini butun ro'yxatni qayta raqamlamasdan qo'ya olsin.
SORT_ORDER_STEP = 10


def normalize_region_name(value: str) -> str:
    """Nomni saqlashdan oldin tozalaydi: chetki va takroriy bo'shliqlarsiz.

    «Samarqand  shimol » va «Samarqand shimol» bitta hudud bo'lishi kerak —
    aks holda unique indeks ikkalasini ham o'tkazib yuboradi va dropdownda
    ko'zga bir xil ko'rinadigan ikki qator paydo bo'ladi.
    """
    return " ".join(value.split())


def usage_phrase_uz(agents: int, clients: int, groups: int) -> str:
    """«3 ta xodim va 12 ta mijozda» — o'chirishni rad etish xabari uchun.

    Nol bo'lgan turlar tushirib qoldiriladi: «0 ta guruh» adminga hech narsa
    aytmaydi, faqat xabarni uzaytiradi.
    """
    parts = [
        f"{count} ta {noun}"
        for count, noun in ((agents, "xodim"), (clients, "mijoz"), (groups, "guruh"))
        if count
    ]
    if not parts:
        return "hech qayerda"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " va " + parts[-1]
