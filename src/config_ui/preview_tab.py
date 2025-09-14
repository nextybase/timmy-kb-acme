from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Solo per type-checking; evita import runtime e side-effects
    from pipeline.context import ClientContext


def _docker_safe(name: Optional[str]) -> str:
    s = (name or "").strip()
    if not s:
        return s
    s = re.sub(r"[^a-zA-Z0-9_.-]", "-", s)
    return s.strip("-._") or s


def _default_container(slug_val: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (slug_val or "kb")).strip("-") or "kb"
    return f"gitbook-{safe}"


def render_preview_controls(
    *,
    st: Any,
    context: "ClientContext",
    log: logging.Logger,
    slug: str,
) -> None:
    """
    Controlli Preview Docker (HonKit), estratti da onboarding_ui.py.

    Importa gli adapter in modo lazy per evitare dipendenze hard a import-time.
    """
    # Import runtime degli adapter (possono non essere disponibili)
    try:
        from adapters.preview import start_preview as _start_preview, stop_preview as _stop_preview

        start_preview: Optional[Callable[..., str]] = _start_preview
        stop_preview: Optional[Callable[..., None]] = _stop_preview
    except Exception:
        start_preview = None
        stop_preview = None

    running = bool(st.session_state.get("sem_preview_container"))
    pill = "<span class='pill on'>ON</span>" if running else "<span class='pill off'>OFF</span>"
    st.markdown(f"**Preview Docker:** {pill}", unsafe_allow_html=True)
    st.markdown("**4) Preview Docker (HonKit)**")

    with st.container(border=True):
        preview_port = st.number_input(
            "Porta preview", min_value=1, max_value=65535, value=4000, step=1, key="inp_sem_port"
        )

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
                    assert start_preview is not None  # per mypy
                    cname = start_preview(
                        context,
                        log,
                        port=int(preview_port),
                        container_name=st.session_state.get("sem_container_name"),
                    )
                    st.session_state["sem_preview_container"] = cname
                    url = f"http://127.0.0.1:{int(preview_port)}"
                    st.success(f"Preview avviata su {url} (container: {cname})")
                    log.info(
                        {
                            "event": "preview_started",
                            "slug": slug,
                            "run_id": st.session_state.get("run_id"),
                            "port": int(preview_port),
                            "container": cname,
                        }
                    )
                except Exception as e:
                    msg = str(e)
                    if any(
                        k in msg.lower()
                        for k in ("docker", "daemon", "not running", "cannot connect")
                    ):
                        st.warning(
                            "Docker non risulta attivo. Avvia Docker Desktop e riprova ad avviare la preview."
                        )
                        log.warning("Preview non avviata: Docker non attivo", extra={"error": msg})
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
                    assert stop_preview is not None  # per mypy
                    cname = st.session_state.get("sem_preview_container")
                    stop_preview(log, container_name=cname)
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
                except Exception as e:
                    st.exception(e)
