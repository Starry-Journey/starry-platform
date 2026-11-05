from app.config import settings


def test_daily_quota(client, monkeypatch):
    from app.routers import chat

    async def fake_stream(messages):
        yield "ok"

    monkeypatch.setattr(chat, "stream_completion", fake_stream)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "daily_message_limit", 1)

    token = client.post("/v1/auth/device").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    with client.stream("POST", "/v1/chat/stream", headers=headers, json={"message": "一"}) as r:
        assert r.status_code == 200
        "".join(r.iter_text())

    second = client.post("/v1/chat/stream", headers=headers, json={"message": "二"})
    assert second.status_code == 429
