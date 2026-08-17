"""`calls.list` javobidagi bitta qatorni o'qish — chegaraviy holatlar.

NEGA BU TESTLAR BOR. Sinxronizatsiyaning asosiy filtri shu joyda hal
bo'ladi: audiosi bor qo'ng'iroq saqlanadi, qolgani umuman olinmaydi.
Ya'ni `MoizvonkiCall.from_api()` dagi bitta noto'g'ri «bor/yo'q» qarori
yo ro'yxatni baholanmaydigan qatorlar bilan to'ldiradi, yo haqiqiy
suhbatni jimgina yo'qotadi. Ikkalasi ham ekranda «tizim xato qilyapti»
bo'lib ko'rinadi, sababi esa shu yerda — bitta maydonni o'qishda.

⚠️ Bu testlar TARMOQQA CHIQMAYDI: `from_api()` sof funksiya, MoyZvonki'ga
hech qanday so'rov yubormaydi.
"""

import pytest

from src.modules.moizvonki.domain.entities import MoizvonkiCall

#: Har testda bir xil bo'lgan majburiy maydonlar
ASOS = {"db_call_id": "42", "start_time": 1_700_000_000}


def _call(**payload) -> MoizvonkiCall:
    return MoizvonkiCall.from_api({**ASOS, **payload})


# ══════════════════════════════════════════════════════════════
#  Yozuv havolasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "qiymat",
    [
        "records/2026/08/call-42.mp3",
        "/records/call-42.mp3",
        "https://bonvi.moizvonki.ru/records/call-42.mp3",
        "http://bonvi.moizvonki.ru/records/call-42.mp3",
    ],
)
def test_haqiqiy_havola_saqlanadi(qiymat: str) -> None:
    """Nisbiy yo'l ham, to'liq manzil ham audio hisoblanadi.

    Hujjatda manzil mutlaqmi yoki nisbiymi aytilmagan — ikkalasi ham
    o'tishi SHART, aks holda o'rnatmaga qarab hamma qo'ng'iroq
    «audiosiz» bo'lib qolardi.
    """
    call = _call(recording=qiymat)
    assert call.has_recording
    assert call.recording == qiymat


@pytest.mark.parametrize(
    "qiymat",
    ["", "   ", "0", "-", "null", "NULL", "none", "false", "n/a", "undefined"],
)
def test_joy_egallovchi_qiymat_audio_emas(qiymat: str) -> None:
    """`0`, `null`, chiziqcha — «yozuv yo'q» degani, manzil emas.

    Bunday qiymat matn sifatida saqlansa, quvur qo'ng'iroqni baholashga
    urinadi va MoyZvonki'dan 404 oladi — ya'ni xato haqiqiy sababdan
    ancha uzoqda, tinglash paytida chiqadi.
    """
    call = _call(recording=qiymat)
    assert not call.has_recording
    assert call.recording is None


@pytest.mark.parametrize("qiymat", ["javascript:alert(1)", "data:audio/mp3;base64,AA"])
def test_audio_bolmagan_sxema_rad_etiladi(qiymat: str) -> None:
    """http(s) bo'lmagan sxema — bu audio manzili emas."""
    assert _call(recording=qiymat).recording is None


def test_maydon_yoq_bolsa_audio_yoq() -> None:
    assert _call().recording is None


# ══════════════════════════════════════════════════════════════
#  `answered` bayrog'i
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("xom", "kutilgan"),
    [
        (1, True),
        ("1", True),
        (True, True),
        ("true", True),
        (0, False),
        ("0", False),
        (False, False),
        ("false", False),
        (None, False),
    ],
)
def test_answered_har_qanday_shaklda_oqiladi(xom: object, kutilgan: bool) -> None:
    """Satr shaklidagi `"true"` butun sahifani yiqitmasligi kerak.

    Ilgari bu `bool(int(value))` edi: `int("true")` → `ValueError`, ya'ni
    bitta g'alati qator butun sinxronizatsiyani to'xtatardi.
    """
    assert _call(answered=xom).answered is kutilgan


# ══════════════════════════════════════════════════════════════
#  Mijoz nomi
# ══════════════════════════════════════════════════════════════


def test_mijoz_nomi_saqlanadi() -> None:
    call = _call(client_name="Anvar aka", client_number="+998901234567")
    assert call.client_name == "Anvar aka"
    assert call.client_number == "+998901234567"
    assert call.client_label == "Anvar aka"


@pytest.mark.parametrize(
    "nom",
    ["+998901234567", "998901234567", "+998 90 123-45-67", "901234567"],
)
def test_raqamning_nusxasi_nom_deb_saqlanmaydi(nom: str) -> None:
    """MoyZvonki kontakt katalogda bo'lmasa nom o'rniga raqamni beradi.

    Uni nom deb saqlash jadvalda foydasiz takror ko'rinadi va «nomi bor»
    degan yolg'on belgi beradi. Raqam alohida ustunda turadi.
    """
    call = _call(client_name=nom, client_number="+998901234567")
    assert call.client_name is None
    # Nom yo'q — lekin ustun bo'sh qolmaydi, raqam ko'rsatiladi
    assert call.client_label == "+998901234567"


def test_nom_ham_raqam_ham_yoq() -> None:
    call = _call()
    assert call.client_name is None
    assert call.client_label is None
