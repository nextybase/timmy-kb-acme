# onboarding_ui.py
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple, List

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

# ClientContext per la tab Semantica (opzionale)
try:
    from pipeline.context import ClientContext  # type: ignore
except Exception:  # pragma: no cover
    ClientContext = None  # type: ignore

# Preview adapters (HonKit) opzionali
try:
    from adapters.preview import start_preview, stop_preview  # type: ignore
except Exception:  # pragma: no cover
    start_preview = stop_preview = None  # type: ignore

# -----------------------------------------------------------------------------
# Import UI/Config helpers (riuso: NIENTE duplicazioni)
# -----------------------------------------------------------------------------
from config_ui.mapping_editor import (  # type: ignore  # noqa: E402
    load_default_mapping,
    load_tags_reviewed,
    save_tags_reviewed,
    split_mapping,
    build_mapping,
    validate_categories,
)
from config_ui.drive_runner import (  # type: ignore  # noqa: E402
    build_drive_from_mapping,
    emit_readmes_for_raw,
)

# Download PDF da Drive â†’ raw/ locale (opzionale, potrebbe non essere ancora implementato)
try:
    from config_ui.drive_runner import download_raw_from_drive  # type: ignore
except Exception:  # pragma: no cover
    download_raw_from_drive = None  # type: ignore

# -----------------------------------------------------------------------------
# Import funzioni Semantica (opzionali, con fallback)
# -----------------------------------------------------------------------------
try:
    # Facade pubblica stabile per la UI
    from semantic.api import (  # type: ignore
        get_paths as sem_get_paths,
        load_reviewed_vocab as sem_load_vocab,
        convert_markdown as sem_convert,
        enrich_frontmatter as sem_enrich,
        write_summary_and_readme as sem_write_md,
    )
except Exception:  # pragma: no cover
    sem_get_paths = sem_load_vocab = sem_convert = sem_enrich = sem_write_md = None  # type: ignore

# -----------------------------------------------------------------------------
# Import Finanza (opzionale)
# -----------------------------------------------------------------------------
try:
    from finance.api import import_csv as fin_import_csv, summarize_metrics as fin_summarize  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    fin_import_csv = fin_summarize = None  # type: ignore
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


def _norm_str(val: Optional[str]) -> str:
    return val.strip() if isinstance(val, str) else ""


def _safe_streamlit_rerun() -> None:
    # Usa lâ€™API stabile; fallback a experimental se presente. Evita warning Pylance.
    fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


# =============================================================================
# Componenti UI
# =============================================================================
def _render_landing_inputs(log: logging.Logger) -> Tuple[bool, str, str]:
    """
    Schermata iniziale: SOLO due input centrali (slug, nome cliente).
    Appena entrambi sono compilati, blocchiamo i valori e facciamo apparire la UI.
    """
    # Placeholder full-width senza altri elementi
    st.markdown("<div style='height: 8vh'></div>", unsafe_allow_html=True)

    # Input centrali full-width
    slug_raw = st.text_input(
        "Slug cliente",
        value=st.session_state.get("slug", ""),
        placeholder="es. acme",
        key="landing_slug",
    )
    client_raw = st.text_input(
        "Nome cliente",
        value=st.session_state.get("client_name", ""),
        placeholder="ACME S.p.A.",
        key="landing_client",
    )

    slug = _norm_str(slug_raw)
    client = _norm_str(client_raw)

    # Lock automatico quando entrambi non vuoti
    if slug and client and not st.session_state.get("client_locked", False):
        st.session_state["slug"] = slug
        st.session_state["client_name"] = client
        st.session_state["client_locked"] = True
        _safe_streamlit_rerun()

    locked = bool(st.session_state.get("client_locked", False))
    return locked, st.session_state.get("slug", ""), st.session_state.get("client_name", "")


