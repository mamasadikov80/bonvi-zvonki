"""`handlers/groups.py` → `_parse_rate()` — guruh tugmasidan kelgan ma'lumot.

Sof unit test: Telegram API ga chiqmaydi, faqat satr ajratiladi.

NEGA MUHIM: `callback_data` — TASHQARIDAN keladigan satr. Telegram uni
tekshirmaydi va eski xabardagi tugma bir necha oydan keyin ham bosilishi
mumkin. Ajratish qat'iy bo'lmasa:

  · noto'g'ri ball (0, 9, −1) bazaga tushib statistikani buzardi;
  · bo'sh token bilan so'rov backend'ga ketardi;
  · kutilmagan shakl handler'ni yiqitib, mijoz «bot ishlamayapti»
    degan taassurot olardi.

To'g'ri xatti-harakat: shubhali bo'lsa `None` — handler esa mijozga
«Tugma eskirgan» deb xotirjam javob beradi.
"""

import pytest

from src.handlers.groups import _parse_rate
from src.views.groups import survey_kb

TOKEN = "abc123token"


# ══════════════════════════════════════════════════════════════
#  To'g'ri kirish
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ball", [1, 2, 3, 4, 5])
def test_har_ball_togri_ajratiladi(ball: int) -> None:
    assert _parse_rate(f"rate:{TOKEN}:{ball}") == (TOKEN, ball)


def test_views_qurgan_callback_data_ajratiladi() -> None:
    """Ikki modul kelishuvi: `views` yozadi, `handlers` o'qiydi.

    Format bir tomonda o'zgarsa, guruhdagi hamma tugma jimgina
    «eskirgan» bo'lib qolardi — shuning uchun ular birga tekshiriladi.
    """
    markup = survey_kb("bonvi_bot", TOKEN, miniapp_name="")

    natijalar = [_parse_rate(t.callback_data) for t in markup.inline_keyboard[0]]

    assert natijalar == [(TOKEN, n) for n in range(1, 6)]


def test_token_atrofidagi_bosh_joy_kesiladi() -> None:
    assert _parse_rate(f"rate: {TOKEN} :4") == (TOKEN, 4)


# ══════════════════════════════════════════════════════════════
#  Buzuq kirish → None
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("data", "sabab"),
    [
        ("", "bo'sh satr"),
        ("rate", "ikki nuqta yo'q"),
        (f"rate:{TOKEN}", "ball yo'q"),
        (f"rate:{TOKEN}:3:extra", "ortiqcha bo'lak"),
        (f"vote:{TOKEN}:3", "boshqa prefiks"),
        (f"gd:flag:{TOKEN}", "boshqa oqimning tugmasi"),
        (f"RATE:{TOKEN}:3", "katta harfli prefiks"),
        ("rate::3", "token bo'sh"),
        ("rate:   :3", "token faqat bo'shliq"),
        (f"rate:{TOKEN}:x", "ball son emas"),
        (f"rate:{TOKEN}:", "ball bo'sh"),
        (f"rate:{TOKEN}:3.5", "kasr son"),
    ],
)
def test_buzuq_kirish_none_qaytaradi(data: str, sabab: str) -> None:
    assert _parse_rate(data) is None, f"«{data}» o'tib ketdi ({sabab})"


@pytest.mark.parametrize("ball", ["0", "6", "-1", "99", "100"])
def test_oraliqdan_tashqari_ball_rad_etiladi(ball: str) -> None:
    """1–5 dan tashqarisi bazaga tushsa CSAT o'rtachasi buzilardi."""
    assert _parse_rate(f"rate:{TOKEN}:{ball}") is None


def test_juda_uzun_token_ham_yiqitmaydi() -> None:
    """Xato bo'lsa ham — istisno emas, `None` yoki tartibli natija."""
    uzun = "a" * 5000

    natija = _parse_rate(f"rate:{uzun}:3")

    assert natija == (uzun, 3)


def test_ajratish_hech_qachon_istisno_kotarmaydi() -> None:
    """Handler `None` ni kutadi — istisno mijozga xato ekrani berardi."""
    for data in ("rate:::", ":::", "rate:a:b:c:d", "🙂", "rate:🙂:3"):
        assert _parse_rate(data) is None or isinstance(_parse_rate(data), tuple)
