# onboarding_ui.py
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

# -----------------------------------------------------------------------------
# Bootstrap PYTHONPATH per moduli locali (src/*)
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# -----------------------------------------------------------------------------
# Import pipeline (con fallback sicuro)
# -----------------------------------------------------------------------------
try:
    from pipeline.env_utils import compute_redact_flag  # type: ignore
except Exception:  # pragma: no cover
    compute_redact_flag = None  # type: ignore

try:
    from pipeline.logging_utils import get_structured_logger  # type: ignore
except Exception:  # pragma: no cover
    get_structured_logger = None  # type: ignore

# -----------------------------------------------------------------------------
# Import UI/Config helpers (riuso: NIENTE duplicazioni)
# -----------------------------------------------------------------------------
from config_ui.utils import (
    yaml_load,
    yaml_dump,
    ensure_within_and_resolve,
)  # type: ignore
from config_ui.mapping_editor import (  # type: ignore
    load_default_mapping,
    load_tags_reviewed,
    save_tags_reviewed,
    split_mapping,
    build_mapping,
    validate_categories,
)
from config_ui.drive_runner import (  # type: ignore
    build_drive_from_mapping,
    emit_readmes_for_raw,
)

# -----------------------------------------------------------------------------
# Streamlit (UI)
# -----------------------------------------------------------------------------
try:
    import streamlit as st  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "Streamlit non disponibile. Installa le dipendenze UI per eseguire questo file."
    ) from e


# =============================================================================
# Utility locali orchestratore (logging & redazione)
# =============================================================================
def _safe_compute_redact_flag(env: Optional[Dict[str, str]] = None, level: str = "INFO") -> bool:
    """
    Determina se abilitare la redazione log.
    Riuso della funzione repo se presente, fallback minimale altrimenti.
    """
    env = env or dict(os.environ)
    if compute_redact_flag is not None:
        try:
            return bool(compute_redact_flag(env, level))  # type: ignore[arg-type]
        except TypeError:
            return bool(compute_redact_flag(env, level))  # type: ignore[misc]
        except Exception:
            pass
    # Fallback: abilita redazione in prod o se esplicitamente richiesto
    val = env.get("LOG_REDACTION") or env.get("LOG_REDACTED") or ""
    if val.lower() in {"1", "true", "yes", "on"}:
        return True
    if (env.get("ENV") or "").lower() in {"prod", "production"}:
        return True
    return False


def _safe_get_logger(name: str, redact: bool) -> logging.Logger:
    """
    Logger strutturato del repo con `context` se disponibile; altrimenti fallback basicConfig.
    """
    if get_structured_logger is not None:
        try:
            ctx = SimpleNamespace(redact_logs=bool(redact))
            return get_structured_logger(name, context=ctx)  # type: ignore[call-arg]
        except Exception:
            pass
    # Fallback plain
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    return logging.getLogger(name)


def _request_shutdown(log: logging.Logger) -> None:
    """
    Termina il processo Streamlit avviato da terminale.
    Prova con SIGTERM; fallback a os._exit(0) in casi estremi.
    """
    import signal
    try:
        log.info({"event": "ui_shutdown_request"})
        pid = os.getpid()
        os.kill(pid, signal.SIGTERM)
    except Exception:
        os._exit(0)


# =============================================================================
# Componenti UI
# =============================================================================
def _sidebar_context(log: logging.Logger) -> Tuple[str, str]:
    st.sidebar.header("Contesto cliente")
    slug = st.sidebar.text_input(
        "Slug cliente",
        value=st.session_state.get("slug", ""),
        placeholder="es. acme",
        key="inp_slug",
    )
    client_name = st.sidebar.text_input(
        "Nome cliente (opz.)",
        value=st.session_state.get("client_name", ""),
        placeholder="ACME S.p.A.",
        key="inp_client_name",
    )
    # Pulsante CHIUDI UI nella sidebar (colonna destra) sotto gli input
    if st.sidebar.button("Chiudi UI", key="btn_close_ui_sidebar", use_container_width=True):
        st.sidebar.info("Chiusura in corso…")
        _request_shutdown(log)

    st.session_state["slug"] = slug.strip()
    st.session_state["client_name"] = client_name.strip()
    return st.session_state["slug"], st.session_state["client_name"]


def _load_mapping(slug: str) -> Dict[str, Any]:
    """
    Carica il mapping rivisto se esiste, altrimenti default.
    """
    try:
        return load_tags_reviewed(slug)
    except Exception:
        return load_default_mapping()


