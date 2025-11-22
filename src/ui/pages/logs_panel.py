#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/ui/pages/logs_panel.py
"""
Dashboard dei log globali della UI + pannello osservabilità.

- Vista globale sui log Streamlit salvati in `.timmykb/logs/`.
- Sezione di controllo per gli strumenti di osservabilità:
  - preferenza uso stack esterno (Grafana/Loki)
  - preferenza tracing OpenTelemetry
  - redazione log (maschera ID / token sensibili)
  - livello di verbosity log (DEBUG/INFO/WARNING/ERROR)

Questa pagina NON richiede slug attivo: opera a livello globale.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from pipeline.log_viewer import LogFileInfo, get_global_logs_dir, list_global_log_files, load_log_sample
from pipeline.logging_utils import get_structured_logger
from pipeline.observability_config import get_grafana_url, load_observability_settings, update_observability_settings
from ui.chrome import render_chrome_then_require
from ui.utils.stubs import get_streamlit

st = get_streamlit()


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


def _render_observability_controls() -> None:
    """
    Pannello di controllo per gli strumenti di osservabilità.

    Non modifica il comportamento runtime immediato della UI,
    ma scrive/legge le preferenze globali da `observability.yaml`,
    che possono essere usate dagli orchestratori CLI e da altre
    componenti per configurare logging e tracing.
    """
    st.markdown("### Strumenti di osservabilità")

    settings = load_observability_settings()
    logger = get_structured_logger("ui.logs_panel")

    col1, col2 = st.columns([1, 1])

    def _fallback_toggle(*_args: Any, value: bool = False, **_kwargs: Any) -> bool:
        return value

    toggle = getattr(st, "toggle", None) or getattr(st, "checkbox", None) or _fallback_toggle
    success = getattr(st, "success", None) or (lambda *_args, **_kwargs: None)
    with col1:
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
        if stack_enabled:
            st.link_button("Apri Grafana", grafana_url, type="secondary")

    with col2:
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
            st.success("Endpoint OTEL configurato (TIMMY_OTEL_ENDPOINT è impostata).")
        else:
            st.info(
                "Nessun endpoint OTEL configurato: il tracing è solo una preferenza "
                "finché non imposti TIMMY_OTEL_ENDPOINT."
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
    st.markdown("### Log globali UI (`.timmykb/logs/`)")
    st.caption(
        "Esplora i log globali della UI Streamlit salvati in `.timmykb/logs/`. "
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
        subtitle="Pannello di controllo per log e osservabilità (.timmykb/logs + Grafana/OTEL).",
    )

    st.subheader("Log dashboard")

    # 1) Strumenti di osservabilità (preferenze globali)
    _render_observability_controls()

    _divider()

    # 2) Viewer log globali UI
    _render_global_logs_view()


if __name__ == "__main__":  # pragma: no cover - per debug manuale
    main()
