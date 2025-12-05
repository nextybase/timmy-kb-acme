# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/admin.py
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import socket
import subprocess
import time
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast
from urllib.parse import urlencode

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

try:
    from google.auth.transport import requests as greq  # type: ignore[import]
    from google.oauth2 import id_token  # type: ignore[import]
except Exception:  # pragma: no cover - ambiente senza google-auth
    greq = None
    id_token = None

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings

# Coerenza con le altre pagine UI
from ui.chrome import header, sidebar  # vedi home.py per lo stesso schema

# ---------- Chrome coerente ----------
# L'entrypoint imposta page_config; qui solo header+sidebar come in home.py
header(None, title="Admin", subtitle="Gestione autenticazione e configurazioni amministrative.")
sidebar(None)

REPO_ROOT = Path(__file__).resolve().parents[3]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint pubblico OAuth2
ISS_ALLOWED = {"accounts.google.com", "https://accounts.google.com"}
SESSION_TTL_SECONDS = 3600


@lru_cache(maxsize=1)
def _load_settings() -> Optional[Settings]:
    try:
        return Settings.load(REPO_ROOT)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _oauth_env() -> Dict[str, str]:
    """Carica valori OAuth dai segreti/ENV in modo lazy e memorizzato."""
    client_id = (get_env_var("GOOGLE_CLIENT_ID", default="") or "").strip()
    client_secret = (get_env_var("GOOGLE_CLIENT_SECRET", default="") or "").strip()
    redirect_uri = (get_env_var("GOOGLE_REDIRECT_URI", default="") or "").strip()
    allowed_domain = (get_env_var("ALLOWED_GOOGLE_DOMAIN", default="unisom.it") or "unisom.it").strip()
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "allowed_domain": allowed_domain,
    }


def _current_timestamp() -> int:
    return int(time.time())


def _generate_pkce_verifier() -> str:
    # Lunghezza consigliata 43-128 caratteri
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _ensure_session() -> None:
    st.session_state.setdefault("oauth_state", secrets.token_urlsafe(24))
    st.session_state.setdefault("oauth_nonce", secrets.token_urlsafe(24))
    st.session_state.setdefault("oauth_pkce_verifier", _generate_pkce_verifier())


def _pop_oauth_artifacts() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    state = st.session_state.pop("oauth_state", None)
    nonce = st.session_state.pop("oauth_nonce", None)
    verifier = st.session_state.pop("oauth_pkce_verifier", None)
    return state, nonce, verifier


