from cryptography.fernet import Fernet

from app import config
from app.routers import charts


def device(client):
    return client.post("/v1/auth/device").json()["token"]


def test_chart_flow(client, monkeypatch):
    monkeypatch.setattr(config.settings, "chart_enc_key", Fernet.generate_key().decode())
    monkeypatch.setattr(
        charts,
        "compute_chart",
        lambda dt, lat, lon, hsys: {
            "planets": [{"name": "Sun", "sign": "Capricorn", "degree": 10.2}],
            "houses": [{"house": 1, "sign": "Aries", "degree": 5.1}],
            "aspects": [],
            "ascendant": {"sign": "Aries", "degree": 5.1},
            "midheaven": {"sign": "Capricorn", "degree": 1.0},
        },
    )
    token = device(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/v1/charts",
        headers=headers,
        json={
            "label": "上海 · 测试盘",
            "birth_date": "2000-01-01",
            "birth_time": "08:30",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["label"] == "上海 · 测试盘"
    chart_id = created.json()["id"]

    listed = client.get("/v1/charts", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["label"] == "上海 · 测试盘"

    got = client.get(f"/v1/charts/{chart_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["planets"][0]["name"] == "Sun"

    assert client.delete(f"/v1/charts/{chart_id}", headers=headers).status_code == 204
    assert client.get(f"/v1/charts/{chart_id}", headers=headers).status_code == 404


def test_metrics_endpoint(client):
    client.get("/healthz")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "starry_http_requests_total" in resp.text


def test_chart_requires_auth(client):
    resp = client.post(
        "/v1/charts",
        json={
            "label": "上海 · 测试盘",
            "birth_date": "2000-01-01",
            "birth_time": "08:30",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    assert resp.status_code == 401


def test_chart_reading_cached(client, monkeypatch):
    from cryptography.fernet import Fernet

    from app import config

    monkeypatch.setattr(config.settings, "chart_enc_key", Fernet.generate_key().decode())
    calls = {"n": 0}

    async def fake_reading(chart):
        calls["n"] += 1
        return "这是一段温柔的星盘解读。"

    monkeypatch.setattr(charts, "generate_reading", fake_reading)
    monkeypatch.setattr(
        charts,
        "compute_chart",
        lambda dt, lat, lon, hsys: {
            "planets": [{"name": "Sun", "sign": "Capricorn", "degree": 9.9}],
            "houses": [{"house": 1, "sign": "Aquarius", "degree": 4.5}],
            "aspects": [],
            "ascendant": {"sign": "Aquarius", "degree": 4.5},
            "midheaven": {"sign": "Capricorn", "degree": 1.0},
        },
    )
    headers = {"Authorization": f"Bearer {device(client)}"}
    created = client.post(
        "/v1/charts",
        headers=headers,
        json={
            "label": "解读测试",
            "birth_date": "2000-01-01",
            "birth_time": "08:30",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    chart_id = created.json()["id"]

    first = client.post(f"/v1/charts/{chart_id}/reading", headers=headers)
    assert first.status_code == 200
    assert first.json()["cached"] is False
    second = client.post(f"/v1/charts/{chart_id}/reading", headers=headers)
    assert second.json()["cached"] is True
    assert calls["n"] == 1
