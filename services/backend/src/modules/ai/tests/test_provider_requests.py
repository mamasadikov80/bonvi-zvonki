"""Har bir vendor uchun HTTP qatlami stub qilinadi.

Maqsad: **bitta chaqiruv joyi — turli vendor** ekanini isbotlash va har
biri qanday so'rov yuborishini ko'rsatish. Haqiqiy API kaliti kerak emas:
`httpx.MockTransport` so'rovni tutib qoladi va tayyor javob qaytaradi.

Ishga tushirish (so'rovlarni ko'rish uchun `-s` bilan):
    docker compose exec -T backend pytest src/modules/ai/tests/test_provider_requests.py -q -s
"""

import json
from typing import Any

import httpx
import pytest

from src.modules.ai.application.factory import (
    MODEL_SETTING,
    PROVIDER_SETTING,
    build_client,
    resolve_from_values,
)
from src.modules.ai.domain.entities import ROLE_ASR, ROLE_LLM

FAKE_KEY = "sk-test-DO-NOT-USE-0123456789abcdef"

# ── Vendorlarning tayyor javoblari ────────────────────────────

TRANSCRIPTION_JSON = {
    "task": "transcribe",
    "language": "uzbek",
    "duration": 1.0,
    "text": "salom dunyo",
    "segments": [
        {
            "id": 0,
            "seek": 0,
            "start": 0.0,
            "end": 1.0,
            "text": "salom dunyo",
            "tokens": [1],
            "temperature": 0.0,
            "avg_logprob": -0.1,
            "compression_ratio": 1.0,
            "no_speech_prob": 0.01,
        }
    ],
}

CHAT_JSON = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1,
    "model": "stub",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "OK"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

ANTHROPIC_JSON = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5",
    "content": [{"type": "text", "text": "OK"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 1},
}

ANTHROPIC_SSE = (
    'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_test",'
    '"type":"message","role":"assistant","model":"claude-opus-5","content":[],'
    '"stop_reason":null,"stop_sequence":null,'
    '"usage":{"input_tokens":10,"output_tokens":0}}}\n\n'
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}\n\n'
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":"{\\"ball\\": 87}"}}\n\n'
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn",'
    '"stop_sequence":null},"usage":{"output_tokens":8}}\n\n'
    'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)

