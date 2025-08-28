# onboarding_ui.py
from __future__ import annotations

# --- Bootstrap path: rende importabile la cartella 'src' come package root ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
# ---------------------------------------------------------------------------

import io
import os
import signal
import subprocess
import time
import uuid
from typing import Tuple, Dict, Any, List

import streamlit as st

# Logging/env dal repo (fallback robuste)
try:
    from pipeline.logging_utils import get_structured_logger  # type: ignore
except Exception:
    get_structured_logger = None  # type: ignore

try:
    from pipeline.env_utils import compute_redact_flag  # type: ignore
except Exception:
    compute_redact_flag = None  # type: ignore

# Moduli config_ui (API allineate)
from src.config_ui.mapping_editor import (
    load_default_mapping,
    split_mapping,
    build_mapping,
    validate_categories,
    save_tags_reviewed,
    examples_to_items,   # usiamo le helper esposte dal modulo
    items_to_examples,
)
from src.config_ui.vision_parser import extract_ovm_sections, write_vision_yaml


# ----------------- Helper locali (log, shutdown, pdf) -----------------

def _safe_compute_redact_flag() -> bool:
    if compute_redact_flag is None:
        return True
    try:
        return bool(compute_redact_flag())
    except TypeError:
        pass
    try:
        return bool(compute_redact_flag({}, "INFO"))
    except Exception:
        return True


def _safe_get_logger(name: str, redact_flag: bool):
    if get_structured_logger is None:
        class _Stub:
            def info(self, *a, **k): pass
            def warning(self, *a, **k): pass
            def error(self, *a, **k): pass
            def exception(self, *a, **k): pass
        return _Stub()
    try:
        return get_structured_logger(name, redact_secrets=redact_flag)  # type: ignore
    except TypeError:
        try:
            return get_structured_logger(name, redact=redact_flag)  # type: ignore
        except TypeError:
            return get_structured_logger(name)  # type: ignore