def _render_header_after_lock(log: logging.Logger, slug: str, client_name: str) -> None:
    # Mostra info bloccate e un pulsante di chiusura UI
    left, right = st.columns([4, 1])
    with left:
        st.markdown(f"**Cliente:** {client_name} &nbsp;&nbsp;|&nbsp;&nbsp; **Slug:** `{slug}`")
    with right:
        if st.button("Chiudi UI", key="btn_close_ui_top", use_container_width=True):
            _request_shutdown(log)


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
        # Accordion per-voce con widget con key UNIVOCHE (l'expander non supporta 'key' in alcune versioni)
        for idx, cat_key in enumerate(sorted(cats.keys(), key=str)):
            meta = cats.get(cat_key, {})
            with st.expander(cat_key, expanded=False):
                amb = st.text_input(
                    f"Ambito â€” {cat_key}",
                    value=str(meta.get("ambito", "")),
                    key=f"amb_{idx}_{cat_key}",
                )
                desc = st.text_area(
                    f"Descrizione â€” {cat_key}",
                    value=str(meta.get("descrizione", "")),
                    height=120,
                    key=f"desc_{idx}_{cat_key}",
                )
                examples_str = "\n".join([str(x) for x in (meta.get("esempio") or [])])
                ex = st.text_area(
                    f"Esempi (uno per riga) â€” {cat_key}",
                    value=examples_str,
                    height=120,
                    key=f"ex_{idx}_{cat_key}",
                )

                if st.button(
                    f"Salva â€œ{cat_key}â€",
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
                                _safe_streamlit_rerun()
                            except Exception:
                                pass
                    except Exception as e:
                        st.exception(e)

        st.caption(
            "Suggerimento: usa il pulsante Salva dentro ogni voce per applicare modifiche puntuali."
        )

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
            except Exception as e:
                st.exception(e)


def _render_drive_tab(log: logging.Logger, slug: str) -> None:
    st.subheader("Drive")
    st.caption(
        "Crea la struttura su Drive a partire dal mapping rivisto e genera i README nelle sottocartelle di `raw/`."
    )

    colA, colB = st.columns([1, 1], gap="large")

    with colA:
        if st.button(
            "1) Crea/aggiorna struttura Drive", key="btn_drive_create", use_container_width=True
        ):
            try:
                prog = st.progress(0)
                status = st.empty()

                def _cb(step: int, total: int, label: str) -> None:
                    pct = int(step * 100 / total)
                    prog.progress(pct)
                    status.markdown(f"{pct}% â€” {label}")

                ids = build_drive_from_mapping(
                    slug=slug, client_name=st.session_state.get("client_name", ""), progress=_cb
                )
                st.success(f"Struttura creata: {ids}")
                log.info({"event": "drive_structure_created", "slug": slug, "ids": ids})
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
                result = emit_readmes_for_raw(slug=slug)
                st.success(f"README creati: {len(result)}")
                log.info({"event": "raw_readmes_uploaded", "slug": slug, "count": len(result)})
                st.session_state["drive_readmes_done"] = True
            except Exception as e:
                st.exception(e)

    # -------------------------------------------------------------------------
    # Nuova sezione: download PDF da Drive â†’ raw/ (visibile SOLO dopo i README)
    # -------------------------------------------------------------------------
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
                    st.error(
                        "Funzione di download non disponibile: aggiornare 'config_ui.drive_runner'."
                    )
                else:
                    try:
                        # Usa variante con progress se disponibile
                        prog = st.progress(0)
                        status = st.empty()
                        try:
                            from config_ui.drive_runner import download_raw_from_drive_with_progress  # type: ignore

                            def _pcb(done: int, total: int, label: str) -> None:
                                pct = int((done * 100) / (total or 1))
                                prog.progress(pct)
                                status.markdown(f"{pct}% â€” {label}")

                            res = download_raw_from_drive_with_progress(slug=slug, on_progress=_pcb)  # type: ignore[misc]
                        except Exception:
                            res = download_raw_from_drive(slug=slug)  # type: ignore[misc]
                        count = len(res) if hasattr(res, "__len__") else None
                        st.success(
                            f"Download completato{f' ({count} file)' if count is not None else ''}."
                        )
                        log.info({"event": "drive_raw_downloaded", "slug": slug, "count": count})
                        st.session_state["raw_downloaded"] = True
                        try:
                            _safe_streamlit_rerun()  # per sbloccare la tab Semantica
                        except Exception:
                            pass
                    except Exception as e:
                        st.exception(e)
        with c2:
            st.write(
                (
                    "La struttura delle cartelle Ã¨ stata creata su Drive; "
                    "popolarne il contenuto seguendo le indicazioni del file README presente in ogni "
                    "cartella per proseguire con la procedura"
                )
            )


# =============================================================================
# Tab: Semantica (RAW â†’ BOOK + frontmatter + README/SUMMARY + preview)
# =============================================================================
def _ensure_context(slug: str, log: logging.Logger) -> object:
    if ClientContext is None:
        raise RuntimeError("Moduli pipeline non disponibili: impossibile creare il ClientContext.")
    # Nessun prompt da UI; env non obbligatorio per operazioni locali
    return ClientContext.load(
        slug=slug,
        interactive=False,
        require_env=False,
        run_id=None,
    )  # type: ignore[no-any-return]


def _render_finance_tab(log: logging.Logger, slug: str) -> None:
    from pathlib import Path as _Path

    try:
        from pipeline.path_utils import ensure_within as _ensure_within  # type: ignore
        from pipeline.file_utils import safe_write_bytes as _safe_write_bytes  # type: ignore
    except Exception:
        _ensure_within = None  # type: ignore
        _safe_write_bytes = None  # type: ignore

    st.subheader("Finanza (CSV â†’ finance.db)")
    st.caption(
        "Ingestione opzionale di metriche numeriche in un DB SQLite separato (`semantic/finance.db`)."
    )
    if fin_import_csv is None or fin_summarize is None:
        st.warning(
            "Modulo finanza non disponibile. Verificare l'ambiente o l'installazione del progetto."
        )
        return

    colA, colB = st.columns([1, 1], gap="large")
    with colA:
        file = st.file_uploader(
            "Carica CSV: metric, period, value, [unit], [currency], [note], [canonical_term]",
            type=["csv"],
            accept_multiple_files=False,
        )
        if st.button(
            "Importa in finance.db",
            key="btn_fin_import",
            use_container_width=True,
            disabled=(file is None),
        ):
            try:
                base = sem_get_paths(slug)["base"] if sem_get_paths else _Path(".")
                sem_dir = base / "semantic"
                tmp_name = f"tmp-finance-{st.session_state.get('run_id','run')}.csv"
                tmp_csv = sem_dir / tmp_name
                if _ensure_within is not None:
                    _ensure_within(sem_dir, tmp_csv)
                sem_dir.mkdir(parents=True, exist_ok=True)
                data = file.read() if file is not None else b""
                if _safe_write_bytes is not None:
                    _safe_write_bytes(tmp_csv, data, atomic=True)
                else:
                    tmp_csv.write_bytes(data)
                res = fin_import_csv(base, tmp_csv)  # type: ignore[misc]
                st.success(
                    f"Import OK â€” righe: {res.get('rows', 0)}  in {res.get('db', str(sem_dir / 'finance.db'))}"
                )
                log.info({"event": "finance_import_ok", "slug": slug, "rows": res.get("rows")})
                try:
                    tmp_csv.unlink(missing_ok=True)
                except Exception:
                    pass
            except Exception as e:
                st.exception(e)
    with colB:
        try:
            base = sem_get_paths(slug)["base"] if sem_get_paths else _Path(".")
            summary = fin_summarize(base)  # type: ignore[misc]
            if summary:
                st.caption("Metriche presenti:")
                st.table(
                    {"metric": [m for m, _ in summary], "osservazioni": [n for _, n in summary]}
                )
            else:
                st.info("Nessuna metrica importata al momento.")
        except Exception as e:
            st.exception(e)


def _render_semantic_tab(log: logging.Logger, slug: str) -> None:
    st.subheader("Semantica (RAW â†’ BOOK)")
    st.caption(
        "Converte i PDF in Markdown, arricchisce i frontmatter e genera README/SUMMARY. Preview Docker opzionale."
    )

    # Guardie minime su dipendenze
    if any(x is None for x in (sem_convert, sem_enrich, sem_write_md, sem_load_vocab)):
        st.error("Modulo semantic.api non disponibile o import parziale. Verificare l'ambiente.")
        return
    if ClientContext is None:
        st.error("Pipeline non disponibile: impossibile creare il contesto cliente.")
        return

    # Prepara contesto
    try:
        context = _ensure_context(slug, log)
    except Exception as e:
        st.exception(e)
        return

    colA, colB = st.columns([1, 1], gap="large")

    with colA:
        st.markdown("**1) Conversione RAW â†’ BOOK**")
        if st.button("Converti PDF in Markdown", key="btn_sem_convert", use_container_width=True):
            try:
                mds: List[Path] = sem_convert(context, log, slug=slug)  # type: ignore[misc]
                st.success(f"OK. File Markdown in book/: {len(mds)}")
                log.info(
                    {
                        "event": "semantic_convert_done",
                        "slug": slug,
                        "run_id": st.session_state.get("run_id"),
                        "md_count": len(mds),
                    }
                )
            except Exception as e:
                st.exception(e)

        st.markdown("**2) Arricchisci frontmatter**")
        if st.button(
            "Arricchisci con tag canonici (SQLite)",
            key="btn_sem_enrich",
            use_container_width=True,
        ):
            try:
                base_dir = sem_get_paths(slug)["base"]  # type: ignore[index]
                vocab = sem_load_vocab(base_dir, log)  # type: ignore[misc]
                touched: List[Path] = sem_enrich(context, log, vocab, slug=slug)  # type: ignore[misc]
                st.success(f"OK. Frontmatter aggiornati: {len(touched)}")
                log.info(
                    {
                        "event": "semantic_enrich_done",
                        "slug": slug,
                        "run_id": st.session_state.get("run_id"),
                        "touched": len(touched),
                    }
                )
            except Exception as e:
                st.exception(e)

    with colB:
        st.markdown("**3) README/SUMMARY**")
        if st.button(
            "Genera/valida README & SUMMARY", key="btn_sem_write_md", use_container_width=True
        ):
            try:
                sem_write_md(context, log, slug=slug)  # type: ignore[misc]
                st.success("OK. README.md e SUMMARY.md pronti.")
                log.info(
                    {
                        "event": "semantic_write_md_done",
                        "slug": slug,
                        "run_id": st.session_state.get("run_id"),
                    }
                )
            except Exception as e:
                st.exception(e)

        st.markdown("**4) Preview Docker (HonKit)**")
        with st.container(border=True):
            # Porta e stato container in sessione
            preview_port = st.number_input(
                "Porta preview",
                min_value=1,
                max_value=65535,
                value=4000,
                step=1,
                key="inp_sem_port",
            )

            # Avanzate: container_name opzionale
            from typing import Optional

            def _docker_safe(name: Optional[str]) -> str:
                import re as _re

                s = (name or "").strip()
                if not s:
                    return s
                s = _re.sub(r"[^a-zA-Z0-9_.-]", "-", s)
                s = s.strip("-._") or s
                return s

            def _default_container(slug_val: str) -> str:
                import re as _re

                safe = _re.sub(r"[^a-zA-Z0-9_.-]+", "-", (slug_val or "kb")).strip("-") or "kb"
                return f"gitbook-{safe}"

            with st.expander("Avanzate", expanded=False):
                current_default = _default_container(slug)
                container_name_raw = st.text_input(
                    "Nome container Docker",
                    value=st.session_state.get("sem_container_name", current_default),
                    help="Lasciare vuoto per usare il default suggerito.",
                    key="inp_sem_container_name",
                )
                container_name = _docker_safe(container_name_raw) or current_default
                st.session_state["sem_container_name"] = container_name
            running = bool(st.session_state.get("sem_preview_container"))
            st.write(f"Stato: {'ATTIVA' if running else 'SPENTA'}")
            cols = st.columns([1, 1])
            with cols[0]:
                if st.button(
                    "Avvia preview",
                    key="btn_sem_preview_start",
                    use_container_width=True,
                    disabled=(start_preview is None or running),
                ):
                    try:
                        cname = start_preview(
                            context,
                            log,
                            port=int(preview_port),
                            container_name=st.session_state.get("sem_container_name"),
                        )  # type: ignore[misc]
                        st.session_state["sem_preview_container"] = cname
                        st.success(
                            f"Preview avviata su http://127.0.0.1:{int(preview_port)}  (container: {cname})"
                        )
                        log.info(
                            {
                                "event": "preview_started",
                                "slug": slug,
                                "run_id": st.session_state.get("run_id"),
                                "port": int(preview_port),
                                "container": cname,
                            }
                        )
                        _safe_streamlit_rerun()
                    except Exception as e:
                        msg = str(e)
                        if any(
                            k in msg.lower()
                            for k in ("docker", "daemon", "not running", "cannot connect")
                        ):
                            st.warning(
                                "Docker non risulta attivo. Avvia Docker Desktop e riprova ad avviare la preview."
                            )
                            log.warning(
                                "Preview non avviata: Docker non attivo",
                                extra={"error": msg},
                            )
                        else:
                            st.exception(e)
            with cols[1]:
                if st.button(
                    "Ferma preview",
                    key="btn_sem_preview_stop",
                    use_container_width=True,
                    disabled=(stop_preview is None or not running),
                ):
                    try:
                        cname = st.session_state.get("sem_preview_container")
                        stop_preview(log, container_name=cname)  # type: ignore[misc]
                        st.session_state["sem_preview_container"] = None
                        st.success("Preview fermata.")
                        log.info(
                            {
                                "event": "preview_stopped",
                                "slug": slug,
                                "run_id": st.session_state.get("run_id"),
                                "container": cname,
                            }
                        )
                        _safe_streamlit_rerun()
                    except Exception as e:
                        st.exception(e)

    st.divider()
    st.caption(
        "Nota: questo step **non** usa Google Drive nÃ© esegue push su GitHub; lavora su disco locale e preview."
    )


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    st.set_page_config(page_title="NeXT â€” Onboarding UI", layout="wide")
    redact = _safe_compute_redact_flag()
    log = _safe_get_logger("onboarding_ui", redact)
    # run_id per correlazione log UI
    try:
        import uuid as _uuid

        if not st.session_state.get("run_id"):
            st.session_state["run_id"] = _uuid.uuid4().hex
    except Exception:
        pass

    # Gating iniziale: solo input slug+cliente a schermo pieno
    if not st.session_state.get("client_locked", False):
        locked, _, _ = _render_landing_inputs(log)
        if not locked:
            return  # finchÃ© non sono compilati entrambi, non mostrare altro

    # Da qui in poi la UI completa
    slug = st.session_state.get("slug", "")
    client_name = st.session_state.get("client_name", "")

    st.title("NeXT â€” Onboarding UI")
    _render_header_after_lock(log, slug, client_name)

    # Tabs: Semantica nascosta finchÃ© non abbiamo scaricato i PDF su raw/
    tabs_labels: List[str] = ["Configurazione", "Drive"]
    if st.session_state.get("client_locked"):
        tabs_labels.append("Finanza")

    # Sblocca la tab "Semantica" se:
    # - la UI ha appena scaricato i PDF (flag di sessione), oppure
    # - esiste la cartella raw/ locale del cliente con almeno un PDF (stato reale)
    raw_ready = False
    try:
        if sem_get_paths is not None and slug:
            raw_dir = sem_get_paths(slug)["raw"]  # type: ignore[index]
            if raw_dir.exists():
                try:
                    # pronto se ci sono PDF in raw/ (ricorsivo)
                    has_pdfs = any(raw_dir.rglob("*.pdf"))
                except Exception:
                    has_pdfs = False
                # in alternativa, considera pronto se esiste il CSV generato nella fase tag
                has_csv = (raw_dir.parent / "semantic" / "tags_raw.csv").exists()
                raw_ready = bool(has_pdfs or has_csv)
    except Exception:
        raw_ready = False

    if st.session_state.get("raw_downloaded") or raw_ready:
        tabs_labels.append("Semantica")

    tabs = st.tabs(tabs_labels)
    with tabs[0]:
        _render_config_tab(log, slug, client_name)
    with tabs[1]:
        _render_drive_tab(log, slug)
    if "Finanza" in tabs_labels:
        with tabs[2]:
            _render_finance_tab(log, slug)
    if "Semantica" in tabs_labels:
        fin_index = 1 + (1 if "Finanza" in tabs_labels else 0)
        with tabs[1 + fin_index]:
            _render_semantic_tab(log, slug)


if __name__ == "__main__":
    main()
