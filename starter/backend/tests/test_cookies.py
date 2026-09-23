from __future__ import annotations

from fastapi import Response

from app.core.config import settings
from app.core.cookies import (
    CSRF_COOKIE,
    OAUTH_COOKIE,
    SESSION_COOKIE,
    SIGNUP_COOKIE,
    delete_csrf_cookie,
    delete_oauth_cookie,
    delete_session_cookie,
    delete_signup_cookie,
    set_csrf_cookie,
    set_oauth_cookie,
    set_session_cookie,
    set_signup_cookie,
)


def _parse_set_cookie(header: str) -> dict[str, str]:
    parts = header.split(";")
    result: dict[str, str] = {}
    result["key_value"] = parts[0].strip()
    for part in parts[1:]:
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip().lower()] = v.strip()
        else:
            result[part.strip().lower()] = "true"
    return result


def _make_response() -> Response:
    return Response(status_code=200)


def test_set_session_cookie_attributes() -> None:
    response = _make_response()
    set_session_cookie(response, "test-token")
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    parsed = _parse_set_cookie(set_cookie)
    assert SESSION_COOKIE in parsed["key_value"]
    assert "httponly" in parsed
    assert "path" in set_cookie.lower()
    assert "max-age" in set_cookie.lower() or "expires" in set_cookie.lower()


def test_set_session_cookie_httponly() -> None:
    response = _make_response()
    set_session_cookie(response, "test-token")
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie


def test_set_signup_cookie_httponly() -> None:
    response = _make_response()
    set_signup_cookie(response, "test-token")
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie


def test_set_oauth_cookie_attributes() -> None:
    response = _make_response()
    set_oauth_cookie(response, state="test-state", code_verifier="test-verifier")
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    parsed = _parse_set_cookie(set_cookie)
    assert OAUTH_COOKIE in parsed["key_value"]
    assert "httponly" in parsed
    assert "lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_csrf_cookie_not_httponly() -> None:
    response = _make_response()
    set_csrf_cookie(response, "test-csrf-token")
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" not in set_cookie


def test_delete_session_cookie() -> None:
    response = _make_response()
    delete_session_cookie(response)
    set_cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE in set_cookie
    assert "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()


def test_session_cookie_name_uses_runtime_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "session_cookie_name", "custom_session")
    response = _make_response()
    set_session_cookie(response, "test-token")
    assert "custom_session=" in response.headers.get("set-cookie", "")

    response = _make_response()
    delete_session_cookie(response)
    assert "custom_session=" in response.headers.get("set-cookie", "")


def test_delete_signup_cookie() -> None:
    response = _make_response()
    delete_signup_cookie(response)
    set_cookie = response.headers.get("set-cookie", "")
    assert SIGNUP_COOKIE in set_cookie


def test_delete_oauth_cookie() -> None:
    response = _make_response()
    delete_oauth_cookie(response)
    set_cookie = response.headers.get("set-cookie", "")
    assert OAUTH_COOKIE in set_cookie


def test_delete_csrf_cookie() -> None:
    response = _make_response()
    delete_csrf_cookie(response)
    set_cookie = response.headers.get("set-cookie", "")
    assert CSRF_COOKIE in set_cookie