GEMINI_JSON = {
    "candidates": [
        {
            "content": {"parts": [{"text": "OK"}], "role": "model"},
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 1,
        "candidatesTokenCount": 1,
        "totalTokenCount": 2,
    },
}

class Recorder:
    """So'rovni yozib oladi va o'rniga tayyor javob beradi."""

    def __init__(self, payload: Any, *, sse: bool = False, status: int = 200) -> None:
        self.payload = payload
        self.sse = sse
        self.status = status
        self.request: httpx.Request | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        request.read()
        if self.sse:
            return httpx.Response(
                self.status,
                content=self.payload,
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(self.status, json=self.payload)

    @property
    def body(self) -> str:
        assert self.request is not None
        return self.request.content.decode("utf-8", errors="replace")

    def dump(self, title: str) -> None:
        assert self.request is not None, "so'rov umuman yuborilmadi"
        req = self.request
        interesting = {
            k: v
            for k, v in req.headers.items()
            if k.lower()
            in {"authorization", "x-api-key", "xi-api-key", "x-goog-api-key", "content-type"}
        }
        safe = {
            k: ("<KALIT>" if FAKE_KEY in v else v[:60]) for k, v in interesting.items()
        }
        body = self.body
        if "multipart" in req.headers.get("content-type", ""):
            body = " | ".join(
                line.strip()
                for line in body.splitlines()
                if line.strip().startswith("Content-Disposition") or _is_field(line)
            )[:400]
        else:
            body = body[:400]
        print(f"\n── {title}")
        print(f"   {req.method} {req.url}")
        print(f"   headers: {safe}")
        print(f"   body: {body}")


def _is_field(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith(("--", "Content-"))


def _client(provider: str, role: str, recorder: Recorder, model: str = ""):
    values = {
        PROVIDER_SETTING[role]: provider,
        MODEL_SETTING[role]: model,
        f"ai.{provider}_api_key": FAKE_KEY,
    }
    resolution = resolve_from_values(values, role)
    transport = httpx.MockTransport(recorder.handler)
    if provider == "gemini":
        # google-genai o'z httpx klientini quradi — unga transport beramiz
        return build_client(resolution, http_args={"transport": transport})
    return build_client(resolution, http_client=httpx.AsyncClient(transport=transport))


async def _silence():
    yield b"\x00" * 32


# ══════════════════════════════════════════════════════════════
#  ASR — bir xil chaqiruv, turli vendor
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_openai_asr_request_shape():
    """Standart model manzilga va so'rov tanasiga tushadi."""
    rec = Recorder(TRANSCRIPTION_JSON)
    client = _client("openai", ROLE_ASR, rec)
    transcript = await client.transcribe(_silence(), filename="call.mp3", language=None)
    rec.dump("OpenAI · ASR · transcribe()")

    assert str(rec.request.url) == "https://api.openai.com/v1/audio/transcriptions"
    assert rec.request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    # Reyestrdagi standart ASR modeli
    assert 'name="model"' in rec.body and "gpt-4o-transcribe" in rec.body
    assert transcript.text == "salom dunyo"


@pytest.mark.asyncio
async def test_openai_asr_response_format_depends_on_model():
    """`verbose_json` — FAQAT whisper oilasida.

    Yangi modellar (`gpt-4o-transcribe`) uni qo'llamaydi va so'rov 400
    bilan qaytadi. Shuning uchun format model nomiga qarab tanlanadi;
    vaqt belgilari (`segments`) ham shunga bog'liq.
    """
    whisper = Recorder(TRANSCRIPTION_JSON)
    result = await _client("openai", ROLE_ASR, whisper, "whisper-1").transcribe(
        _silence(), filename="call.mp3", language=None
    )
    assert "verbose_json" in whisper.body
    assert result.segments and result.segments[0].end_ms == 1000

    modern = Recorder(TRANSCRIPTION_JSON)
    await _client("openai", ROLE_ASR, modern, "gpt-4o-transcribe").transcribe(
        _silence(), filename="call.mp3", language=None
    )
    assert "verbose_json" not in modern.body


@pytest.mark.asyncio
async def test_gemini_asr_request_shape():
    rec = Recorder(GEMINI_JSON)
    client = _client("gemini", ROLE_ASR, rec)
    transcript = await client.transcribe(_silence(), filename="call.mp3", language="uz")
    rec.dump("Gemini · ASR · transcribe()")

    assert "generativelanguage.googleapis.com" in str(rec.request.url)
    assert ":generateContent" in str(rec.request.url)
    # Reyestrdagi standart model manzilga tushishi kerak
    assert "gemini-3.1-flash-lite" in str(rec.request.url)
    assert rec.request.headers["x-goog-api-key"] == FAKE_KEY
    payload = json.loads(rec.body)
    parts = payload["contents"][0]["parts"]
    assert any("inlineData" in part for part in parts), "audio inline yuborilishi kerak"
    assert transcript.text == "OK"


# ══════════════════════════════════════════════════════════════
#  LLM — bir xil chaqiruv, turli vendor
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anthropic_llm_streams_and_uses_schema():
    rec = Recorder(ANTHROPIC_SSE, sse=True)
    client = _client("anthropic", ROLE_LLM, rec)
    answer = await client.complete(
        system="Sen qo'ng'iroqni baholaysan.",
        user="Transkript: ...",
        schema={"type": "object", "properties": {"ball": {"type": "integer"}}},
        max_tokens=2048,
    )
    rec.dump("Anthropic · LLM · complete() [streaming]")

    assert str(rec.request.url) == "https://api.anthropic.com/v1/messages"
    assert rec.request.headers["x-api-key"] == FAKE_KEY
    assert rec.request.headers["anthropic-version"] == "2023-06-01"
    payload = json.loads(rec.body)
    assert payload["model"] == "claude-haiku-4-5", "standart model claude-opus-5"
    assert payload["stream"] is True, "uzun javob uchun streaming"
    assert payload["max_tokens"] == 2048
    assert payload["system"] == "Sen qo'ng'iroqni baholaysan."
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert answer == '{"ball": 87}'


@pytest.mark.asyncio
async def test_openai_llm_request_shape():
    rec = Recorder(CHAT_JSON)
    client = _client("openai", ROLE_LLM, rec)
    answer = await client.complete(system="tizim", user="foydalanuvchi", max_tokens=64)
    rec.dump("OpenAI · LLM · complete()")

    assert str(rec.request.url) == "https://api.openai.com/v1/chat/completions"
    payload = json.loads(rec.body)
    assert payload["model"] == "gpt-4.1-mini"
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert answer == "OK"



# ══════════════════════════════════════════════════════════════
#  ping() — tekshirish endpointi shu chaqiruvni ishlatadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "role", "payload", "sse"),
    [
        ("openai", ROLE_ASR, TRANSCRIPTION_JSON, False),
        ("gemini", ROLE_ASR, GEMINI_JSON, False),
        ("openai", ROLE_LLM, CHAT_JSON, False),
        ("gemini", ROLE_LLM, GEMINI_JSON, False),
        ("anthropic", ROLE_LLM, ANTHROPIC_JSON, False),
    ],
)
async def test_ping_works_for_every_provider(provider, role, payload, sse):
    rec = Recorder(payload, sse=sse)
    client = _client(provider, role, rec)
    answer = await client.ping()
    assert rec.request is not None, "ping haqiqiy so'rov yuborishi kerak"
    assert answer
    print(f"   ping {provider}/{role} → {rec.request.method} {rec.request.url}")
