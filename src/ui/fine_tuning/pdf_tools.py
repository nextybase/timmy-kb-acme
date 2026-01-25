# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout, workspace_validation_policy
from semantic.core import compile_document_to_vision_yaml
from ui.utils.context_cache import get_client_context
from ui.utils.stubs import get_streamlit

st = get_streamlit()
LOG = get_structured_logger("ui.pdf_tools")


def run_pdf_to_yaml_config(slug: str) -> None:
    ctx = get_client_context(slug, require_env=False)
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(ctx)
    repo_root = layout.repo_root_dir
    cfg_dir = layout.config_path.parent
    pdf_path = ensure_within_and_resolve(repo_root, layout.vision_pdf or (cfg_dir / "VisionStatement.pdf"))
    yaml_path = vision_yaml_workspace_path(repo_root, pdf_path=Path(pdf_path))

    if not pdf_path.exists():
        st.error(f"VisionStatement.pdf mancante nel workspace: {pdf_path}")
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
