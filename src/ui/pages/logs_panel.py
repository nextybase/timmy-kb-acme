#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/ui/pages/logs_panel.py
"""
Dashboard dei log globali della UI + pannello osservabilità.

- Vista globale sui log Streamlit salvati in `.timmy_kb/logs/`.
- Sezione di controllo per gli strumenti di osservabilità:
  - preferenza uso stack esterno (Grafana/Loki)
  - preferenza tracing OpenTelemetry
  - redazione log (maschera ID / token sensibili)
  - livello di verbosity log (DEBUG/INFO/WARNING/ERROR)

Questa pagina NON richiede slug attivo: opera a livello globale.
"""


from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

import requests

from pipeline.log_viewer import LogFileInfo, get_global_logs_dir, list_global_log_files, load_log_sample
from pipeline.logging_utils import get_structured_logger
from pipeline.observability_config import (
    ObservabilitySettings,
    get_grafana_errors_dashboard_url,
    get_grafana_logs_dashboard_url,
    get_grafana_url,
    get_observability_settings,
    get_tracing_state,
    update_observability_settings,
)
from pipeline.tracing import start_phase_span, start_root_trace

try:  # Prefer local tool under repo root
    from tools import observability_stack
except Exception:  # pragma: no cover
    observability_stack = None

if observability_stack is None:  # pragma: no cover
    try:
        import importlib.util

        repo_root = Path(__file__).resolve().parents[2]
        obs_path = repo_root / "tools" / "observability_stack.py"
        spec = importlib.util.spec_from_file_location("observability_stack", obs_path)
        if spec is not None and spec.loader is not None:
            observability_stack = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(observability_stack)
    except Exception:
        observability_stack = None

StackAction = Callable[[], tuple[bool, str]]
start_observability_stack: StackAction | None = getattr(observability_stack, "start_observability_stack", None)
stop_observability_stack: StackAction | None = getattr(observability_stack, "stop_observability_stack", None)
from ui.chrome import render_chrome_then_require
from ui.utils.slug import get_active_slug
from ui.utils.stubs import get_streamlit

st = get_streamlit()


def _safe_link_button(label: str, url: str, **kwargs: Any) -> bool:
    """Fallback compatto quando l'API `link_button` non è disponibile."""
    link_btn = getattr(st, "link_button", None)
    if callable(link_btn):
        try:
            return bool(link_btn(label, url, **kwargs))
        except Exception:
            pass
    button = getattr(st, "button", None)
    if callable(button):
        try:
            return bool(button(label, **kwargs))
        except Exception:
            pass
    return False


def _safe_success(message: str, **kwargs: Any) -> bool:
    """Mostra messaggio di successo anche con stub limitato."""
    succ = getattr(st, "success", None)
    if callable(succ):
        try:
            succ(message, **kwargs)
            return True
        except Exception:
            pass
    write_fn = getattr(st, "write", None)
    if callable(write_fn):
        write_fn(message)
        return True
    return False


def _matches_text(row: Dict[str, Any], query: str) -> bool:
    """Match case-insensitive su message/event/slug/file_path."""
    if not query:
        return True
    q = query.lower()
    for key in ("event", "message", "slug", "file_path"):
        val = row.get(key)
        if isinstance(val, str) and q in val.lower():
            return True
    return False


def _divider() -> None:  # pragma: no cover - UI sugar
    divider_fn = getattr(st, "divider", None)
    if divider_fn:
        divider_fn()
    else:
        write_fn = getattr(st, "write", None) or (lambda *_args, **_kwargs: None)
        write_fn("---")


def _is_docker_available() -> bool:
    """Semplice check per capire se il daemon Docker è attivo."""
    override = os.getenv("TIMMY_DOCKER_AVAILABLE")
    if override is not None:
        return override.lower() in {"1", "true", "yes", "on"}
    unix_sock = Path("/var/run/docker.sock")
    if unix_sock.exists():
        return True
    pipe = Path(r"\\.\pipe\docker_engine")
    return pipe.exists()


