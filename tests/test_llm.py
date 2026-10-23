import asyncio
import json

import httpx
import pytest

from novel2img.llm import LLMError, OllamaClient, parse_json


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Sure! Here it is: {"a": {"b": 2}} Hope this helps.', {"a": {"b": 2}}),
        ("[1, 2]", [1, 2]),
        ("not json at all", None),
        ("", None),
    ],
)
def test_parse_json(text, expected):
    assert parse_json(text) == expected


def make_client(handler) -> OllamaClient:
    return OllamaClient(
        "http://ollama.test/", "test-model", num_ctx=4096, transport=httpx.MockTransport(handler)
    )


def test_chat_json_sends_a_json_mode_request_and_parses_the_reply():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": '{"ok": true}'}})

    reply = asyncio.run(make_client(handler).chat_json("sys", "usr", temperature=0.1, timeout=5))

    assert reply == {"ok": True}
    assert str(requests[0].url) == "http://ollama.test/api/chat"
    body = json.loads(requests[0].content)
    assert body["model"] == "test-model"
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.1, "num_ctx": 4096}
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_unparseable_reply_returns_none():
    def handler(request):
        return httpx.Response(200, json={"message": {"content": "I can't do that."}})

    assert asyncio.run(make_client(handler).chat_json("s", "u", temperature=0, timeout=5)) is None


def test_ollama_errors_are_reported():
    def handler(request):
        return httpx.Response(404, json={"error": "model 'test-model' not found"})

    with pytest.raises(LLMError, match="404: model 'test-model' not found"):
        asyncio.run(make_client(handler).chat_json("s", "u", temperature=0, timeout=5))


def test_connection_errors_mention_ollama_serve():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMError, match="ollama serve"):
        asyncio.run(make_client(handler).chat_json("s", "u", temperature=0, timeout=5))


def test_unload_sends_keep_alive_zero_and_never_raises():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        raise httpx.ConnectError("connection refused", request=request)

    asyncio.run(make_client(handler).unload())
    assert requests == [{"model": "test-model", "keep_alive": 0}]
