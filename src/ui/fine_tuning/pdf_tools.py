# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.vision_paths import vision_yaml_repo_path
from semantic.core import compile_document_to_vision_yaml
from ui.utils.stubs import get_streamlit

st = get_streamlit()
LOG = get_structured_logger("ui.pdf_tools")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_pdf_to_yaml_config() -> None:
    repo_root = _repo_root()
    cfg_dir = repo_root / "config"
    pdf_path = ensure_within_and_resolve(repo_root, cfg_dir / "VisionStatement.pdf")
    yaml_path = vision_yaml_repo_path(repo_root)

    if not pdf_path.exists():
        st.error(f"PDF non trovato: {pdf_path}")
        return

    try:
        compile_document_to_vision_yaml(pdf_path, yaml_path)
        st.success(f"Creato: {yaml_path}")
        try:
            preview = read_text_safe(repo_root, yaml_path)
            st.code(preview, language="yaml")
        except Exception:
            LOG.info("ui.pdf_tools.preview_unavailable")
    except Exception as exc:
        LOG.warning("ui.pdf_tools.convert_error", extra={"err": str(exc)})
        st.error(f"Errore durante la conversione: {exc}")
