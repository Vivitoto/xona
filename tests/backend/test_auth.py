from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api import auth as auth_module
from backend.app.api.auth import PasswordHasher
from backend.app.core.settings import Settings
from backend.app.main import create_app


ORIGIN = "http://testserver"
PASSWORD = "correct horse battery staple"
USERNAME = "vito"


def _settings(tmp_path: Path, *, enabled: bool = True, secure: bool = False) -> Settings:
    password_hash = PasswordHasher().hash(PASSWORD)
    return Settings(
        config_dir=tmp_path / "config",
        auth_enabled=enabled,
        auth_username=USERNAME,
        auth_password_hash=password_hash,
        auth_cookie_secure=secure,
    )


def _client(settings: Settings, *, base_url: str = ORIGIN) -> TestClient:
    app = create_app(settings)

    @app.api_route("/api/probe", methods=["GET", "POST"])
    def api_probe() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app, base_url=base_url)


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text


def test_auth_enabled_rejects_unauthenticated_api_routes_by_default(
    tmp_path: Path,
) -> None:
    client = _client(_settings(tmp_path))

    response = client.get("/api/probe")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_auth_disabled_allows_anonymous_api_access(tmp_path: Path) -> None:
    client = _client(_settings(tmp_path, enabled=False))

    response = client.get("/api/probe")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_health_check_remains_public_when_auth_enabled(tmp_path: Path) -> None:
    client = _client(_settings(tmp_path))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_success_sets_signed_session_and_status_reports_user(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    client = _client(settings)

    response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": USERNAME}
    assert "xona_session" in client.cookies
    assert response.cookies.get("xona_session") is not None

    status = client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json() == {"authenticated": True, "username": USERNAME}

    protected = client.get("/api/probe")
    assert protected.status_code == 200
    assert protected.json() == {"ok": True}


def test_login_rejects_wrong_credentials_without_setting_cookie(
    tmp_path: Path,
) -> None:
    client = _client(_settings(tmp_path))

    response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": "wrong"},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 401
    assert "xona_session" not in response.headers.get("set-cookie", "")
    assert client.cookies.get("xona_session") is None


def test_session_cookie_attributes_include_secure_when_configured(
    tmp_path: Path,
) -> None:
    client = _client(_settings(tmp_path, secure=True), base_url="https://testserver")

    response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": "https://testserver"},
    )

    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"]
    assert "xona_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
    assert "Max-Age=604800" in set_cookie
    assert "Secure" in set_cookie


def test_logout_clears_current_client_session(tmp_path: Path) -> None:
    client = _client(_settings(tmp_path))
    _login(client)

    response = client.post("/api/auth/logout", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert "xona_session" not in client.cookies
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/status").json() == {"authenticated": False}
    assert client.get("/api/probe").status_code == 401


def test_unsafe_api_requests_require_matching_origin_when_auth_enabled(
    tmp_path: Path,
) -> None:
    client = _client(_settings(tmp_path))

    missing_origin = client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    assert missing_origin.status_code == 403

    mismatched_origin = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": "http://evil.example"},
    )
    assert mismatched_origin.status_code == 403

    malformed_origin = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": "http://testserver:bad"},
    )
    assert malformed_origin.status_code == 403

    _login(client)

    protected_missing_origin = client.post("/api/probe")
    assert protected_missing_origin.status_code == 403

    protected_mismatched_origin = client.post(
        "/api/probe", headers={"Origin": "http://evil.example"}
    )
    assert protected_mismatched_origin.status_code == 403

    logout_missing_origin = client.post("/api/auth/logout")
    assert logout_missing_origin.status_code == 403


def test_tampered_session_cookie_is_rejected(tmp_path: Path) -> None:
    client = _client(_settings(tmp_path))
    _login(client)
    valid_cookie = client.cookies["xona_session"]
    client.cookies.clear()
    client.cookies.set("xona_session", f"{valid_cookie}tampered")

    assert client.get("/api/auth/status").json() == {"authenticated": False}
    assert client.get("/api/probe").status_code == 401


def test_expired_session_cookie_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(_settings(tmp_path))
    _login(client)

    monkeypatch.setattr(auth_module, "SESSION_MAX_AGE_SECONDS", -1)

    assert client.get("/api/auth/status").json() == {"authenticated": False}
    assert client.get("/api/probe").status_code == 401


def test_password_hash_not_plaintext_and_public_settings_redacts_it(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    assert settings.auth_password_hash != PASSWORD
    assert PasswordHasher().verify(PASSWORD, settings.auth_password_hash)

    public_settings = settings.public_dict()
    rendered = repr(public_settings)
    assert PASSWORD not in rendered
    assert settings.auth_password_hash not in rendered
    assert public_settings["auth_password_hash"] == "********"
