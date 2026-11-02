import asyncio
import base64
import hashlib
import json
import os
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from fastapi.testclient import TestClient
from meridian.app import create_app
from meridian.oauth import GoogleOAuth, SCOPE
from meridian.settings import Settings, ALL_KEYS
from meridian.connectors import gmail_sync


@pytest.fixture(autouse=True)
def clean_connection_environment(monkeypatch):
    for key in ALL_KEYS:
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("MERIDIAN_KEYCHAIN_HELPER", raising=False)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as c:
        c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
        yield c


def test_settings_roundtrip_never_returns_secrets(client):
    r = client.put(
        "/api/connections",
        json={
            "canvas_token": "private-canvas-value",
            "google_client_id": "desktop-client",
            "google_client_secret": "private-google-value",
        },
    )
    assert r.status_code == 200
    assert r.json()["canvas"] and r.json()["google_client"]
    assert "private-canvas-value" not in r.text and "private-google-value" not in r.text
    assert "private-canvas-value" not in client.get("/api/state").text
    client.put("/api/connections", json={})
    assert client.get("/api/connections").json()["canvas"]
    assert not client.delete("/api/connections/canvas").json()["canvas"]
    assert client.delete("/api/connections/unknown").status_code == 404


def test_settings_fallback_permissions_and_preserved_tasks(tmp_path):
    settings = Settings(tmp_path / "settings")
    settings.set("CANVAS_TOKEN", "test-secret")
    assert (tmp_path / "settings/secrets.json").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "settings").stat().st_mode & 0o777 == 0o700
    assert Settings(tmp_path / "settings").stored("CANVAS_TOKEN") == "test-secret"
    with pytest.raises(ValueError):
        settings.set("UNRECOGNIZED", "bad")


def test_connection_validation_and_request_protection(client):
    assert (
        client.put(
            "/api/connections", json={"canvas_url": "http://canvas.example"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/connections", json={"canvas_url": "https://user:pass@canvas.example"}
        ).status_code
        == 422
    )
    assert client.post("/api/oauth/google/start").status_code == 422
    client.headers.pop("X-Meridian-Token")
    assert client.put("/api/connections", json={}).status_code == 403
    assert client.post("/api/oauth/google/start").status_code == 403


def test_oauth_uses_pkce_scope_and_one_time_state(tmp_path, monkeypatch):
    settings = Settings(tmp_path)
    settings.set("GOOGLE_CLIENT_ID", "desktop-client")
    oauth = GoogleOAuth(settings)
    query = parse_qs(
        urlparse(oauth.begin("http://127.0.0.1:18765/api/oauth/google/callback")).query
    )
    assert query["scope"] == [SCOPE]
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    verifier = oauth.pending[state]["verifier"]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == [challenge]
    oauth.pending[state]["expires"] = 0
    with pytest.raises(ValueError):
        asyncio.run(oauth.finish(state, "never-used"))
    assert state not in oauth.pending


def test_oauth_two_accounts_keep_separate_refresh_tokens(tmp_path, monkeypatch):
    settings = Settings(tmp_path)
    settings.set("GOOGLE_CLIENT_ID", "desktop-client")
    oauth = GoogleOAuth(settings)
    current = {"email": "one@example.test"}

    def handler(req):
        if req.url.path == "/token":
            assert b"code_verifier=" in req.content
            return httpx.Response(
                200,
                json={
                    "scope": SCOPE,
                    "refresh_token": "refresh-" + current["email"],
                    "access_token": "short-lived",
                },
            )
        return httpx.Response(200, json={"emailAddress": current["email"]})

    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.oauth.httpx.AsyncClient",
        lambda **kw: cls(transport=httpx.MockTransport(handler), **kw),
    )
    for email in ["one@example.test", "two@example.test"]:
        current["email"] = email
        query = parse_qs(
            urlparse(
                oauth.begin("http://127.0.0.1:18765/api/oauth/google/callback")
            ).query
        )
        state = query["state"][0]
        assert asyncio.run(oauth.finish(state, "code")) == email
        with pytest.raises(ValueError):
            asyncio.run(oauth.finish(state, "code"))
    accounts = json.loads(settings.get("GOOGLE_ACCOUNTS"))
    assert (
        len(accounts) == 2
        and accounts["one@example.test"] != accounts["two@example.test"]
    )
    assert settings.status()["accounts"] == ["one@example.test", "two@example.test"]
    assert "refresh-" not in json.dumps(settings.status())


def test_failed_google_exchange_preserves_accounts(tmp_path, monkeypatch):
    settings = Settings(tmp_path)
    settings.set("GOOGLE_CLIENT_ID", "client")
    settings.set("GOOGLE_ACCOUNTS", json.dumps({"one@example.test": "keep-refresh"}))
    oauth = GoogleOAuth(settings)
    query = parse_qs(
        urlparse(oauth.begin("http://127.0.0.1:18765/api/oauth/google/callback")).query
    )
    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.oauth.httpx.AsyncClient",
        lambda **kw: cls(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(400, json={"error": "invalid_grant"})
            ),
            **kw,
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(oauth.finish(query["state"][0], "code"))
    assert json.loads(settings.get("GOOGLE_ACCOUNTS")) == {
        "one@example.test": "keep-refresh"
    }


def test_disconnect_clears_both_google_accounts(client):
    settings = client.app.state.settings
    settings.set(
        "GOOGLE_ACCOUNTS",
        json.dumps({"one@example.test": "one", "two@example.test": "two"}),
    )
    assert len(client.get("/api/connections").json()["accounts"]) == 2
    assert not client.delete("/api/connections/gmail").json()["accounts"]
    assert not client.get("/api/state").json()["connections"]["gmail"]


def test_multi_account_sync_refreshes_each_and_scopes_evidence(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv(
        "GOOGLE_ACCOUNTS",
        json.dumps({"one@example.test": "first", "two@example.test": "second"}),
    )
    refreshed = []

    def handler(req):
        if req.url.path == "/token":
            refresh = parse_qs(req.content.decode())["refresh_token"][0]
            refreshed.append(refresh)
            return httpx.Response(200, json={"access_token": refresh + "-access"})
        if req.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "same-id"}]})
        return httpx.Response(
            200,
            json={
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"Please complete your interview by 2026-11-04 12:00"
                        ).decode()
                    },
                }
            },
        )

    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.connectors.httpx.AsyncClient",
        lambda **kw: cls(transport=httpx.MockTransport(handler), **kw),
    )
    items = asyncio.run(gmail_sync())
    assert refreshed == ["first", "second"]
    assert len(items) == 2 and items[0].source_id != items[1].source_id
    assert "one%40example.test" in items[0].source_url


def test_oauth_callback_redirect_has_no_authorization_code(client):
    r = client.get(
        "/api/oauth/google/callback?state=invalid&code=super-secret-code",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert (
        "super-secret-code" not in r.headers["location"]
        and "failed" in r.headers["location"]
    )
