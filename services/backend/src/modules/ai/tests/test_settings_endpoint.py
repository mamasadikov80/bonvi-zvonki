"""`POST /api/v1/settings/ai/test` — to'rtta stsenariy.

Haqiqiy endpoint, haqiqiy JWT, haqiqiy baza. Faqat HTTP qatlami stub:
`httpx.MockTransport` provayder o'rniga javob beradi.

Ishga tushirish:
    docker compose exec -T backend pytest src/modules/ai/tests/test_settings_endpoint.py -q -s
"""

from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.main import app
from src.modules.ai.tests.test_provider_requests import CHAT_JSON, FAKE_KEY
from src.modules.settings.infrastructure.models import SettingModel

API = "http://test/api/v1"
TEST_KEYS = (
    "ai.llm_provider",
    "ai.llm_model",
    "ai.openai_api_key",
    "ai.gemini_api_key",
)


async def _snapshot() -> dict[str, Any]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(SettingModel).where(SettingModel.key.in_(TEST_KEYS))
            )
        ).scalars().all()
        return {row.key: dict(row.value) for row in rows}


async def _restore(saved: dict[str, Any]) -> None:
    async with SessionFactory() as session:
        await session.execute(delete(SettingModel).where(SettingModel.key.in_(TEST_KEYS)))
        for key, value in saved.items():
            session.add(SettingModel(key=key, category="ai", value=value))
        await session.commit()


@pytest_asyncio.fixture
async def admin_client():
    """Admin sifatida kirgan HTTP klient. Test tugagach sozlamalar tozalanadi."""
    saved = await _snapshot()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            f"{API}/auth/login",
            json={"email": "admin@zvonki.uz", "password": "admin12345"},
        )
        assert login.status_code == 200, login.text
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        try:
            yield client
        finally:
            await _restore(saved)


def _stub(monkeypatch, handler) -> None:
    """Endpoint ichidagi tekshiruvga stub transport ulaydi."""
    from src.modules.ai.application import tester as tester_module
    from src.modules.settings.presentation import router as router_module

    async def patched(session, role, **kwargs):
        return await tester_module.run_connection_test(
            session,
            role,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(router_module, "run_connection_test", patched)


async def _configure(client: httpx.AsyncClient, model: str = "") -> None:
    response = await client.put(
        f"{API}/settings",
        json={
            "values": {
                "ai.llm_provider": "openai",
                "ai.llm_model": model,
                "ai.openai_api_key": FAKE_KEY,
            }
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_success_reports_latency_and_model(admin_client, monkeypatch):
    await _configure(admin_client)
    _stub(monkeypatch, lambda request: httpx.Response(200, json=CHAT_JSON))

    response = await admin_client.post(f"{API}/settings/ai/test", json={"role": "llm"})
    body = response.json()
    print("\n1) MUVAFFAQIYAT:", body)

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4.1-mini"
    assert isinstance(body["latency_ms"], int)
    assert "ishladi" in body["detail"]


@pytest.mark.asyncio
async def test_bad_key_is_reported_in_uzbek_without_leaking_it(
    admin_client, monkeypatch
):
    await _configure(admin_client)
    _stub(
        monkeypatch,
        lambda request: httpx.Response(
            401,
            json={
                "error": {
                    "message": f"Incorrect API key provided: {FAKE_KEY}. "
                    "You can find your API key at https://platform.openai.com/account/api-keys.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        ),
    )

    body = (
        await admin_client.post(f"{API}/settings/ai/test", json={"role": "llm"})
    ).json()
    print("\n2) 401 NOTO'G'RI KALIT:", body)

    assert body["ok"] is False
    assert body["code"] == "ai_auth"
    assert "API kalit noto'g'ri" in body["error"]
    assert FAKE_KEY not in body["error"], "kalit xato xabariga tushmasligi kerak"


@pytest.mark.asyncio
async def test_unknown_model_has_its_own_message(admin_client, monkeypatch):
    await _configure(admin_client, model="gpt-9o-ultra")
    _stub(
        monkeypatch,
        lambda request: httpx.Response(
            404,
            json={
                "error": {
                    "message": "The model `gpt-9o-ultra` does not exist or you do not have access to it.",
                    "type": "invalid_request_error",
                    "code": "model_not_found",
                }
            },
        ),
    )

    body = (
        await admin_client.post(f"{API}/settings/ai/test", json={"role": "llm"})
    ).json()
    print("\n3) NOMA'LUM MODEL:", body)

    assert body["ok"] is False
    assert body["code"] == "ai_model"
    assert "gpt-9o-ultra" in body["error"]
    assert body["model"] == "gpt-9o-ultra"


@pytest.mark.asyncio
async def test_network_failure_has_its_own_message(admin_client, monkeypatch):
    await _configure(admin_client)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Temporary failure in name resolution", request=request)

    _stub(monkeypatch, boom)

    body = (
        await admin_client.post(f"{API}/settings/ai/test", json={"role": "llm"})
    ).json()
    print("\n4) TARMOQ XATOSI:", body)

    assert body["ok"] is False
    assert body["code"] == "ai_network"
    assert "ulanib bo'lmadi" in body["error"]


@pytest.mark.asyncio
async def test_missing_key_is_reported_before_any_call(admin_client, monkeypatch):
    response = await admin_client.put(
        f"{API}/settings",
        json={"values": {"ai.llm_provider": "gemini", "ai.gemini_api_key": ""}},
    )
    assert response.status_code == 200

    called: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json=CHAT_JSON)

    _stub(monkeypatch, record)
    body = (
        await admin_client.post(f"{API}/settings/ai/test", json={"role": "llm"})
    ).json()
    print("\n5) KALIT YO'Q:", body)

    assert body["ok"] is False
    assert body["code"] == "ai_not_configured"
    assert "ai.gemini_api_key" in body["error"]
    assert called == [], "kalit yo'q bo'lsa provayderga so'rov yuborilmasligi kerak"


@pytest.mark.asyncio
async def test_invalid_role_is_rejected(admin_client):
    response = await admin_client.post(
        f"{API}/settings/ai/test", json={"role": "telepathy"}
    )
    print("\n6) NOTO'G'RI ROL:", response.status_code, response.json())
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sales_role_cannot_run_the_test():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            f"{API}/auth/login",
            json={"email": "sardor@zvonki.uz", "password": "sardor12345"},
        )
        assert login.status_code == 200, login.text
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        response = await client.post(f"{API}/settings/ai/test", json={"role": "llm"})
        print("\n7) SAVDO XODIMI:", response.status_code, response.json())
        assert response.status_code == 403
