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
            "birth_date": "2000-01-01",
            "birth_time": "08:30",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    assert created.status_code == 201, created.text
    chart_id = created.json()["id"]

    got = client.get(f"/v1/charts/{chart_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["planets"][0]["name"] == "Sun"

    assert client.delete(f"/v1/charts/{chart_id}", headers=headers).status_code == 204
    assert client.get(f"/v1/charts/{chart_id}", headers=headers).status_code == 404


def test_chart_requires_auth(client):
    resp = client.post(
        "/v1/charts",
        json={
            "birth_date": "2000-01-01",
            "birth_time": "08:30",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    assert resp.status_code == 401
