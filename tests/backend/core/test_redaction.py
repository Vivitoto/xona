import pytest

from backend.app.core.redaction import REDACTED, redact_payload


@pytest.mark.parametrize(
    "field_name",
    (
        "api_key",
        "app_secret",
        "authorization",
        "cookie",
        "emby_api_key",
        "password",
        "proxy_password",
        "refresh_token",
        "secret",
        "set-cookie",
    ),
)
def test_redact_payload_masks_known_secret_field_names(field_name: str) -> None:
    payload = {field_name: "raw-secret-value"}

    redacted = redact_payload(payload)

    assert "raw-secret-value" not in repr(redacted)
    if field_name in redacted:
        assert redacted[field_name] == REDACTED


def test_redact_payload_removes_url_credentials_from_log_payloads() -> None:
    payload = {
        "proxy_url": "http://proxy-user:proxy-pass@proxy.local:8080",
        "public_url": "http://example.local/items",
    }

    redacted = redact_payload(payload)
    rendered = repr(redacted)

    assert "proxy-user" not in rendered
    assert "proxy-pass" not in rendered
    assert "proxy.local" in rendered
    assert "example.local" in rendered
    assert REDACTED in rendered


def test_redact_payload_removes_cookies_bearer_tokens_and_nested_api_keys() -> None:
    payload = {
        "headers": {
            "Authorization": "Bearer bearer-token-secret",
            "Cookie": "xona_session=cookie-secret; cf_clearance=cloudflare-secret",
        },
        "events": [
            {
                "url": "http://emby.local/Items?api_key=query-api-key-secret",
                "message": "request failed",
            },
            {
                "details": {
                    "password": "nested-password-secret",
                    "safe": "visible value",
                },
            },
        ],
    }

    redacted = redact_payload(payload)
    rendered = repr(redacted)

    assert "bearer-token-secret" not in rendered
    assert "cookie-secret" not in rendered
    assert "cloudflare-secret" not in rendered
    assert "query-api-key-secret" not in rendered
    assert "nested-password-secret" not in rendered
    assert "visible value" in rendered
    assert REDACTED in rendered
