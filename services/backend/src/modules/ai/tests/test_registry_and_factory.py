"""Reyestr va fabrika testlari — haqiqiy API kalitisiz.

Ishga tushirish:
    docker compose exec -T backend pytest src/modules/ai/tests -q
"""

import pytest

from src.modules.ai.application.factory import (
    MODEL_SETTING,
    PROVIDER_SETTING,
    build_client,
    resolve_from_values,
)
from src.modules.ai.domain.entities import (
    AI_ROLES,
    ROLE_ASR,
    ROLE_LLM,
    ASRClient,
    LLMClient,
)
from src.modules.ai.domain.errors import AIConfigError, redact, translate
from src.modules.ai.domain.registry import (
    AI_PROVIDERS,
    providers_for_role,
    select_options,
)
from src.modules.ai.infrastructure.builders import check_registry
from src.modules.settings.domain.entities import SETTINGS_BY_KEY

FAKE_KEY = "sk-test-DO-NOT-USE-0123456789abcdef"


def _values(role: str, provider_key: str, *, key: str | None = FAKE_KEY, model: str = ""):
    provider = {p.key: p for p in AI_PROVIDERS}[provider_key]
    values: dict[str, object] = {
        PROVIDER_SETTING[role]: provider_key,
        MODEL_SETTING[role]: model,
    }
    if key is not None:
        values[provider.api_key_setting] = key
    return values


# ── 1. Har bir provayder e'lon qilgan har bir rolda hal bo'ladi ──


@pytest.mark.parametrize(
    ("provider_key", "role"),
    [(p.key, role) for p in AI_PROVIDERS for role in sorted(p.roles)],
)
def test_every_provider_resolves_for_every_declared_role(provider_key, role):
    resolution = resolve_from_values(_values(role, provider_key), role)
    assert resolution.provider.key == provider_key
    assert resolution.model == resolution.provider.default_model(role)
    assert resolution.api_key == FAKE_KEY

    client = build_client(resolution)
    assert client.provider_key == provider_key
    assert client.model == resolution.model
    protocol = ASRClient if role == ROLE_ASR else LLMClient
    assert isinstance(client, protocol), f"{provider_key}/{role} interfeysga mos emas"


def test_admin_typed_model_wins_over_default():
    values = _values(ROLE_LLM, "anthropic", model="claude-sonnet-4-6-preview-xyz")
    assert resolve_from_values(values, ROLE_LLM).model == "claude-sonnet-4-6-preview-xyz"


# ── 2. Kalit yo'q → aniq xato, sozlama nomi bilan ──


@pytest.mark.parametrize("provider", AI_PROVIDERS, ids=lambda p: p.key)
def test_missing_key_names_the_setting(provider):
    role = sorted(provider.roles)[0]
    with pytest.raises(AIConfigError) as excinfo:
        resolve_from_values(_values(role, provider.key, key=None), role)
    message = excinfo.value.message
    assert provider.api_key_setting in message
    assert provider.label in message
    assert "Sozlamalar → AI" in message


def test_empty_string_key_counts_as_missing():
    with pytest.raises(AIConfigError):
        resolve_from_values(_values(ROLE_LLM, "anthropic", key="   "), ROLE_LLM)


def test_legacy_key_setting_is_reused():
    """Eski `llm.anthropic_api_key` to'ldirilgan bo'lsa qayta so'ralmaydi."""
    values = {
        PROVIDER_SETTING[ROLE_LLM]: "anthropic",
        "llm.anthropic_api_key": FAKE_KEY,
    }
    resolution = resolve_from_values(values, ROLE_LLM)
    assert resolution.key_source == "legacy"
    assert resolution.api_key == FAKE_KEY


# ── 3. Noma'lum provayder / noto'g'ri rol ──


def test_unknown_provider_fails_clearly():
    with pytest.raises(AIConfigError) as excinfo:
        resolve_from_values({PROVIDER_SETTING[ROLE_LLM]: "skynet"}, ROLE_LLM)
    message = excinfo.value.message
    assert "skynet" in message
    for provider in providers_for_role(ROLE_LLM):
        assert provider.key in message


def test_provider_without_the_role_fails_clearly():
    values = _values(ROLE_ASR, "anthropic")
    values[PROVIDER_SETTING[ROLE_ASR]] = "anthropic"
    with pytest.raises(AIConfigError) as excinfo:
        resolve_from_values(values, ROLE_ASR)
    assert "Anthropic Claude" in excinfo.value.message
    assert "asr" in excinfo.value.message


def test_empty_provider_falls_back_to_registry_default():
    values = {"ai.anthropic_api_key": FAKE_KEY}
    assert resolve_from_values(values, ROLE_LLM).provider.key == "anthropic"


# ── 4. Reyestr ↔ klientlar ↔ sozlamalar mosligi ──


def test_registry_and_builders_agree():
    assert check_registry() == []


def test_every_provider_has_its_secret_setting():
    for provider in AI_PROVIDERS:
        spec = SETTINGS_BY_KEY[provider.api_key_setting]
        assert spec.type == "secret"
        assert spec.category.value == "ai"


def test_select_options_come_from_the_registry():
    for role in AI_ROLES:
        values = [option["value"] for option in select_options(role)]
        assert values == [p.key for p in providers_for_role(role)]
        assert SETTINGS_BY_KEY[PROVIDER_SETTING[role]].options == select_options(role)


def test_model_field_is_free_text_not_a_select():
    for role in AI_ROLES:
        spec = SETTINGS_BY_KEY[MODEL_SETTING[role]]
        assert spec.type == "string", "model nomi qotib qolmasligi kerak"
        assert spec.options == []


# ── 5. Maxfiylik ──


def test_auth_failure_is_detected_even_when_the_vendor_returns_400():
    """Gemini noto'g'ri kalitga 401 emas, 400 qaytaradi — jonli tekshiruvda topilgan."""

    class VendorError(Exception):
        code = 400
        message = "API key not valid. Please pass a valid API key."

    error = translate(
        VendorError(), provider_label="Google Gemini", model="gemini-2.5-flash"
    )
    assert error.code == "ai_auth"
    assert "API kalit noto'g'ri" in error.message


def test_redact_removes_configured_and_pattern_secrets():
    text = f"Incorrect API key provided: {FAKE_KEY}. Also gsk_ABCDEFGHIJKLMNOP123456"
    cleaned = redact(text, (FAKE_KEY,))
    assert FAKE_KEY not in cleaned
    assert "gsk_ABCDEFGHIJKLMNOP123456" not in cleaned
    assert "«yashirildi»" in cleaned