def _build_auth_url(state: str, nonce: str) -> str:
    cfg = _oauth_env()
    verifier = cast(str, st.session_state.get("oauth_pkce_verifier") or _generate_pkce_verifier())
    st.session_state["oauth_pkce_verifier"] = verifier
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": "openid email",
        "state": state,
        "nonce": nonce,
        "hd": cfg["allowed_domain"],  # hint UX; enforcement sul claim 'hd' dell'ID token
        "include_granted_scopes": "true",
        "prompt": "select_account",
        "access_type": "online",
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _exchange_code_for_tokens(code: str, *, code_verifier: str) -> Dict[str, Any]:
    cfg = _oauth_env()
    data: dict[str, str] = {
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    requests = cast(Any, import_module("requests"))
    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()
    return cast(Dict[str, Any], response.json())


def _verify_id_token(idt: str) -> Dict[str, Any]:
    if id_token is None or greq is None:
        # Mancano le librerie Google Auth: segnaliamo come errore di configurazione
        raise ConfigError(
            "Librerie Google Auth non disponibili. " "Installa il pacchetto 'google-auth' per usare il login Admin."
        )

    cfg = _oauth_env()
    info = cast(
        Dict[str, Any],
        id_token.verify_oauth2_token(idt, greq.Request(), cfg["client_id"]),  # type: ignore[union-attr]
    )
    iss = str(info.get("iss"))
    if iss not in ISS_ALLOWED:
        raise ConfigError(f"Issuer non valido: {iss}")
    hd = (info.get("hd") or "").lower()
    email = (info.get("email") or "").lower()
    domain = email.split("@")[-1] if "@" in email else ""
    allowed_domain = cfg["allowed_domain"].lower()
    if (hd != allowed_domain) and (domain != allowed_domain):
        # Dominio non autorizzato: errore di permessi lato UI
        raise PermissionError("Dominio dell'account non autorizzato")
    return info


def _session_expired(user: Dict[str, Any]) -> bool:
    try:
        exp = int(user.get("exp", 0))
    except Exception:
        exp = 0
    if exp <= 0:
        return False
    return _current_timestamp() > exp


def _enforce_session_ttl() -> Optional[Dict[str, Any]]:
    user = st.session_state.get("user")
    if not isinstance(user, dict):
        st.session_state.pop("user", None)
        return None
    if _session_expired(user):
        st.session_state.pop("user", None)
        st.warning("Sessione scaduta. Effettua nuovamente il login.")
        return None
    return cast(Dict[str, Any], user)


# ---------- Osservabilità (Admin) ----------
def _docker_ready() -> bool:
    """True se Docker CLI è presente e l'engine risponde."""
    docker_exe = shutil.which("docker")
    if not docker_exe:
        return False
    try:
        subprocess.run(  # noqa: S603
            [docker_exe, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
        )  # noqa: S603,S607
        return True
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    """True se localhost:port è aperta."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _start_observability_stack() -> tuple[bool, str]:
    """Avvia Loki+Promtail+Grafana via docker compose usando il .env in root."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return False, f"File .env non trovato in {env_path}"
    compose_cmd = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "-f",
        str(REPO_ROOT / "observability" / "docker-compose.yaml"),
        "up",
        "-d",
    ]
    try:
        result = subprocess.run(  # noqa: S603
            compose_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )  # noqa: S603,S607
        if result.returncode == 0:
            return True, "Stack osservabilità avviato."
        return False, result.stderr.strip() or "Compose non riuscito."
    except subprocess.TimeoutExpired:
        return False, "Timeout avvio docker compose (120s)."
    except Exception as exc:
        return False, f"Errore avvio compose: {exc}"


def _stop_observability_stack() -> tuple[bool, str]:
    """Ferma lo stack osservabilità (docker compose down)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return False, f"File .env non trovato in {env_path}"
    compose_cmd = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "-f",
        str(REPO_ROOT / "observability" / "docker-compose.yaml"),
        "down",
    ]
    try:
        result = subprocess.run(  # noqa: S603
            compose_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )  # noqa: S603,S607
        if result.returncode == 0:
            return True, "Stack osservabilità arrestato."
        return False, result.stderr.strip() or "Compose down non riuscito."
    except subprocess.TimeoutExpired:
        return False, "Timeout durante docker compose down (120s)."
    except Exception as exc:
        return False, f"Errore arresto compose: {exc}"


def _render_admin_panel() -> None:
    st.subheader("Amministrazione")
    st.caption("Controlli stack osservabilità (Loki + Promtail + Grafana)")
    divider = getattr(st, "divider", None)
    if callable(divider):
        divider()

    docker_ok = _docker_ready()
    if not docker_ok:
        st.warning("Docker non risulta attivo. Avvialo per usare Grafana.")

    grafana_live = _port_in_use(3000)
    expected_running = bool(st.session_state.get("obs_expected_running", False))
    display_running = expected_running or grafana_live

    col_start, col_stop = st.columns(2)

    with col_start:
        if st.button(
            "Avvia stack Grafana (Loki+Promtail)",
            key="btn_obs_start",
            disabled=not docker_ok,
            help="Esegue: docker compose --env-file ./.env -f observability/docker-compose.yaml up -d",
        ):
            ok, msg = _start_observability_stack()
            if ok:
                st.success(msg)
                st.session_state["obs_expected_running"] = True
                expected_running = True
                display_running = True
            else:
                st.error(msg)

    with col_stop:
        if st.button(
            "Arresta stack Grafana (docker compose down)",
            key="btn_obs_stop",
            disabled=not display_running,
            help="Esegue: docker compose --env-file ./.env -f observability/docker-compose.yaml down",
        ):
            ok, msg = _stop_observability_stack()
            if ok:
                st.success(msg)
                st.session_state["obs_expected_running"] = False
                expected_running = False
                display_running = False
                grafana_live = False
            else:
                st.error(msg)

    st.link_button(
        "Apri Grafana (localhost:3000)",
        url="http://localhost:3000",
        disabled=not grafana_live,
        help="Si abilita quando Grafana risponde sulla porta 3000.",
    )

    if expected_running and not grafana_live:
        st.info("Stack avviato: attendo risposta di Grafana su http://localhost:3000 ...")


def _handle_oauth_callback(code: Optional[str], state: Optional[str]) -> None:
    if not code:
        return
    expected_state, expected_nonce, code_verifier = _pop_oauth_artifacts()
    if not expected_state or state != expected_state:
        st.error("State non valido.")
        st.stop()
    if not code_verifier:
        st.error("PKCE verifier mancante.")
        st.stop()
    try:
        verifier = cast(str, code_verifier)
        tokens = _exchange_code_for_tokens(code, code_verifier=verifier)
        idinfo = _verify_id_token(tokens["id_token"])
    except Exception as exc:
        st.error(f"Autenticazione fallita: {exc}")
        st.stop()
    if expected_nonce and str(idinfo.get("nonce") or "") != expected_nonce:
        st.error("Nonce non valido.")
        st.stop()
    now = _current_timestamp()
    st.session_state["user"] = {
        "sub": idinfo.get("sub"),
        "email": idinfo.get("email"),
        "hd": idinfo.get("hd"),
        "at": now,
        "exp": now + SESSION_TTL_SECONDS,
    }
    st.success(f"Accesso effettuato: {idinfo.get('email')}")
    _render_admin_panel()
    st.stop()


def _mask(s: str) -> str:
    return s[:8] + "..." + s[-10:] if s and len(s) > 20 else (s or "...")


# ---------- UI ----------
st.subheader("Login con Google (dominio autorizzato)")

# Se le librerie Google Auth mancano, rendiamo la pagina import-safe e autoesplicativa.
if id_token is None or greq is None:
    st.error(
        "Librerie Google Auth non disponibili.\n\n"
        "Installa il pacchetto `google-auth` nel venv per abilitare il login Admin."
    )
else:
    # Guardie config (mostra diagnosi ma NON interrompe la sidebar)
    cfg = _oauth_env()
    if not cfg["client_id"] or not cfg["redirect_uri"]:
        st.error("Config mancante: imposta GOOGLE_CLIENT_ID e GOOGLE_REDIRECT_URI.")
        with st.expander("Diagnostica"):
            st.code(
                f"client_id={_mask(cfg['client_id'])}\nredirect={cfg['redirect_uri']}\n"
                f"allowed_domain={cfg['allowed_domain']}",
                language="bash",
            )
    else:
        user = _enforce_session_ttl()
        if user:
            st.success(f"Accesso già attivo: {user.get('email')}")
            _render_admin_panel()
            st.stop()

        _ensure_session()
        qp = st.query_params
        code: Optional[str] = qp.get("code")
        state: Optional[str] = qp.get("state")

        _handle_oauth_callback(code, state)

        # Schermata iniziale
        login_url = _build_auth_url(st.session_state["oauth_state"], st.session_state["oauth_nonce"])
        st.link_button("Accedi con Google", login_url, width="stretch")

        # Modalità locale opzionale: espone il pannello anche senza login
        settings_obj = _load_settings()
        if settings_obj and settings_obj.ui_admin_local_mode:
            st.info(
                "Modalità locale attiva: pannello osservabilità disponibile senza login. "
                "Ricorda di valorizzare le credenziali Grafana in `.env`."
            )
            _render_admin_panel()
            st.stop()

        with st.expander("Diagnostica (locale)"):
            st.code(
                json.dumps(
                    {
                        "GOOGLE_CLIENT_ID": _mask(cfg["client_id"]),
                        "GOOGLE_REDIRECT_URI": cfg["redirect_uri"],
                        "ALLOWED_GOOGLE_DOMAIN": cfg["allowed_domain"],
                    },
                    indent=2,
                ),
                language="json",
            )
