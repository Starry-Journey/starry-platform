from app.config import settings


def device(client):
    resp = client.post("/v1/auth/device")
    assert resp.status_code == 200
    return resp.json()["token"]


def test_comments_flow(client, monkeypatch):
    token = device(client)
    headers = {"Authorization": f"Bearer {token}"}

    assert (
        client.post("/v1/comments", json={"room": "post:abc", "author": "a", "content": "x"}).status_code
        == 401
    )

    created = client.post(
        "/v1/comments",
        headers=headers,
        json={"room": "post:abc", "author": "starry", "content": "第一条评论"},
    )
    assert created.status_code == 201
    comment_id = created.json()["id"]

    listed = client.get("/v1/comments", params={"room": "post:abc"})
    assert listed.status_code == 200
    assert [c["content"] for c in listed.json()["items"]] == ["第一条评论"]

    monkeypatch.setattr(settings, "admin_token", "admin-secret")
    assert client.delete(f"/v1/comments/{comment_id}").status_code == 403
    deleted = client.delete(f"/v1/comments/{comment_id}", headers={"X-Admin-Token": "admin-secret"})
    assert deleted.status_code == 204
    assert client.get("/v1/comments", params={"room": "post:abc"}).json()["items"] == []


def test_comment_validation(client):
    token = device(client)
    resp = client.post(
        "/v1/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"room": "post:abc", "author": "a", "content": ""},
    )
    assert resp.status_code == 422
