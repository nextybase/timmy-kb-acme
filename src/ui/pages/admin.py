# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/admin.py
from __future__ import annotations

import json
import os
import secrets
import time
from importlib import import_module
from typing import Any, Dict, Optional, cast
from urllib.parse import urlencode

import streamlit as st
from google.auth.transport import requests as greq
from google.oauth2 import id_token

# ✨ Coerenza con le altre pagine UI
from ui.chrome import header, sidebar  # vedi home.py per lo stesso schema

# ---------- Chrome coerente ----------
# L'entrypoint imposta page_config; qui solo header+sidebar come in home.py
header(None)
sidebar(None)

# ---------- Config/env ----------
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
GOOGLE_CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
REDIRECT_URI = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()  # es.: http://localhost:8501/admin
ALLOWED_DOMAIN = (os.getenv("ALLOWED_GOOGLE_DOMAIN") or "unisom.it").strip()

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint pubblico OAuth2
ISS_ALLOWED = {"accounts.google.com", "https://accounts.google.com"}


def _ensure_session() -> None:
    st.session_state.setdefault("oauth_state", secrets.token_urlsafe(24))
    st.session_state.setdefault("oauth_nonce", secrets.token_urlsafe(24))


def _build_auth_url(state: str, nonce: str) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email",
        "state": state,
        "nonce": nonce,
        "hd": ALLOWED_DOMAIN,  # hint UX; enforcement sul claim 'hd' dell'ID token
        "include_granted_scopes": "true",
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    data: dict[str, str] = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    requests = cast(Any, import_module("requests"))
    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()
    return cast(Dict[str, Any], response.json())


def _verify_id_token(idt: str) -> Dict[str, Any]:
    info = cast(Dict[str, Any], id_token.verify_oauth2_token(idt, greq.Request(), GOOGLE_CLIENT_ID))
    iss = str(info.get("iss"))
    if iss not in ISS_ALLOWED:
        raise ValueError(f"Issuer non valido: {iss}")
    hd = (info.get("hd") or "").lower()
    email = (info.get("email") or "").lower()
    domain = email.split("@")[-1] if "@" in email else ""
    if (hd != ALLOWED_DOMAIN) and (domain != ALLOWED_DOMAIN):
        raise ValueError("Dominio dell'account non autorizzato")
    return info


def _mask(s: str) -> str:
    return s[:8] + "..." + s[-10:] if s and len(s) > 20 else (s or "∅")


# ---------- UI ----------
st.subheader("Login con Google (dominio autorizzato)")

# Guardie config (mostra diagnosi ma NON interrompe la sidebar)
if not GOOGLE_CLIENT_ID or not REDIRECT_URI:
    st.error("Config mancante: imposta GOOGLE_CLIENT_ID e GOOGLE_REDIRECT_URI.")
    with st.expander("Diagnostica"):
        st.code(
            f"client_id={_mask(GOOGLE_CLIENT_ID)}\nredirect={REDIRECT_URI}\nallowed_domain={ALLOWED_DOMAIN}",
            language="bash",
        )
else:
    _ensure_session()
    qp = st.query_params
    code: Optional[str] = qp.get("code")
    state: Optional[str] = qp.get("state")

    # Callback OAuth
    if code:
        if state != st.session_state.get("oauth_state"):
            st.error("State non valido.")
            st.stop()
        try:
            tokens = _exchange_code_for_tokens(code)
            idinfo = _verify_id_token(tokens["id_token"])
            st.session_state["user"] = {
                "sub": idinfo.get("sub"),
                "email": idinfo.get("email"),
                "hd": idinfo.get("hd"),
                "at": int(time.time()),
            }
            st.success(f"Accesso effettuato: {idinfo.get('email')}")
            st.page_link("src/ui/pages/home.py", label="Vai alla Home", icon="➡️")
            st.stop()
        except Exception as e:
            st.error(f"Autenticazione fallita: {e}")
            st.stop()

    # Schermata iniziale
    login_url = _build_auth_url(st.session_state["oauth_state"], st.session_state["oauth_nonce"])
    st.link_button("Accedi con Google", login_url, width="stretch")

    with st.expander("Diagnostica (locale)"):
        st.code(
            json.dumps(
                {
                    "GOOGLE_CLIENT_ID": _mask(GOOGLE_CLIENT_ID),
                    "GOOGLE_REDIRECT_URI": REDIRECT_URI,
                    "ALLOWED_GOOGLE_DOMAIN": ALLOWED_DOMAIN,
                },
                indent=2,
            ),
            language="json",
        )
