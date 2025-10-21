# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/tools_check.py
# Tools › Check: lancia scripts/kb_healthcheck.py su 'dummy' e,
# se ok, mostra semantic_mapping.yaml come albero (titolo/descrizione).
from __future__ import annotations

import html
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, cast

import streamlit as st
import yaml

from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# --- percorsi (nessuna preparazione workspace) ---
REPO_ROOT = Path(__file__).resolve().parents[3]  # <repo root>
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT = REPO_ROOT / "scripts" / "kb_healthcheck.py"
SLUG = "dummy"
ROOT_PDF = REPO_ROOT / "config" / "VisionStatement.pdf"


# --- UI helpers ---
def _render_mapping_tree(mapping: Dict[str, Any]) -> None:
    """Albero elegante: solo titolo (ambito) e descrizione."""
    SKIP = {"context", "synonyms", "system_folders"}
    areas = [(k, v) for k, v in mapping.items() if k not in SKIP and isinstance(v, dict)]
    if not areas:
        st.info("Nessuna area rilevata nel mapping.")
        return

    st.markdown("#### Struttura semantica (titolo & descrizione)")

    items_html: list[str] = []
    for key, bloc in areas:
        titolo = html.escape(bloc.get("ambito") or key)
        descr = html.escape(bloc.get("descrizione") or "")
        safe_key = html.escape(key)
        items_html.append(
            f'<div class="tree-item">'
            f'<div class="tree-title">{titolo}</div>'
            f'<div class="tree-desc">{descr}</div>'
            f'<div class="tree-key">({safe_key})</div>'
            f"</div>"
        )

    tree_html = (
        "<style>"
        "  .tree {{ border-left: 2px solid #eee; margin-left: .5rem; padding-left: .75rem; }}"
        "  .tree-item {{ margin-bottom: .6rem; }}"
        "  .tree-title {{ font-weight: 600; }}"
        "  .tree-desc {{ color: #555; margin-top: .15rem; }}"
        '  .tree-key {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",'
        '                       "Courier New", monospace; font-size: 0.8rem; color: #777; }}'
        "</style>"
        '<div class="tree">'
        f'{"".join(items_html)}'
        "</div>"
    )
    st.html(tree_html)


def _run_healthcheck(force: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), "--slug", SLUG]
    if force:
        cmd.append("--force")

    st.caption("Esecuzione comando:")
    st.code(" ".join(shlex.quote(t) for t in cmd), language="bash")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603


def _parse_stdout(stdout: str) -> Dict[str, Any]:
    return cast(Dict[str, Any], json.loads(stdout))


def _gate_hit(stderr: str) -> bool:
    """
    Rileva l'errore del gate Vision ('già eseguito per questo PDF').
    """
    return bool(re.search(r"Vision.*gi[aà]\s+eseguito", stderr, flags=re.IGNORECASE) or "file=vision_hash" in stderr)


def main() -> None:
    st.title("Tools › Check")
    st.caption("Esegue l’healthcheck Vision su 'dummy' e visualizza il semantic_mapping come albero.")

    # prerequisiti leggeri (nessuna azione sul workspace)
    errors = []
    if not SCRIPT.exists():
        errors.append(f"Script non trovato: {SCRIPT}")
    if not ROOT_PDF.exists():
        errors.append(f"VisionStatement.pdf assente in root: {ROOT_PDF}")
    if not os.getenv("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY mancante.")
    if not (os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID")):
        errors.append("OBNEXT_ASSISTANT_ID/ASSISTANT_ID mancante.")

    if errors:
        st.error("Pre-requisiti mancanti:")
        for e in errors:
            st.markdown(f"- {e}")
    else:
        st.success("Pre-requisiti OK.")

    run_btn = st.button(
        "Esegui Healthcheck su 'dummy'",
        type="primary",
        disabled=bool(errors),
    )
    if not run_btn:
        return

    # 1° tentativo (senza force)
    with st.status("Eseguo healthcheck…", expanded=True) as status:
        res = _run_healthcheck(force=False)

        with st.expander("Output CLI", expanded=False):
            st.text(res.stdout or "(stdout vuoto)")
        with st.expander("Errori CLI", expanded=False):
            st.text(res.stderr or "(stderr vuoto)")

        # Auto-retry con --force se colpiamo il gate Vision
        if res.returncode != 0 and _gate_hit(res.stderr):
            st.info("Vision è già stata eseguita per questo PDF. Riprovo con forzatura…")
            res = _run_healthcheck(force=True)
            with st.expander("Output CLI (retry)", expanded=False):
                st.text(res.stdout or "(stdout vuoto)")
            with st.expander("Errori CLI (retry)", expanded=False):
                st.text(res.stderr or "(stderr vuoto)")

        if res.returncode != 0:
            status.update(label=f"Errore durante l'esecuzione (codice {res.returncode}).", state="error")
            st.error(f"kb_healthcheck è uscita con codice {res.returncode}")
            return

        # parse JSON
        try:
            payload = _parse_stdout(res.stdout)
        except Exception as e:
            status.update(label="JSON non valido dallo stdout.", state="error")
            st.error(f"Impossibile decodificare l'output: {e}")
            return

        status.update(label="Completato.", state="complete")

    st.success("Healthcheck completato con successo.")
    st.write(f"file_search usato: **{bool(payload.get('used_file_search'))}**")
    st.write(f"thread_id: `{payload.get('thread_id')}` - run_id: `{payload.get('run_id')}`")

    # semantic_mapping: preferisci il contenuto nel payload (se presente), altrimenti leggi dal path
    mapping_text: Optional[str] = payload.get("semantic_mapping_content")
    if not mapping_text:
        mp = payload.get("mapping_yaml")
        if mp:
            try:
                mapping_path = ensure_within_and_resolve(REPO_ROOT, Path(mp))
                mapping_text = read_text_safe(mapping_path.parent, mapping_path, encoding="utf-8")
            except Exception:
                mapping_text = None

    if mapping_text:
        try:
            mapping = yaml.safe_load(mapping_text) or {}
        except Exception:
            st.warning("Impossibile parsare il semantic_mapping.yaml; lo mostro raw.")
            st.code(mapping_text, language="yaml")
        else:
            _render_mapping_tree(mapping)
            with st.expander("semantic_mapping.yaml (raw)", expanded=False):
                st.code(mapping_text, language="yaml")
    else:
        st.warning("Nessun contenuto di semantic_mapping disponibile.")


if __name__ == "__main__":
    main()
