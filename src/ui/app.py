from __future__ import annotations

# Nessun side-effect a import time: bootstrap e tutti gli import vivono in main().


def main() -> None:
    # =========================================================================
    # Bootstrap path (posticipato per evitare E402 e side-effects)
    # =========================================================================
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    SRC = ROOT / "src"
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

    # =========================================================================
    # Import locali (lazy) – dopo bootstrap
    # =========================================================================
    import logging
    import os
    import subprocess
    from types import SimpleNamespace
    from typing import Any, Dict, Optional, cast

    import streamlit as st

    from pipeline.config_utils import (
        bump_n_ver_if_needed,
        get_client_config,
        set_data_ver_today,
        update_config_with_drive_ids,
    )
    from pipeline.context import ClientContext
    from pipeline.env_utils import compute_redact_flag
    from pipeline.logging_utils import get_structured_logger  # fix import
    from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard

    # Semantica API (niente get_paths: i path vengono dal ClientContext)
    from semantic.api import convert_markdown as sem_convert
    from semantic.api import enrich_frontmatter as sem_enrich
    from semantic.api import load_reviewed_vocab as sem_load_vocab
    from semantic.api import write_summary_and_readme as sem_write_md

    # UI/Config helpers
    from ui.components.mapping_editor import (
        build_mapping,
        load_default_mapping,
        load_tags_reviewed,
        save_tags_reviewed,
        split_mapping,
        validate_categories,
    )

    # Landing (modulo esterno)
    from ui.landing_slug import render_landing_slug
    from ui.services.drive_runner import build_drive_from_mapping, download_raw_from_drive, emit_readmes_for_raw
    from ui.tabs.finance import render_finance_tab
    from ui.tabs.preview import render_preview_controls

    # =========================================================================
    # Helpers (chiudono su import locali)
    # =========================================================================
    def _safe_compute_redact_flag(env: Optional[Dict[str, str]] = None, level: str = "INFO") -> bool:
        env = env or dict(os.environ)
        try:
            return bool(compute_redact_flag(env, level))
        except Exception:
            val = (env.get("LOG_REDACTION") or env.get("LOG_REDACTED") or "").lower()
            if val in {"1", "true", "yes", "on"}:
                return True
            return (env.get("ENV") or "").lower() in {"prod", "production"}

    def _safe_get_logger(name: str, redact: bool) -> logging.Logger:
        try:
            ctx = SimpleNamespace(redact_logs=bool(redact))
            logger_obj = get_structured_logger(name, context=ctx)
            return cast(logging.Logger, logger_obj)
        except Exception:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(levelname)s: %(message)s",
            )
            return logging.getLogger(name)

    def _request_shutdown(log: logging.Logger) -> None:
        import signal

        try:
            log.info({"event": "ui_shutdown_request"})
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    def _norm_str(val: Optional[str]) -> str:
        return val.strip() if isinstance(val, str) else ""

    def _safe_streamlit_rerun() -> None:
        fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _ensure_context(slug: str, log: logging.Logger) -> ClientContext:
        # Nessun prompt; env non obbligatorio per operazioni locali
        return ClientContext.load(
            slug=slug,
            interactive=False,
            require_env=False,
            run_id=None,
        )

    def _mark_modified_and_bump_once(
        slug: str, log: logging.Logger, *, context: Optional[ClientContext] = None
    ) -> None:
        try:
            if (not bool(st.session_state.get("bumped"))) and bump_n_ver_if_needed is not None:
                ctx = context if context is not None else _ensure_context(slug, log)
                bump_n_ver_if_needed(ctx, log)
                st.session_state["bumped"] = True
            st.session_state["modified"] = True
        except Exception:
            pass

    # =========================================================================
    # Sezioni UI (modulari)
    # =========================================================================
    def _render_config_tab(log: logging.Logger, slug: str, client_name: str) -> None:
        st.subheader("Configurazione (mapping semantico)")
        try:
            mapping = load_tags_reviewed(slug)
        except Exception:
            mapping = load_default_mapping()

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
            for idx, cat_key in enumerate(sorted(cats.keys(), key=str)):
                meta = cats.get(cat_key, {})
                with st.expander(cat_key, expanded=False):
                    amb = st.text_input(
                        f"Ambito - {cat_key}",
                        value=str(meta.get("ambito", "")),
                        key=f"amb_{idx}_{cat_key}",
                    )
                    desc = st.text_area(
                        f"Descrizione - {cat_key}",
                        value=str(meta.get("descrizione", "")),
                        height=120,
                        key=f"desc_{idx}_{cat_key}",
                    )
                    examples_str = "\n".join([str(x) for x in (meta.get("esempio") or [])])
                    ex = st.text_area(
                        f"Esempi (uno per riga) - {cat_key}",
                        value=examples_str,
                        height=120,
                        key=f"ex_{idx}_{cat_key}",
                    )

                    if st.button(
                        f"Salva {cat_key}",
                        key=f"btn_save_cat_{idx}_{cat_key}",
                        use_container_width=True,
                    ):
                        try:
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
                                _mark_modified_and_bump_once(slug, log)
                                st.success(f"Salvata la voce: {cat_key}")
                                _safe_streamlit_rerun()
                        except Exception as e:
                            st.exception(e)

            st.caption(("Suggerimento: usa il pulsante Salva dentro ogni voce per applicare modifiche puntuali."))

        colSx, colDx = st.columns([1, 1])
        with colSx:
            if st.button("Valida mapping", key="btn_validate_mapping", use_container_width=True):
                err = validate_categories(cats, normalize_keys=normalize_keys)
                st.success("Mapping valido.") if not err else st.error(f"Errore: {err}")
        with colDx:
            if st.button(
                "Salva mapping rivisto",
                key="btn_save_mapping_all",
                type="primary",
                use_container_width=True,
            ):
                try:
                    new_map = build_mapping(
                        cats,
                        reserved,
                        slug=slug,
                        client_name=client_name,
                        normalize_keys=normalize_keys,
                    )
                    path = save_tags_reviewed(slug, new_map)
                    st.success(f"Salvato: {path}")
                    log.info({"event": "tags_reviewed_saved_all", "slug": slug, "path": str(path)})
                    _mark_modified_and_bump_once(slug, log)
                except Exception as e:
                    st.exception(e)

    def _render_drive_tab(log: logging.Logger, slug: str) -> None:
        st.subheader("Drive")
        st.caption(
            "Crea la struttura su Drive a partire dal mapping rivisto e genera i README "
            "nelle sottocartelle di `raw/`."
        )

        # Verifica dipendenze Drive
        try:
            from googleapiclient.http import MediaIoBaseDownload as _chk

            _ = _chk
            dep_ok = True
        except Exception:
            dep_ok = False

        if not dep_ok:
            st.warning(
                "Funzionalità Drive non disponibili: dipendenza mancante "
                "`google-api-python-client`.\n"
                "Installa il pacchetto e riavvia la UI. Esempio: "
                "`pip install google-api-python-client`.",
                icon="⚠️",
            )
            return

        # Preflight credenziali
        with st.expander("Preflight Drive", expanded=False):
            saf = os.getenv("SERVICE_ACCOUNT_FILE") or ""
            did = os.getenv("DRIVE_ID") or ""

            def _mask_path(p: str) -> str:
                from pathlib import Path as _P

                try:
                    return _P(p).name if p else "(unset)"
                except Exception:
                    return "(invalid)"

            def _mask_id(s: str) -> str:
                return (s[:6] + " …") if s else "(unset)"

            st.write(f"SERVICE_ACCOUNT_FILE: {_mask_path(saf)}")
            st.write(f"DRIVE_ID: {_mask_id(did)}")

            if st.button("Verifica credenziali Drive", key="btn_drive_preflight", use_container_width=True):
                try:
                    from pipeline.drive_utils import get_drive_service

                    ctx = ClientContext.load(slug=slug, interactive=False, require_env=True, run_id=None)
                    svc = get_drive_service(ctx)
                    _ = svc.about().get(fields="user").execute()
                    st.success("OK: credenziali e accesso Drive verificati.")
                except Exception as e:
                    st.exception(e)

        colA, colB = st.columns([1, 1], gap="large")

        with colA:
            if st.button(
                "1) Crea/aggiorna struttura Drive",
                key="btn_drive_create",
                use_container_width=True,
            ):
                try:
                    prog = st.progress(0)
                    status = st.empty()

                    def _cb(step: int, total: int, label: str) -> None:
                        pct = int(step * 100 / max(total, 1))
                        prog.progress(pct)
                        status.markdown(f"{pct}% - {label}")

                    ids = build_drive_from_mapping(
                        slug=slug,
                        client_name=st.session_state.get("client_name", ""),
                        progress=_cb,
                    )
                    st.success(f"Struttura creata: {ids}")
                    log.info({"event": "drive_structure_created", "slug": slug, "ids": ids})
                except FileNotFoundError as e:
                    st.error(
                        "Mapping non trovato per questo cliente. Apri la tab 'Configurazione', "
                        "verifica/modifica il mapping e premi 'Salva mapping rivisto', poi riprova."
                    )
                    st.caption(f"Dettagli: {e}")
                except Exception as e:
                    st.exception(e)
        with colB:
            if st.button(
                "2) Genera README in raw/",
                key="btn_drive_readmes",
                type="primary",
                use_container_width=True,
            ):
                try:
                    result = emit_readmes_for_raw(slug=slug, ensure_structure=True)
                    st.success(f"README creati: {len(result)}")
                    log.info({"event": "raw_readmes_uploaded", "slug": slug, "count": len(result)})
                    st.session_state["drive_readmes_done"] = True
                    _mark_modified_and_bump_once(slug, log)
                except FileNotFoundError as e:
                    st.error(
                        "Mapping non trovato per questo cliente. Apri la tab 'Configurazione', "
                        "verifica/modifica il mapping e premi 'Salva mapping rivisto', poi riprova."
                    )
                    st.caption(f"Dettagli: {e}")
                except Exception as e:
                    st.exception(e)

        # Download PDF → raw/ (solo dopo README)
        if st.session_state.get("drive_readmes_done"):
            st.markdown("---")
            st.subheader("Download contenuti su raw/")
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button(
                    "Scarica PDF da Drive in raw/",
                    key="btn_drive_download_raw",
                    use_container_width=True,
                ):
                    if download_raw_from_drive is None:
                        st.error(("Funzione di download non disponibile: aggiornare 'ui.services.drive_runner'."))
                    else:
                        try:
                            prog = st.progress(0)
                            status = st.empty()
                            try:
                                from ui.services.drive_runner import download_raw_from_drive_with_progress

                                def _pcb(done: int, total: int, label: str) -> None:
                                    pct = int((done * 100) / max(total, 1))
                                    prog.progress(pct)
                                    status.markdown(f"{pct}% - {label}")

                                res = download_raw_from_drive_with_progress(slug=slug, on_progress=_pcb)
                            except Exception:
                                res = download_raw_from_drive(slug=slug)
                            count = len(res) if hasattr(res, "__len__") else None
                            msg_tail = f" ({count} file)" if count is not None else ""
                            st.success(f"Download completato{msg_tail}.")
                            log.info({"event": "drive_raw_downloaded", "slug": slug, "count": count})
                            st.session_state["raw_downloaded"] = True
                            st.session_state["raw_ready"] = True
                            _safe_streamlit_rerun()
                        except Exception as e:
                            st.exception(e)
                st.markdown("")
                if st.button(
                    "Rileva PDF in raw/",
                    key="btn_drive_detect_raw_ready",
                    use_container_width=True,
                ):
                    try:
                        ctx = _ensure_context(slug, log)
                        raw_dir = getattr(ctx, "raw_dir", None)
                        # --- base_dir sicuro (no Optional / None) ---
                        has_pdfs = any(raw_dir.rglob("*.pdf")) if (raw_dir and raw_dir.exists()) else False
                        has_csv = False
                        base_dir_opt = getattr(ctx, "base_dir", None)
                        if raw_dir and raw_dir.exists():
                            base_dir_safe = raw_dir.parent
                        elif isinstance(base_dir_opt, Path):
                            base_dir_safe = base_dir_opt
                        else:
                            base_dir_safe = None
                        if isinstance(base_dir_safe, Path):
                            has_csv = (base_dir_safe / "semantic" / "tags_raw.csv").exists()
                        # ------------------------------------------
                        st.session_state["raw_ready"] = bool(has_pdfs or has_csv)
                        st.success(
                            "Rilevazione completata: "
                            + (
                                "PDF trovati o CSV presente."
                                if st.session_state["raw_ready"]
                                else "nessun PDF rilevato."
                            )
                        )
                        _safe_streamlit_rerun()
                    except Exception as e:
                        st.exception(e)
            with c2:
                st.write(
                    "La struttura delle cartelle è stata creata su Drive; popolare i contenuti "
                    "seguendo le indicazioni del README presente in ogni cartella per proseguire."
                )

    def _render_semantic_tab(log: logging.Logger, slug: str) -> None:
        st.subheader("Semantica (RAW → BOOK)")
        st.caption(
            "Converte i PDF in Markdown, arricchisce i frontmatter e genera README/SUMMARY. "
            "Preview Docker opzionale."
        )

        if any(x is None for x in (sem_convert, sem_enrich, sem_write_md, sem_load_vocab)):
            st.error("Modulo semantic.api non disponibile o import parziale. Verificare l'ambiente.")
            return

        try:
            context = _ensure_context(slug, log)
        except Exception as e:
            st.exception(e)
            return

        colA, colB = st.columns([1, 1], gap="large")

        with colA:
            st.markdown("<div class='next-card'>", unsafe_allow_html=True)
            st.markdown("**1) Conversione RAW → BOOK**")
            st.caption("Converte i PDF in Markdown (cartella book/).")
            if st.button("Converti PDF in Markdown", key="btn_sem_convert", use_container_width=True):
                try:
                    mds = sem_convert(context, log, slug=slug)
                    st.success(f"OK. File Markdown in book/: {len(mds)}")
                    log.info(
                        {
                            "event": "semantic_convert_done",
                            "slug": slug,
                            "run_id": st.session_state.get("run_id"),
                            "md_count": len(mds),
                        }
                    )
                    _mark_modified_and_bump_once(slug, log, context=context)
                except Exception as e:
                    st.exception(e)
            st.markdown("</div>", unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("**2) Arricchisci frontmatter**")
                st.caption("Arricchisce i metadati con tag canonici (SQLite).")
                if st.button(
                    "Arricchisci con tag canonici (SQLite)",
                    key="btn_sem_enrich",
                    use_container_width=True,
                ):
                    try:
                        # Usa il base_dir reale dal ClientContext (override inclusi)
                        base_dir_opt = getattr(context, "base_dir", None)
                        raw_dir_opt = getattr(context, "raw_dir", None)
                        if isinstance(base_dir_opt, Path):
                            base_dir_safe = base_dir_opt
                        elif isinstance(raw_dir_opt, Path):
                            base_dir_safe = raw_dir_opt.parent
                        else:
                            base_dir_safe = None
                        if base_dir_safe is None:
                            st.error("base_dir non disponibile nel contesto.")
                        else:
                            vocab = sem_load_vocab(base_dir_safe, log)
                            touched = sem_enrich(context, log, vocab, slug=slug)
                            st.success(f"OK. Frontmatter aggiornati: {len(touched)}")
                            log.info(
                                {
                                    "event": "semantic_enrich_done",
                                    "slug": slug,
                                    "run_id": st.session_state.get("run_id"),
                                    "touched": len(touched),
                                }
                            )
                            _mark_modified_and_bump_once(slug, log, context=context)
                    except Exception as e:
                        st.exception(e)

        with colB:
            with st.container(border=True):
                st.markdown("**3) README/SUMMARY**")
                st.caption("Prepara e valida README.md e SUMMARY.md.")
                if st.button(
                    "Genera/valida README & SUMMARY",
                    key="btn_sem_write_md",
                    use_container_width=True,
                ):
                    try:
                        sem_write_md(context, log, slug=slug)
                        st.success("OK. README.md e SUMMARY.md pronti.")
                        log.info(
                            {
                                "event": "semantic_write_md_done",
                                "slug": slug,
                                "run_id": st.session_state.get("run_id"),
                            }
                        )
                        _mark_modified_and_bump_once(slug, log, context=context)
                    except Exception as e:
                        st.exception(e)

            # Preview (modulo estratto)
            render_preview_controls(st=st, context=context, log=log, slug=slug)

        st.divider()
        st.caption(
            "Nota: questo step **non** usa Google Drive né esegue push su GitHub; "
            "lavora su disco locale ed espone una preview."
        )

    # =========================================================================
    # Page config + stile (nessuna riga >120)
    # =========================================================================
    try:
        _fav = ROOT / "assets" / "ico-next.png"
        if _fav.exists():
            st.set_page_config(
                page_title="NeXT - Onboarding UI",
                layout="wide",
                page_icon=str(_fav),
            )
        else:
            st.set_page_config(page_title="NeXT - Onboarding UI", layout="wide")
    except Exception:
        st.set_page_config(page_title="NeXT - Onboarding UI", layout="wide")

    st.markdown(
        """
        <style>
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stButton > button {
            background: #F2B400 !important;
            color: #111827 !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            border: 1px solid #e5e7eb !important;
        }
        .stButton > button:hover {
            filter: brightness(0.98);
        }
        .next-card {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 16px 18px;
            background: #ffffff;
        }
        .pill {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 600;
            border: 1px solid #f5d98b;
        }
        .pill.off {
            background: #FEF3C7;
            color: #6B7280;
        }
        .pill.on  {
            background: #FDE68A;
            color: #1F2937;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"] > label {
            display: block;
            padding: 8px 12px;
            border-radius: 10px;
            color: #111827;
            cursor: pointer;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            font-weight: 600;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"] > label:hover {
            background: #FDF6B2;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"] > label > div[role="radio"] {
            display: none;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"]
        > label:has(div[role="radio"][aria-checked="true"]) {
            background: #FDE68A;
            border: 1px solid #f5d98b;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"]
        div[role="radiogroup"]
        > label:has(div[role="radio"][aria-checked="true"])
        div[role="radio"][aria-checked="true"] {
            background: #FDE68A;
            border: 1px solid #f5d98b;
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    redact = _safe_compute_redact_flag()
    log = _safe_get_logger("onboarding_ui", redact)

    # run_id per correlazione log UI
    try:
        import uuid as _uuid

        if not st.session_state.get("run_id"):
            st.session_state["run_id"] = _uuid.uuid4().hex
    except Exception:
        pass

    # Flag di sessione per versioning
    st.session_state.setdefault("modified", False)
    st.session_state.setdefault("bumped", False)

    # =========================================================================
    # Landing (gating iniziale)
    # =========================================================================
    if not st.session_state.get("client_locked", False):
        locked, _, _ = render_landing_slug(log)
        top_l, top_r = st.columns([4, 1])
        with top_r:
            if st.button(
                "Esci",
                key="btn_exit_landing",
                help="Chiude l'interfaccia Streamlit e termina il processo.",
                use_container_width=True,
            ):
                try:
                    log.info({"event": "ui_exit_requested", "slug": st.session_state.get("slug", "-")})
                except Exception:
                    pass
                _request_shutdown(log)
        if not locked:
            return  # Finché non è lockato, non mostrare altro

    # =========================================================================
    # UI completa (sidebar + contenuto)
    # =========================================================================
    slug = cast(str, st.session_state.get("slug", ""))
    client_name = cast(str, st.session_state.get("client_name", ""))

    st.session_state["sidebar_active"] = False
    if st.session_state.get("client_locked", False):
        with st.sidebar:
            st.session_state["sidebar_active"] = True
            # Branding (silenzioso se assente)
            try:
                _logo = ROOT / "assets" / "next-logo.png"
                if _logo.exists():
                    import base64 as _b64

                    logo_path = ensure_within_and_resolve(ROOT, _logo)
                    with open_for_read_bytes_selfguard(logo_path) as logo_file:
                        _data = logo_file.read()
                    _b64s = _b64.b64encode(_data).decode("ascii")
                    st.markdown(
                        "<img src='data:image/png;base64,{data}' alt='NeXT' "
                        "style='width:100%;height:auto;display:block;' />".format(data=_b64s),
                        unsafe_allow_html=True,
                    )
            except Exception:
                pass

            # Menù (aggiunge Finanza se cliente lockato)
            st.subheader("Menù")
            _menu_items = ["Configurazione", "Drive"]
            if st.session_state.get("client_locked"):
                _menu_items.append("Finanza")
            _menu_items += ["Semantica", "Preview"]

            _current = cast(str, st.session_state.get("active_section") or "Configurazione")
            try:
                _default_index = _menu_items.index(_current) if _current in _menu_items else 0
            except Exception:
                _default_index = 0
            _choice = st.radio(
                label="Sezione",
                options=_menu_items,
                index=_default_index,
                key="sidebar_menu",
                label_visibility="collapsed",
            )
            if _choice != _current:
                st.session_state["active_section"] = _choice
                _safe_streamlit_rerun()

            # Impostazioni retriever (config cliente)
            with st.expander("Ricerca (retriever)", expanded=False):
                cfg: Dict[str, Any] = {}
                try:
                    _ctx_read = _ensure_context(slug, log)
                    cfg = get_client_config(_ctx_read) or {}
                except Exception:
                    cfg = {}

                retr = dict(cfg.get("retriever") or {})
                try:
                    current_limit = int(retr.get("candidate_limit", 4000) or 4000)
                except Exception:
                    current_limit = 4000
                try:
                    current_budget = int(retr.get("latency_budget_ms", 0) or 0)
                except Exception:
                    current_budget = 0
                auto_flag = bool(retr.get("auto_by_budget", False))

                st.caption(("Imposta il limite candidati per il ranking. Valori più alti aumentano la latenza."))
                new_limit = st.number_input(
                    "candidate_limit",
                    min_value=500,
                    max_value=20000,
                    step=500,
                    value=int(current_limit),
                    help="Numero massimo di candidati da considerare (default: 4000).",
                    key="inp_retr_limit",
                )
                new_budget = st.number_input(
                    "budget di latenza (ms)",
                    min_value=0,
                    max_value=10000,
                    step=50,
                    value=int(current_budget),
                    help="0 = disabilitato. Usato solo come riferimento operativo.",
                    key="inp_retr_budget",
                )
                new_auto = st.toggle(
                    "Auto per budget",
                    value=bool(auto_flag),
                    help=("Se attivo, il sistema sceglie automaticamente candidate_limit in base al budget."),
                    key="tgl_retr_auto",
                )

                # Stima limite se auto+budget
                if bool(new_auto) and int(new_budget) > 0:
                    try:
                        from src.retriever import choose_limit_for_budget

                        est = choose_limit_for_budget(int(new_budget))
                    except Exception:
                        est = None
                    if est:
                        st.caption(f"Limite stimato in base al budget: {int(est)}")

                colL, colR = st.columns([1, 1])
                with colL:
                    if st.button("Salva impostazioni retriever", key="btn_save_retriever"):
                        try:
                            lim = max(500, min(20000, int(new_limit)))
                            bud = max(0, min(10000, int(new_budget)))
                            ctx = _ensure_context(slug, log)
                            try:
                                cfg_now = get_client_config(ctx) or {}
                            except Exception:
                                cfg_now = {}
                            retr_prev = dict((cfg_now.get("retriever") or {}))
                            retr_prev.update(
                                {
                                    "candidate_limit": lim,
                                    "latency_budget_ms": bud,
                                    "auto_by_budget": bool(new_auto),
                                }
                            )
                            update_config_with_drive_ids(ctx, updates={"retriever": retr_prev}, logger=log)
                            _mark_modified_and_bump_once(slug, log)
                            st.success("Impostazioni salvate nel config del cliente.")
                        except Exception as e:
                            st.exception(e)
                with colR:
                    st.caption(("Calibra con 1000/2000/4000 e scegline il più piccolo che rispetta il budget."))

            # Tools
            st.subheader("Tools")
            if st.button(
                "Genera/Aggiorna dummy",
                key="btn_dummy",
                help=(
                    "Genera/aggiorna un utente e un dataset dummy per lo slug corrente.\n"
                    "Utile per test locali della pipeline senza materiali reali."
                ),
            ):
                slug_local = slug
                with st.spinner("Generazione dummy in corso…"):
                    try:
                        log.info({"event": "ui_dummy_generate_start", "slug": slug_local})
                        # Usa l'interprete corrente per robustezza cross-platform
                        proc = subprocess.run(
                            [sys.executable, "src/tools/gen_dummy_kb.py", "--slug", slug_local],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        log.info(
                            {
                                "event": "ui_dummy_generate_end",
                                "slug": slug_local,
                                "returncode": proc.returncode,
                            }
                        )
                        if proc.returncode == 0:
                            st.success("Dummy generato/aggiornato.")
                        else:
                            st.error(f"Dummy: errore (code {proc.returncode})")
                            if proc.stderr:
                                st.code(proc.stderr[:4000])
                        if proc.stdout:
                            st.code(proc.stdout[:4000])
                    except Exception as e:
                        st.error(f"Eccezione durante la generazione dummy: {e}")
                        try:
                            log.error(
                                {
                                    "event": "ui_dummy_generate_exception",
                                    "slug": slug_local,
                                    "error": str(e).splitlines()[:1],
                                }
                            )
                        except Exception:
                            pass

            if st.button(
                "Esci",
                key="btn_exit_sidebar",
                help="Chiude l'interfaccia Streamlit e termina il processo.",
            ):
                try:
                    log.info({"event": "ui_exit_requested", "slug": slug})
                    if bool(st.session_state.get("modified")) and set_data_ver_today is not None:
                        ctx = _ensure_context(slug, log)
                        set_data_ver_today(ctx, log)
                except Exception:
                    pass
                _request_shutdown(log)

    # Header pagina
    st.title("NeXT Onboarding")
    st.markdown(f"**Cliente:** {client_name} | **Slug:** `{slug}`")

    # Gating Semantica (usa ClientContext, non sem_get_paths)
    raw_ready = bool(st.session_state.get("raw_ready"))
    if not raw_ready:
        try:
            ctx = _ensure_context(slug, log)
            raw_dir = getattr(ctx, "raw_dir", None)
            if raw_dir and raw_dir.exists():
                try:
                    has_pdfs = any(raw_dir.rglob("*.pdf"))
                except Exception:
                    has_pdfs = False
            else:
                has_pdfs = False
            # base_dir sicuro
            has_csv = False
            base_dir_opt = getattr(ctx, "base_dir", None)
            if raw_dir and raw_dir.exists():
                base_dir_safe = raw_dir.parent
            elif isinstance(base_dir_opt, Path):
                base_dir_safe = base_dir_opt
            else:
                base_dir_safe = None
            if isinstance(base_dir_safe, Path):
                has_csv = (base_dir_safe / "semantic" / "tags_raw.csv").exists()
            st.session_state["raw_ready"] = bool(has_pdfs or has_csv)
        except Exception:
            pass

    # Sidebar Menù → sezioni
    active = cast(str, st.session_state.get("active_section") or "Configurazione")
    if active == "Configurazione":
        _render_config_tab(log, slug, client_name)
    elif active == "Drive":
        _render_drive_tab(log, slug)
    elif active == "Finanza":
        render_finance_tab(st=st, log=log, slug=slug)
    elif active == "Semantica":
        _render_semantic_tab(log, slug)
    elif active == "Preview":
        # Il tab Preview è interamente nel modulo estratto
        pass


if __name__ == "__main__":
    main()
