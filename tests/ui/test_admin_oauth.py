from __future__ import annotations

import sys
import types
from typing import Any, Dict, Optional, Tuple

import pytest


class StopExecution(RuntimeError):
    """Simula l'eccezione di `st.stop()` durante i test."""


class _QueryParamsStub:
    def __init__(self) -> None:
        self._data: Dict[str, Optional[str]] = {}

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._data.get(key, default)

    def set(self, **entries: Optional[str]) -> None:
        self._data = dict(entries)

    def __getitem__(self, key: str) -> Optional[str]:
        return self._data[key]

    def __setitem__(self, key: str, value: Optional[str]) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        self._data.pop(key, None)


class _ExpanderStub:
    def __enter__(self) -> "_ExpanderStub":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: Dict[str, Any] = {}
        self.query_params = _QueryParamsStub()
        self.success_messages: list[str] = []
        self.error_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.page_links: list[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []

    # UI API -------------------------------------------------------------
    def subheader(self, *args: Any, **kwargs: Any) -> None:
        return None

    def html(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def success(self, message: str) -> None:
        self.success_messages.append(message)

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def page_link(self, *args: Any, **kwargs: Any) -> None:
        self.page_links.append((args, kwargs))

    def link_button(self, *args: Any, **kwargs: Any) -> None:
        return None

    def expander(self, *_args: Any, **_kwargs: Any) -> _ExpanderStub:
        return _ExpanderStub()

    def code(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def stop(self) -> None:
        raise StopExecution()


def _prepare_admin_module(monkeypatch: pytest.MonkeyPatch) -> Tuple[Any, _StreamlitStub]:
    stub = _StreamlitStub()
    sys.modules.pop("streamlit", None)
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    # Stub minimal google modules to satisfy imports at module load
    google_mod = types.ModuleType("google")
    google_auth = types.ModuleType("google.auth")
    google_transport = types.ModuleType("google.auth.transport")
    google_transport.requests = types.SimpleNamespace(Request=object)
    google_auth.transport = google_transport  # type: ignore[attr-defined]
    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2.id_token = types.SimpleNamespace(verify_oauth2_token=lambda *_a, **_k: {})  # type: ignore[attr-defined]
    google_mod.auth = google_auth  # type: ignore[attr-defined]
    google_mod.oauth2 = google_oauth2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", google_transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", google_transport.requests)
    monkeypatch.setitem(sys.modules, "google.oauth2", google_oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.id_token", google_oauth2.id_token)

    import ui.chrome as chrome

    monkeypatch.setattr(chrome, "header", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(chrome, "sidebar", lambda *_a, **_k: None, raising=False)

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8501/admin")
    monkeypatch.setenv("ALLOWED_GOOGLE_DOMAIN", "unisom.it")

    sys.modules.pop("src.ui.pages.admin", None)
    from timmykb.ui.pages import admin

    monkeypatch.setattr(admin, "st", stub, raising=False)
    return admin, stub


def test_oauth_state_single_use(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, st_stub = _prepare_admin_module(monkeypatch)
    assert admin.st is st_stub

    admin._ensure_session()
    state = st_stub.session_state["oauth_state"]
    nonce = st_stub.session_state["oauth_nonce"]
    verifier = st_stub.session_state["oauth_pkce_verifier"]

    monkeypatch.setattr(admin, "_current_timestamp", lambda: 1_000, raising=False)

    def fake_exchange(code: str, *, code_verifier: str) -> Dict[str, Any]:
        assert code == "auth-code"
        assert code_verifier == verifier
        return {"id_token": "token"}

    monkeypatch.setattr(admin, "_exchange_code_for_tokens", fake_exchange, raising=False)
    monkeypatch.setattr(
        admin,
        "_verify_id_token",
        lambda _tok: {"sub": "123", "email": "user@unisom.it", "hd": "unisom.it", "nonce": nonce},
        raising=False,
    )

    with pytest.raises(StopExecution):
        admin._handle_oauth_callback("auth-code", state)

    user = st_stub.session_state["user"]
    assert user["email"] == "user@unisom.it"
    assert user["exp"] == 1_000 + admin.SESSION_TTL_SECONDS
    assert "oauth_state" not in st_stub.session_state
    assert "oauth_nonce" not in st_stub.session_state
    assert "oauth_pkce_verifier" not in st_stub.session_state
    assert st_stub.success_messages[-1].startswith("Accesso effettuato")

    admin._ensure_session()

    with pytest.raises(StopExecution):
        admin._handle_oauth_callback("auth-code", state)
    assert st_stub.error_messages[-1] == "State non valido."
    assert "oauth_state" not in st_stub.session_state


def test_session_ttl_expiration_forces_relogin(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, st_stub = _prepare_admin_module(monkeypatch)

    assert "user" not in st_stub.session_state
    st_stub.session_state.clear()
    st_stub.session_state["user"] = {"email": "user@unisom.it", "exp": 90, "sub": "123", "hd": "unisom.it"}
    assert st_stub.session_state["user"]["exp"] == 90
    monkeypatch.setattr(admin, "_current_timestamp", lambda: 120, raising=False)

    assert admin._session_expired(st_stub.session_state["user"]) is True

    user = admin._enforce_session_ttl()
    assert user is None
    assert "user" not in st_stub.session_state
    assert st_stub.warning_messages[-1].startswith("Sessione scaduta")
    assert "user" not in st_stub.session_state
