import pytest

from app.config import settings
from app.routers import chat


async def fake_stream(messages):
    for part in ["你好", "呀～"]:
        yield part


def device(client):
    return client.post("/v1/auth/device").json()["token"]


def test_chat_stream(client, monkeypatch):
    token = device(client)
    monkeypatch.setattr(chat, "stream_completion", fake_stream)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")

    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "在吗"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "event: delta" in body
    assert "你好" in body
    assert "event: done" in body


def test_chat_requires_auth(client):
    resp = client.post("/v1/chat/stream", json={"message": "hi"})
    assert resp.status_code == 401
