# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Tuple, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from ui.config_store import get_vision_model
from ui.services.vision_provision import provision_from_vision_with_config
from ui.utils.context_cache import get_client_context
from ui.utils.stubs import get_streamlit

from .styles import apply_modal_css
from .yaml_io import build_prompt_from_yaml, load_workspace_yaml, save_workspace_yaml

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover - degradazione per runtime
    ClientContext = Any  # type: ignore[misc]

st = get_streamlit()

LOG = get_structured_logger("ui.vision_modal")
_SS_SECTIONS = "ft_modal_vision_sections"
_SS_LAST_RESULT = "ft_last_vision_result"

_SECTION_MAPPING: Tuple[Tuple[str, str], ...] = (
    ("Vision", "vision"),
    ("Mission", "mission"),
    ("Framework Etico", "framework_etico"),
    ("Goal", "goal"),
    ("Contesto Operativo", "contesto_operativo"),
)


def _st_rerun() -> None:
    rerun = getattr(st, "rerun", None)
    if callable(rerun):  # pragma: no cover - dipende dal runtime
        rerun()


def _clear_state() -> None:
    st.session_state.pop(_SS_SECTIONS, None)


def _is_gate_error(err: Exception) -> bool:
    message = str(err).casefold()
    if "file=vision_hash" in message:
        return True
    if "vision" in message and "eseguit" in message:
        return True
    marker = getattr(err, "file_path", None)
    if isinstance(marker, (str, Path)) and Path(marker).name == ".vision_hash":
        return True
    return False


def _ensure_workspace_pdf(ctx: ClientContext) -> Path:
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision.")
    base_path = Path(repo_root_dir)
    pdf_path = cast(
        Path,
        ensure_within_and_resolve(base_path, base_path / "config" / "VisionStatement.pdf"),
    )
    if not pdf_path.exists():
        raise ConfigError(f"VisionStatement.pdf mancante nel workspace: {pdf_path}")
    return pdf_path


def open_vision_modal(slug: str = "dummy") -> None:
    dialog_factory = getattr(st, "dialog", None)
    if not callable(dialog_factory):
        st.error("La versione corrente di Streamlit non supporta i dialog.")
        return

    DialogFactory = Callable[[str], Callable[[Callable[[], None]], Callable[[], None]]]
    dialog = cast(DialogFactory, dialog_factory)

    @dialog("Esecuzione Vision - Conferma")
    def _inner() -> None:
        apply_modal_css()

        try:
            data = load_workspace_yaml(slug)
        except Exception as exc:
            st.error(str(exc))
            if st.button("Chiudi", key="ft_modal_vision_close_error"):
                _clear_state()
                _st_rerun()
            return

        sections_in_file = data.get("sections") or {}
        default_state: dict[str, str] = {
            mapping_key: str(sections_in_file.get(mapping_key, "") or "") for _, mapping_key in _SECTION_MAPPING
        }
        state = st.session_state.setdefault(_SS_SECTIONS, dict(default_state))

        st.subheader("Prompt Vision - editor sezioni")
        st.caption("Origine: output/<workspace>/config/visionstatement.yaml")

        for label, key in _SECTION_MAPPING:
            with st.expander(label, expanded=(label == "Vision")):
                state[key] = st.text_area(
                    label="",
                    value=state.get(key, ""),
                    key=f"{_SS_SECTIONS}_{key}",
                    height=180,
                    label_visibility="collapsed",
                )

        with st.expander("Mostra prompt completo (anteprima)", expanded=False):
            tmp_data = dict(data)
            tmp_data["sections"] = dict(state)
            prompt_preview = build_prompt_from_yaml(tmp_data)
            st.code(prompt_preview, language="markdown")
            st.caption("Suggerimento: usa Ctrl+C per copiare il prompt.")

        col_cancel, col_save, col_run = st.columns([1, 1, 2])

        if col_cancel.button("Annulla", key="ft_modal_vision_cancel"):
            _clear_state()
            _st_rerun()

        if col_save.button("Salva", key="ft_modal_vision_save"):
            try:
                data["sections"] = dict(state)
                save_workspace_yaml(slug, data)
                st.success("Vision statement salvato in output/<workspace>/config/visionstatement.yaml.")
            except Exception as exc:
                st.error(f"Errore durante il salvataggio: {exc}")

        if col_run.button("Prosegui", key="ft_modal_vision_run", type="primary"):
            try:
                ctx = get_client_context(slug, require_drive_env=False)
                pdf_path = _ensure_workspace_pdf(ctx)
                tmp_data = dict(data)
                tmp_data["sections"] = dict(state)
                prompt = build_prompt_from_yaml(tmp_data)
                result_payload: dict[str, object] | None = None
                with st.spinner("Eseguo Vision..."):
                    try:
                        result_payload = provision_from_vision_with_config(
                            ctx,
                            logger=LOG,
                            slug=slug,
                            pdf_path=pdf_path,
                            model=get_vision_model(),
                            prepared_prompt=prompt,
                        )
                    except ConfigError as err:
                        if not _is_gate_error(err):
                            st.session_state[_SS_LAST_RESULT] = {"error": str(err)}
                            raise
                            result_payload = provision_from_vision_with_config(
                                ctx,
                                logger=LOG,
                                slug=slug,
                                pdf_path=pdf_path,
                                model=get_vision_model(),
                                prepared_prompt=prompt,
                            )
                st.session_state[_SS_LAST_RESULT] = result_payload
                st.success("Vision completata correttamente.")
                _clear_state()
                _st_rerun()
            except ConfigError as err:
                st.error(str(err))
            except Exception as exc:
                st.error(f"Errore Vision: {exc}")

    _inner()