def _shutdown_server() -> None:
    try:
        st.toast("Chiusura in corso…", icon="🛑")
    except Exception:
        pass
    time.sleep(0.1)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _run_orchestrator(cmd: list[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _pdf_to_text(file_bytes: bytes) -> str:
    """Estrazione testo PDF (pypdf -> PyMuPDF)."""
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        pass
    try:
        import fitz  # type: ignore
        text_parts = []
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:  # type: ignore[attr-defined]
            for page in doc:
                text_parts.append(page.get_text() or "")
        return "\n".join(text_parts).strip()
    except Exception as e:
        raise RuntimeError("Installa `pypdf` oppure `pymupdf` per estrarre testo.") from e


# ------------------------ App Streamlit ------------------------

def main() -> None:
    st.set_page_config(page_title="Timmy-KB · Onboarding UI", layout="wide")

    redact = _safe_compute_redact_flag()
    logger = _safe_get_logger(__name__, redact)

    st.title("Timmy-KB · Onboarding UI (incrementale)")
    st.caption("Configurazione (mapping) + Pre-Onboarding. Runner Drive con import pigro e messaggi d’errore chiari.")

    # Sidebar
    with st.sidebar:
        st.header("Contesto")
        slug = st.text_input("Slug cliente", placeholder="es. acme", key="slug")
        client_name = st.text_input("Nome cliente", placeholder="Cliente ACME s.r.l.", key="client_name")
        dry_run = st.toggle("Dry-run (solo locale)", value=True, key="dry_run")
        st.caption("Valori usati nel context del mapping e nei runner Drive.")
        st.divider()
        if st.button("Esci", type="secondary"):
            _shutdown_server()

    # Tabs
    tab_config, tab_pre, tab_sem, tab_push = st.tabs(
        ["Configurazione", "Pre-Onboarding", "Semantic Onboarding (vuoto)", "Onboarding Full (vuoto)"]
    )

    # ===== CONFIGURAZIONE (Editor — MAPPING) =====
    with tab_config:
        st.subheader("Configurazione — Editor del mapping semantico")
        st.caption("Caricato da config/default_semantic_mapping.yaml. Salva in output/…/semantic/tags_reviewed.yaml")

        st.markdown(
            """
            <style>
            .map-card { background: #eef6ff; border: 1px solid #cfe3ff; border-radius: 14px; padding: 12px 14px; margin-bottom: 10px; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Stato editor
        st.session_state.setdefault("mapping_categories", {})
        st.session_state.setdefault("mapping_reserved", {})
        st.session_state.setdefault("mapping_normalize", True)
        st.session_state.setdefault("mapping_auto_loaded", False)

        # Autoload mapping
        if not st.session_state["mapping_auto_loaded"]:
            try:
                root_map = load_default_mapping()
                cats, res = split_mapping(root_map)
                # UI: esempi in items con id
                for k, v in list(cats.items()):
                    v["esempio"] = examples_to_items(v.get("esempio", []))
                st.session_state["mapping_categories"] = cats
                st.session_state["mapping_reserved"] = res
                st.session_state["mapping_auto_loaded"] = True
            except Exception as e:
                st.error(f"Errore nel caricamento mapping: {e}")

        st.toggle(
            "Normalizza chiavi categoria in kebab-case al salvataggio",
            value=st.session_state["mapping_normalize"],
            key="mapping_normalize",
        )

        st.divider()

        cats = st.session_state["mapping_categories"]
        if not cats:
            st.info("Nessun mapping caricato.")
        else:
            def _k(x: str) -> str:
                x = x.strip().lower().replace("_", "-").replace(" ", "-")
                import re as _re
                x = _re.sub(r"[^a-z0-9-]+", "-", x)
                x = _re.sub(r"-{2,}", "-", x).strip("-")
                return x

            cat_keys_sorted = sorted(list(cats.keys()), key=_k)
            tab_objs = st.tabs(cat_keys_sorted)

            if st.button("＋ Aggiungi nuova categoria"):
                base = "nuova-categoria"
                k = base
                i = 1
                while k in cats:
                    k = f"{base}-{i}"
                    i += 1
                cats[k] = {"ambito": "", "descrizione": "", "esempio": []}
                st.experimental_rerun()

            for tab_key, cat_key in zip(tab_objs, cat_keys_sorted):
                data = cats[cat_key]
                with tab_key:
                    rn_cols = st.columns([5, 2, 2])
                    new_key = rn_cols[0].text_input("Rinomina categoria", value=cat_key, key=f"rn_key_{cat_key}")
                    apply_rn = rn_cols[1].button("Applica rinomina", key=f"rn_apply_{cat_key}")
                    del_cat = rn_cols[2].button("🗑️ Elimina categoria", key=f"rn_del_{cat_key}")

                    if apply_rn:
                        final_key = new_key.strip()
                        if not final_key:
                            st.warning("Nome categoria non valido.")
                        elif final_key in cats and final_key != cat_key:
                            st.warning(f"Esiste già '{final_key}'.")
                        else:
                            cats[final_key] = cats.pop(cat_key)
                            st.experimental_rerun()

                    if del_cat:
                        cats.pop(cat_key, None)
                        st.experimental_rerun()

                    st.markdown('<div class="map-card">', unsafe_allow_html=True)
                    ambito = st.text_input("Titolo (Ambito)", value=data.get("ambito", ""), key=f"amb_{cat_key}")
                    descr = st.text_area("Descrizione", value=data.get("descrizione", ""), key=f"desc_{cat_key}")

                    st.markdown("**Esempi**")
                    items: List[Dict[str, str]] = data.get("esempio", []) or []
                    for it in items:
                        it.setdefault("id", uuid.uuid4().hex)
                        it.setdefault("value", "")
                    rm_idx = None
                    for idx, it in enumerate(items):
                        e_cols = st.columns([10, 1])
                        it["value"] = e_cols[0].text_input(
                            f"Esempio {idx+1}", value=it.get("value", ""), key=f"ex_{cat_key}_{it['id']}"
                        )
                        if e_cols[1].button("✖", key=f"ex_del_{cat_key}_{it['id']}"):
                            rm_idx = idx
                    if rm_idx is not None:
                        items.pop(rm_idx)
                        st.experimental_rerun()
                    if st.button("＋ Aggiungi esempio", key=f"ex_add_{cat_key}"):
                        items.append({"id": uuid.uuid4().hex, "value": ""})
                        st.experimental_rerun()

                    data["ambito"] = ambito
                    data["descrizione"] = descr
                    data["esempio"] = items
                    st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        cA, cB, cC = st.columns([1, 1, 1])
        with cA:
            if st.button("Valida mapping"):
                cats_plain = {
                    k: {
                        "ambito": v.get("ambito", ""),
                        "descrizione": v.get("descrizione", ""),
                        "esempio": items_to_examples(v.get("esempio", []) or []),
                    } for k, v in st.session_state["mapping_categories"].items()
                }
                err = validate_categories(cats_plain, normalize_keys=st.session_state["mapping_normalize"])
                st.success("Mapping valido.") if not err else st.error(err)

        with cB:
            with st.expander("Anteprima YAML (mapping) — apri/chiudi", expanded=False):
                cats_plain = {
                    k: {
                        "ambito": v.get("ambito", ""),
                        "descrizione": v.get("descrizione", ""),
                        "esempio": items_to_examples(v.get("esempio", []) or []),
                    } for k, v in st.session_state["mapping_categories"].items()
                }
                final_map = build_mapping(
                    categories=cats_plain,
                    reserved=st.session_state["mapping_reserved"],
                    slug=st.session_state.get("slug") or "",
                    client_name=st.session_state.get("client_name") or "",
                    normalize_keys=st.session_state["mapping_normalize"],
                )
                import yaml
                st.code(yaml.safe_dump(final_map, allow_unicode=True, sort_keys=True), language="yaml")

        with cC:
            base_root = Path("output")
            slug_val = st.session_state.get("slug")
            if st.button("Salva mapping (tags_reviewed.yaml)"):
                try:
                    if not slug_val:
                        st.warning("Inserisci lo slug nella sidebar.")
                    else:
                        cats_plain = {
                            k: {
                                "ambito": v.get("ambito", ""),
                                "descrizione": v.get("descrizione", ""),
                                "esempio": items_to_examples(v.get("esempio", []) or []),
                            } for k, v in st.session_state["mapping_categories"].items()
                        }
                        err = validate_categories(cats_plain, normalize_keys=st.session_state["mapping_normalize"])
                        if err:
                            st.error(err)
                        else:
                            final_map = build_mapping(
                                categories=cats_plain,
                                reserved=st.session_state["mapping_reserved"],
                                slug=slug_val,
                                client_name=st.session_state.get("client_name") or slug_val,
                                normalize_keys=st.session_state["mapping_normalize"],
                            )
                            path = save_tags_reviewed(slug_val, final_map, base_root=base_root)
                            st.success(f"Salvato: {path}")
                except Exception as e:
                    st.error(f"Errore salvataggio: {e}")

    # ===== PRE-ONBOARDING =====
    with tab_pre:
        st.subheader("Pre-Onboarding — Vision YAML + Drive provisioning")
        st.caption("1) Vision PDF → vision.yaml (solo O/V/M). 2) Provisioning Drive (struttura + README).")

        uploaded_pdf = st.file_uploader("Carica vision_statement.pdf", type=["pdf"], key="vision_pdf")

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Estrai testo → O/V/M → vision.yaml"):
                slug_val = st.session_state.get("slug")
                if not slug_val:
                    st.warning("Inserisci lo slug nella sidebar.")
                elif not uploaded_pdf:
                    st.warning("Seleziona prima un file PDF.")
                else:
                    try:
                        pdf_bytes = uploaded_pdf.read()
                        full_text = _pdf_to_text(pdf_bytes)
                        ovm = extract_ovm_sections(full_text)
                        path = write_vision_yaml(slug_val, ovm, base_root="output")
                        st.session_state["vision_text"] = full_text
                        st.success(f"vision.yaml scritto in {path}")
                    except Exception as e:
                        st.error(f"Errore durante l'estrazione/scrittura: {e}")

        with c2:
            if st.session_state.get("vision_text"):
                st.markdown("**Anteprima estratto (prime ~2000 battute)**")
                st.code(st.session_state["vision_text"][:2000], language="markdown")
                st.download_button(
                    label="Scarica estratto (TXT)",
                    data=st.session_state["vision_text"],
                    file_name="vision_statement_extracted.txt",
                    mime="text/plain",
                )

        st.divider()
        st.markdown("### Passi su Drive")
        d1, d2 = st.columns([1, 1])

        with d1:
            if st.button("Crea struttura su Drive"):
                slug_val = st.session_state.get("slug")
                if not slug_val:
                    st.warning("Inserisci lo slug nella sidebar.")
                else:
                    try:
                        from src.config_ui.drive_runner import build_drive_from_mapping
                        ids = build_drive_from_mapping(
                            slug_val,
                            st.session_state.get("client_name") or slug_val,
                            require_env=not st.session_state.get("dry_run", True),
                            base_root="output",
                        )
                        st.success(f"Struttura creata. ClientFolderID: {ids.get('client_folder_id','?')[:6]}…  RAW: {ids.get('raw_id','?')[:6]}…")
                    except Exception as e:
                        st.error(f"Errore Drive (creazione struttura): {e}")

        with d2:
            if st.button("Genera README nelle cartelle RAW"):
                slug_val = st.session_state.get("slug")
                if not slug_val:
                    st.warning("Inserisci lo slug nella sidebar.")
                else:
                    try:
                        from src.config_ui.drive_runner import emit_readmes_for_raw
                        uploaded = emit_readmes_for_raw(
                            slug_val,
                            base_root="output",
                            require_env=not st.session_state.get("dry_run", True),
                        )
                        st.success(f"README caricati in {len(uploaded)} cartelle RAW.")
                    except Exception as e:
                        st.error(f"Errore Drive (README): {e}")

    with tab_sem:
        st.caption("")
    with tab_push:
        st.caption("")


if __name__ == "__main__":
    main()
