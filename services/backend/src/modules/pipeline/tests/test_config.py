"""`load_config()` — quvur sozlamalari muhit o'zgaruvchilaridan.

Sof unit test: bazasiz.

NEGA MUHIM: bular vendor chegaralari. Sozlanmagan yoki noto'g'ri
yozilgan qiymat 429 ga (ya'ni to'xtagan navbatga) yoki teskarisiga —
cheksiz parallel so'rovga va kutilmagan hisobga olib keladi. Shuning
uchun har maydonda EHTIYOTKOR standart bor va buzuq qiymat standartga
qaytadi, ilova ishga tushmay qolmaydi.
"""

import pytest

from src.modules.pipeline.domain.config import PipelineConfig, load_config

#: Kod va’da qilgan standart qiymatlar (`domain/config.py`)
DEFAULTS = {
    "concurrency": 4,
    "asr_rpm": 60,
    "llm_rpm": 120,
    "max_retries": 4,
    "backoff_base_sec": 2.0,
    "backoff_max_sec": 60.0,
    # Arzon modellar rubrika arifmetikasida adashadi, lekin validator
    # xatosi promptga qo'shilgach tuzatadi — 2 ta qayta urinish
    "invalid_retries": 2,
    "min_duration_sec": 30,
    "call_timeout_sec": 900.0,
    "lock_ttl_sec": 1800,
    "progress_every": 10,
}

ENV_KEYS = (
    "PIPELINE_CONCURRENCY",
    "PIPELINE_ASR_RPM",
    "PIPELINE_LLM_RPM",
    "PIPELINE_MAX_RETRIES",
    "PIPELINE_BACKOFF_BASE_SEC",
    "PIPELINE_BACKOFF_MAX_SEC",
    "PIPELINE_INVALID_RETRIES",
    "PIPELINE_MIN_DURATION_SEC",
    "PIPELINE_CALL_TIMEOUT_SEC",
    "PIPELINE_LOCK_TTL_SEC",
    "PIPELINE_PROGRESS_EVERY",
)


@pytest.fixture
def toza_muhit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Barcha `PIPELINE_*` o'chiriladi — natija muhitga bog'liq bo'lmasin."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_sozlanmagan_tizim_ehtiyotkor_standartlar_bilan_ishlaydi(toza_muhit) -> None:
    config = load_config()

    for field, expected in DEFAULTS.items():
        assert getattr(config, field) == expected, f"«{field}» standarti o'zgargan"


def test_muhit_qiymati_oqiladi(toza_muhit, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "12")
    monkeypatch.setenv("PIPELINE_ASR_RPM", "300")
    monkeypatch.setenv("PIPELINE_BACKOFF_MAX_SEC", "45.5")

    config = load_config()

    assert config.concurrency == 12
    assert config.asr_rpm == 300
    assert config.backoff_max_sec == 45.5
    # Tegilmaganlari standartda qoladi
    assert config.llm_rpm == DEFAULTS["llm_rpm"]


def test_har_chaqiruvda_qayta_oqiladi(toza_muhit, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kesh YO'Q — aks holda testda ham, konteynerda ham eski qiymat qolardi."""
    assert load_config().concurrency == 4

    monkeypatch.setenv("PIPELINE_CONCURRENCY", "7")

    assert load_config().concurrency == 7


def test_son_bolmagan_qiymat_standartga_qaytadi(
    toza_muhit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.env` da xato yozilsa quvur TO'XTAMASLIGI kerak."""
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "ko'p")
    monkeypatch.setenv("PIPELINE_BACKOFF_BASE_SEC", "tez")

    config = load_config()

    assert config.concurrency == DEFAULTS["concurrency"]
    assert config.backoff_base_sec == DEFAULTS["backoff_base_sec"]


def test_bosh_satr_standartga_qaytadi(
    toza_muhit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PIPELINE_ASR_RPM=` — compose'da tez-tez uchraydigan holat."""
    monkeypatch.setenv("PIPELINE_ASR_RPM", "")
    monkeypatch.setenv("PIPELINE_MIN_DURATION_SEC", "   ")

    config = load_config()

    assert config.asr_rpm == DEFAULTS["asr_rpm"]
    assert config.min_duration_sec == DEFAULTS["min_duration_sec"]


def test_nol_parallellik_bittaga_kotariladi(
    toza_muhit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """0 bo'lsa hech narsa ishlanmasdi — navbat jimgina to'xtardi."""
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "0")

    assert load_config().concurrency == 1


def test_manfiy_qiymatlar_pastki_chegarada_ushlanadi(
    toza_muhit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PIPELINE_ASR_RPM", "-5")
    monkeypatch.setenv("PIPELINE_BACKOFF_MAX_SEC", "-1")
    monkeypatch.setenv("PIPELINE_LOCK_TTL_SEC", "5")
    monkeypatch.setenv("PIPELINE_CALL_TIMEOUT_SEC", "1")

    config = load_config()

    assert config.asr_rpm == 0  # 0 = cheklovsiz, manfiy emas
    assert config.backoff_max_sec == 0.1
    assert config.lock_ttl_sec == 60  # qulf juda qisqa bo'lmasin
    assert config.call_timeout_sec == 30.0


def test_rpm_nol_cheklovsiz_degani(toza_muhit, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_LLM_RPM", "0")

    assert load_config().llm_rpm == 0


def test_sozlama_ozgarmas(toza_muhit) -> None:
    """`frozen=True` — quvur o'rtasida chegara o'zgarib qolmasin."""
    config = load_config()

    with pytest.raises((AttributeError, TypeError)):
        config.concurrency = 99  # type: ignore[misc]


def test_from_env_va_load_config_bir_xil_natija(toza_muhit) -> None:
    assert load_config() == PipelineConfig.from_env()