def _check_grafana_reachable(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """HEAD rapido su Grafana per mostrare uno stato online/offline."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, f"schema non supportato '{parsed.scheme}'"
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        status = f"{resp.status_code} {resp.reason}"
        if resp.ok or resp.status_code == 405:
            return True, status
        return False, status
    except requests.RequestException as exc:
        return False, str(exc)


def _render_grafana_block(
    *,
    settings: "ObservabilitySettings",
    toggle: Callable[..., bool],
) -> tuple[bool, bool, bool, str]:
    """
    Rende la sezione Grafana/dashboards di osservabilità e restituisce:
    - stack_enabled: nuovo valore del toggle "Osservabilità esterna"
    - docker_available: bool da _is_docker_available()
    - grafana_reachable: bool da _check_grafana_reachable()
    - docker_cmd: stringa di comando Docker suggerito
    """
    docker_available = _is_docker_available()
    docker_cmd = "docker compose --env-file ./.env -f observability/docker-compose.yaml"
    stack_enabled = toggle(
        "Osservabilità esterna (Grafana/Loki)",
        value=settings.stack_enabled,
        help=(
            "Indica che vuoi usare lo stack di osservabilità esterno. "
            "Questa preferenza può essere letta dalla pagina Admin o dagli "
            "script di deploy per avviare lo stack Grafana/Loki."
        ),
    )
    grafana_url = get_grafana_url()
    st.caption(f"URL Grafana configurato (env `TIMMY_GRAFANA_URL` o default): `{grafana_url}`")
    grafana_reachable, reach_msg = (
        _check_grafana_reachable(grafana_url)
        if docker_available
        else (False, "Docker non attivo, abilita Docker prima di controllare Grafana.")
    )
    if stack_enabled:
        _safe_link_button("Apri Grafana", grafana_url, type="secondary")
        status_icon = "🟢" if grafana_reachable else "🔴"
        st.caption(f"Grafana {status_icon} ({reach_msg}).")
    else:
        st.caption("Abilita 'Osservabilità esterna' per aprire Grafana e le dashboard collegate.")
    return stack_enabled, docker_available, grafana_reachable, docker_cmd


def _render_stack_controls(
    *,
    docker_available: bool,
    docker_cmd: str,
    stack_enabled: bool,
    grafana_reachable: bool,
    action_button: Callable[..., bool],
    start_stack: StackAction | None,
    stop_stack: StackAction | None,
) -> None:
    """
    Rende i controlli Start/Stop stack e i messaggi informativi
    relativi allo stato dello stack di osservabilità.
    """
    if not docker_available:
        st.info(
            "Docker non attivo: avvia il daemon prima di usare i pulsanti Grafana."
            f" Esempio: `{docker_cmd} up -d` nella root del progetto."
        )
        return

    stack_ready = stack_enabled and grafana_reachable
    if stack_ready:
        if action_button("Stop Stack"):
            if stop_stack is None:
                st.warning("Stop Stack non disponibile: modulo observability_stack non importato.")
            else:
                ok, msg = stop_stack()
                if ok:
                    _safe_success(f"Stack fermato: {msg}")
                else:
                    st.warning(f"Errore Stop Stack: {msg}")
        st.caption("Stack attivo - usa Stop Stack per spegnere temporaneamente il monitoring.")
    else:
        if action_button("Start Stack"):
            if start_stack is None:
                st.warning("Start Stack non disponibile: modulo observability_stack non importato.")
            else:
                ok, msg = start_stack()
                if ok:
                    _safe_success(f"Stack avviato: {msg}")
                else:
                    st.warning(f"Errore Start Stack: {msg}")
        st.caption("Stack inattivo - avvialo con Start Stack o verifica lo stato del daemon.")


def _render_tracing_controls(
    *,
    settings: ObservabilitySettings,
    toggle: Callable[..., bool],
    action_button: Callable[..., bool],
    logger: logging.Logger,
) -> bool:
    """
    Rende la sezione di controllo per il tracing OpenTelemetry
    e ritorna il nuovo valore di tracing_enabled.
    """
    tracing_enabled = toggle(
        "Tracing OpenTelemetry (OTEL)",
        value=settings.tracing_enabled,
        help=(
            "Abilita il tracing OTEL nella configurazione. "
            "Per essere effettivo è necessario configurare anche "
            "la variabile d'ambiente TIMMY_OTEL_ENDPOINT."
        ),
    )
    otel_env_present = bool(os.getenv("TIMMY_OTEL_ENDPOINT"))
    if otel_env_present:
        _safe_success("Endpoint OTEL configurato (TIMMY_OTEL_ENDPOINT è impostata).")
    else:
        st.info(
            "Nessun endpoint OTEL configurato: il tracing è solo una preferenza "
            "finché non imposti TIMMY_OTEL_ENDPOINT."
        )
    state = get_tracing_state()
    st.caption(
        f"Tracing – preferenze: {'ON' if state.enabled_in_prefs else 'OFF'}, "
        f"endpoint: {'OK' if state.endpoint_present else 'MANCANTE'}, "
        f"librerie OTEL: {'OK' if state.otel_installed else 'NON INSTALLATE'}."
    )
    if state.enabled_in_prefs and not state.effective_enabled:
        st.warning(
            "Tracing attivato nelle preferenze ma non operativo: "
            "configura TIMMY_OTEL_ENDPOINT e installa le librerie OpenTelemetry."
        )
    if action_button("Verifica tracing"):
        env = os.getenv("TIMMY_ENV", "dev")
        with start_root_trace(
            "diagnostic",
            slug=None,
            run_id=None,
            entry_point="ui",
            env=env,
            trace_kind="diagnostic",
        ):
            with start_phase_span(
                "observability.tracing.doctor",
                slug=None,
                run_id=None,
                trace_kind="diagnostic",
            ):
                logger.info(
                    "observability.tracing.test_span_emitted",
                    extra={"trace_kind": "diagnostic"},
                )
        st.info(
            "Span diagnostico emesso. Se Grafana/Tempo sono configurati, "
            "dovresti vederlo in Tempo filtrando per trace_kind=diagnostic negli ultimi minuti."
        )
    return tracing_enabled


def _render_observability_controls() -> None:
    """
    Pannello di controllo per gli strumenti di osservabilità.

    Non modifica il comportamento runtime immediato della UI,
    ma scrive/legge le preferenze globali da `observability.yaml`,
    che possono essere usate dagli orchestratori CLI e da altre
    componenti per configurare logging e tracing.
    """
    st.markdown("### Strumenti di osservabilità")

    settings = get_observability_settings()
    logger = get_structured_logger("ui.logs_panel")

    col1, col2 = st.columns([1, 1])

    def _fallback_toggle(*_args: Any, value: bool = False, **_kwargs: Any) -> bool:
        return value

    toggle = getattr(st, "toggle", None) or getattr(st, "checkbox", None) or _fallback_toggle
    success = getattr(st, "success", None) or (lambda *_args, **_kwargs: None)
    action_button = getattr(st, "button", None) or (lambda *_args, **_kwargs: False)

    with col1:
        stack_enabled, docker_available, reachable, docker_cmd = _render_grafana_block(
            settings=settings,
            toggle=toggle,
        )

    slug = get_active_slug()
    logs_dashboard_url = get_grafana_logs_dashboard_url(slug=slug)
    errors_dashboard_url = get_grafana_errors_dashboard_url(slug=slug)
    col_logs, col_errors = st.columns([1, 1])
    with col_logs:
        if logs_dashboard_url:
            _safe_link_button("Apri dashboard log", logs_dashboard_url, type="secondary")
        else:
            st.caption("Configura `TIMMY_GRAFANA_LOGS_UID` per mostrare il dashboard log.")
    with col_errors:
        if errors_dashboard_url:
            _safe_link_button("Apri dashboard errori", errors_dashboard_url, type="secondary")
        else:
            st.caption("Configura `TIMMY_GRAFANA_ERRORS_UID` per mostrare il dashboard alert/errori.")
    st.caption(f"Slug attivo: {slug or 'nessuno'}")
    st.caption("")
    _render_stack_controls(
        docker_available=docker_available,
        docker_cmd=docker_cmd,
        stack_enabled=stack_enabled,
        grafana_reachable=reachable,
        action_button=action_button,
        start_stack=start_observability_stack,
        stop_stack=stop_observability_stack,
    )

    with col2:
        tracing_enabled = _render_tracing_controls(
            settings=settings,
            toggle=toggle,
            action_button=action_button,
            logger=logger,
        )

    col3, col4 = st.columns([1, 1])
    with col3:
        redact_logs = toggle(
            "Redazione log (maschera ID / token)",
            value=settings.redact_logs,
            help=(
                "Se attivo, i logger strutturati applicano i filtri di redazione "
                "per mascherare ID, token e valori sensibili nei log."
            ),
        )
    with col4:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        try:
            current_index = levels.index(settings.log_level.upper())
        except ValueError:
            current_index = 1  # fallback INFO
        log_level = st.selectbox(
            "Verbosity log CLI/UI",
            options=levels,
            index=current_index,
            help=(
                "Livello di default per i logger strutturati degli orchestratori. "
                "DEBUG è molto verboso, ERROR mostra solo errori."
            ),
        )

    with st.expander("Come usare Grafana/OTEL da qui", expanded=False):
        st.markdown(
            """
1. **Avvia lo stack di osservabilità** (Grafana/Loki/Promtail, e Tempo se presente) da shell
   oppure dalla pagina *Admin* se sono disponibili i bottoni Docker.
2. Imposta `TIMMY_GRAFANA_URL` e, se vuoi tracing, `TIMMY_OTEL_ENDPOINT` nell'ambiente
   in cui giri CLI e UI.
3. Usa i toggle qui sopra per:
   - indicare che lo stack è atteso (*Osservabilità esterna*),
   - attivare il tracing OTEL,
   - controllare redazione e livello di log.
4. Da qui puoi aprire Grafana con **Apri Grafana** e usare le dashboard
   per filtrare log ed errori per cliente (`slug`) e fase.
"""
        )

    # Se qualcosa è cambiato, persisti le nuove impostazioni
    if (
        stack_enabled != settings.stack_enabled
        or tracing_enabled != settings.tracing_enabled
        or redact_logs != settings.redact_logs
        or log_level != settings.log_level
    ):
        new_settings = update_observability_settings(
            stack_enabled=stack_enabled,
            tracing_enabled=tracing_enabled,
            redact_logs=redact_logs,
            log_level=log_level,
        )
        logger.info(
            "ui.observability.settings_updated",
            extra={
                "stack_enabled": bool(new_settings.stack_enabled),
                "tracing_enabled": bool(new_settings.tracing_enabled),
                "redact_logs": bool(new_settings.redact_logs),
                "log_level": new_settings.log_level,
            },
        )
        success("Impostazioni di osservabilità aggiornate.")
        st.caption(
            f"stack_enabled={new_settings.stack_enabled}, "
            f"tracing_enabled={new_settings.tracing_enabled}, "
            f"redact_logs={new_settings.redact_logs}, "
            f"log_level={new_settings.log_level}"
        )


def _render_global_logs_view() -> None:
    """Viewer dei log globali UI (versione estesa dell'implementazione originale)."""
    st.markdown("### Log globali UI (`.timmy_kb/logs/`)")
    st.caption(
        "Esplora i log globali della UI Streamlit salvati in `.timmy_kb/logs/`. "
        "La pagina non richiede uno slug attivo."
    )

    log_dir = get_global_logs_dir()
    files: List[LogFileInfo] = list_global_log_files(max_files=20)

    if not files:
        st.info("Nessun file di log trovato. La cartella dei log globali attesa è:")
        st.code(str(log_dir))
        st.caption(
            "Apri l'app di onboarding, genera un po' di traffico (es. selezione cliente) "
            "e verifica che il logging sia correttamente configurato."
        )
        return

    with st.expander("Dettagli sui log", expanded=False):
        st.markdown(
            "- I log globali della UI sono salvati in "
            f"`{log_dir}`.\n"
            "- Ogni riga segue il formato strutturato definito in `logging_utils`, con "
            "metadati `key=value` (`slug`, `run_id`, `event`, `phase`, `file_path`, ...).\n"
            "- Questa dashboard mostra un estratto delle ultime righe per analisi rapide."
        )

    col_file, col_rows = st.columns([2, 1])
    with col_file:
        selected = st.selectbox(
            "File di log",
            options=files,
            format_func=lambda info: f"{info.name} — {info.human_mtime}",
        )
    with col_rows:
        max_rows = st.slider(
            "Righe recenti",
            min_value=100,
            max_value=2000,
            step=100,
            value=500,
            help="Numero massimo di righe recenti da caricare dal file selezionato.",
        )

    rows = load_log_sample(selected.path, max_lines=max_rows)
    if not rows:
        st.warning(
            "Il file di log esiste ma non contiene righe parsate nel formato atteso. "
            "Verifica la configurazione del logger strutturato."
        )
        return

    levels = sorted({r.get("level") for r in rows if r.get("level")})
    col_level, col_text = st.columns([1, 2])
    with col_level:
        selected_levels = st.multiselect(
            "Livelli",
            options=levels,
            default=levels,
            help="Filtra per livello log (INFO, WARNING, ERROR, ...).",
        )
    with col_text:
        text_filter = st.text_input(
            "Filtro testo",
            placeholder="Cerca in evento, messaggio, slug o percorso file...",
        )

    filtered = [
        r for r in rows if (not selected_levels or r.get("level") in selected_levels) and _matches_text(r, text_filter)
    ]

    st.caption(f"Mostrando {len(filtered)} eventi (su {len(rows)} righe parsate) " f"dal file `{selected.name}`.")
    st.dataframe(filtered)


def main() -> None:
    # Chrome Admin: slug non richiesto
    render_chrome_then_require(
        allow_without_slug=True,
        title="Log dashboard",
        subtitle="Pannello di controllo per log e osservabilità (.timmy_kb/logs + Grafana/OTEL).",
    )

    st.subheader("Log dashboard")

    # 1) Strumenti di osservabilità (preferenze globali)
    _render_observability_controls()

    _divider()

    # 2) Viewer log globali UI
    _render_global_logs_view()


if __name__ == "__main__":  # pragma: no cover - per debug manuale
    main()