def _render_config_tab(log: logging.Logger, slug: str, client_name: str) -> None:
    st.subheader("Configurazione (mapping semantico)")
    mapping = _load_mapping(slug)

    # split: NO 'context' in UI (non lo mostriamo per richiesta esplicita)
    cats, reserved = split_mapping(mapping)
    normalize_keys = st.toggle(
        "Normalizza chiavi in kebab-case",
        value=True,
        help="Applica SSoT di normalizzazione",
        key="tgl_norm_keys",
    )
    col1, col2 = st.columns([1, 1])

    with col1:
        st.caption("Panoramica categorie (solo lettura).")
        st.json(cats, expanded=False)

    with col2:
        st.caption("Modifica voci (una alla volta).")
        # Accordion per-voce con key UNIVOCHE
        for idx, cat_key in enumerate(sorted(cats.keys(), key=str)):
            meta = cats.get(cat_key, {})
            with st.expander(cat_key, expanded=False, key=f"exp_cat_{idx}_{cat_key}"):
                amb = st.text_input(
                    f"Ambito — {cat_key}",
                    value=str(meta.get("ambito", "")),
                    key=f"amb_{idx}_{cat_key}",
                )
                desc = st.text_area(
                    f"Descrizione — {cat_key}",
                    value=str(meta.get("descrizione", "")),
                    height=120,
                    key=f"desc_{idx}_{cat_key}",
                )
                examples_str = "\n".join([str(x) for x in (meta.get("esempio") or [])])
                ex = st.text_area(
                    f"Esempi (uno per riga) — {cat_key}",
                    value=examples_str,
                    height=120,
                    key=f"ex_{idx}_{cat_key}",
                )

                if st.button(
                    f"Salva “{cat_key}”",
                    key=f"btn_save_cat_{idx}_{cat_key}",
                    use_container_width=True,
                ):
                    try:
                        # aggiorna solo questa voce
                        new_cats = dict(cats)
                        new_cats[cat_key] = {
                            "ambito": amb.strip(),
                            "descrizione": desc.strip(),
                            "esempio": [ln.strip() for ln in ex.splitlines() if ln.strip()],
                        }
                        err = validate_categories(new_cats, normalize_keys=normalize_keys)
                        if err:
                            st.error(f"Errore: {err}")
                        else:
                            new_map = build_mapping(
                                new_cats,
                                reserved,
                                slug=slug,
                                client_name=client_name,
                                normalize_keys=normalize_keys,
                            )
                            path = save_tags_reviewed(slug, new_map)
                            log.info(
                                {
                                    "event": "tags_reviewed_saved_item",
                                    "slug": slug,
                                    "cat": cat_key,
                                    "path": str(path),
                                }
                            )
                            st.success(f"Salvata la voce: {cat_key}")
                            try:
                                st.rerun()
                            except Exception:
                                pass
                    except Exception as e:
                        st.exception(e)

        st.caption("Suggerimento: usa il pulsante Salva dentro ogni voce per applicare modifiche puntuali.")

    # Azioni
    colSx, colDx = st.columns([1, 1])
    with colSx:
        if st.button("Valida mapping", key="btn_validate_mapping", use_container_width=True):
            err = validate_categories(cats, normalize_keys=normalize_keys)
            if err:
                st.error(f"Errore: {err}")
            else:
                st.success("Mapping valido.")
    with colDx:
        if st.button("Salva mapping rivisto", key="btn_save_mapping_all", type="primary", use_container_width=True):
            try:
                new_map = build_mapping(
                    cats, reserved, slug=slug, client_name=client_name, normalize_keys=normalize_keys
                )
                path = save_tags_reviewed(slug, new_map)
                st.success(f"Salvato: {path}")
                log.info({"event": "tags_reviewed_saved_all", "slug": slug, "path": str(path)})
            except Exception as e:
                st.exception(e)


def _render_drive_tab(log: logging.Logger, slug: str) -> None:
    st.subheader("Drive")
    st.caption(
        "Crea la struttura su Drive a partire dal mapping rivisto e genera i README nelle sottocartelle di `raw/`."
    )

    colA, colB = st.columns([1, 1], gap="large")

    with colA:
        if st.button("1) Crea/aggiorna struttura Drive", key="btn_drive_create", use_container_width=True):
            try:
                ids = build_drive_from_mapping(slug=slug, client_name=st.session_state.get("client_name", ""))
                st.success(f"Struttura creata: {ids}")
                log.info({"event": "drive_structure_created", "slug": slug, "ids": ids})
            except Exception as e:
                st.exception(e)
    with colB:
        if st.button("2) Genera README in raw/", key="btn_drive_readmes", type="primary", use_container_width=True):
            try:
                result = emit_readmes_for_raw(slug=slug)
                st.success(f"README creati: {len(result)}")
                log.info({"event": "raw_readmes_uploaded", "slug": slug, "count": len(result)})
            except Exception as e:
                st.exception(e)

    st.divider()
    st.caption("Nota: richiede variabili d’ambiente valide (es. DRIVE_ID) e credenziali configurate.")


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    st.set_page_config(page_title="NeXT — Onboarding UI", layout="wide")
    redact = _safe_compute_redact_flag()
    log = _safe_get_logger("onboarding_ui", redact)

    st.title("NeXT — Onboarding UI")
    st.write("Orchestratore UI per configurazione e provisioning struttura iniziale della Knowledge Base.")

    slug, client_name = _sidebar_context(log)
    if not slug or not client_name:
        st.warning("Inserisci **slug** e **nome cliente** per procedere.")
        return

    tabs = st.tabs(["Configurazione", "Drive"])
    with tabs[0]:
        _render_config_tab(log, slug, client_name)
    with tabs[1]:
        _render_drive_tab(log, slug)


if __name__ == "__main__":
    main()
