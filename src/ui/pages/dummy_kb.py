# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/dummy_kb.py
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from pipeline.beta_flags import is_beta_strict
from pipeline.context import validate_slug
from pipeline.docker_utils import check_docker_status
from pipeline.env_utils import get_int
from pipeline.logging_utils import get_structured_logger
from semantic.api import get_paths
from semantic.book_readiness import is_book_ready
from ui.chrome import render_chrome_then_require
from ui.errors import to_user_message
from ui.utils import get_slug, set_active_slug
from ui.utils.stubs import get_streamlit

st = get_streamlit()

REPO_ROOT = Path(__file__).resolve().parents[3]


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        payload, _ = decoder.raw_decode(text[idx:])
        if isinstance(payload, dict):
            return payload
        break
    raise RuntimeError("payload JSON non trovato")


def _render_health_panel(payload: dict[str, Any] | None) -> None:
    if not payload or not isinstance(payload, dict):
        st.error("Health payload mancante o non valido.")
        return
    health = payload.get("health")
    if not isinstance(health, dict):
        st.error("Health payload mancante o non valido.")
        return

    st.subheader("Health report")

    fields = {
        "status": health.get("status"),
        "mode": health.get("mode"),
        "vision_status": health.get("vision_status"),
        "fallback_used": health.get("fallback_used"),
        "raw_pdf_count": health.get("raw_pdf_count"),
        "tags_count": health.get("tags_count"),
        "mapping_valid": health.get("mapping_valid"),
        "readmes_count": health.get("readmes_count"),
    }
    st.table({k: [v] for k, v in fields.items() if v is not None})

    errors = health.get("errors")
    if isinstance(errors, list) and errors:
        st.error("Errori:")
        st.write(errors)

    checks = health.get("checks")
    if isinstance(checks, list) and checks:
        st.write("Checks:")
        st.write(checks)

    external_checks = health.get("external_checks")
    if isinstance(external_checks, dict) and external_checks:
        st.write("External checks:")
        st.json(external_checks)

    golden_pdf = health.get("golden_pdf")
    if isinstance(golden_pdf, dict) and golden_pdf:
        st.write("Golden PDF:")
        st.json(golden_pdf)


def _start_preview_and_show_link(ctx: Any) -> None:
    logger = get_structured_logger("ui.dummy.preview", context=ctx)
    with st.status("Avvio preview Docker...", expanded=False) as status_widget:
        try:
            from adapters.preview import start_preview as _start_preview
        except Exception as exc:
            status_widget.update(label="Preview non disponibile", state="error")
            st.error(f"Preview non disponibile: {exc}")
            return
        try:
            name = _start_preview(ctx, logger)
            st.session_state["preview_container"] = name
            status_widget.update(label=f"Preview avviata ({name}).", state="complete")
        except Exception as exc:
            title, body, caption = to_user_message(exc)
            status_widget.update(label="Errore avvio preview", state="error")
            st.error(title)
            if caption or body:
                st.caption(caption or body)
            return

    host_port = get_int("PREVIEW_PORT", 4000) or 4000
    preview_url = f"http://localhost:{host_port}"
    st.caption("Apri l'anteprima HonKit in un'altra scheda:")
    if hasattr(st, "link_button"):
        st.link_button("Apri anteprima HonKit", preview_url, type="primary")
    else:
        st.write(preview_url)


def _render_preview_after_success(slug: str, payload: dict[str, Any] | None) -> None:
    book_dir: Path | None = None
    if isinstance(payload, dict):
        paths = payload.get("paths")
        if isinstance(paths, dict):
            base = paths.get("base")
            if base:
                book_dir = Path(str(base)) / "book"
    if book_dir is None:
        try:
            book_dir = get_paths(slug)["book"]
        except Exception:
            book_dir = None
    if not book_dir or not is_book_ready(book_dir):
        return

    ctx = None
    try:
        from ui.utils.context_cache import get_client_context

        ctx = get_client_context(slug, require_env=False)
    except Exception:
        ctx = None
    if ctx is None:
        st.warning("Preview Docker non disponibile: contesto cliente non risolvibile.")
        return

    docker_ok, hint = check_docker_status()
    if not docker_ok:
        st.warning(f"Docker non attivo: {hint or 'avvia Docker e riprova.'}")
        if st.button("Attiva Docker e avvia preview", key="btn_dummy_preview_activate"):
            docker_ok, hint = check_docker_status()
            if not docker_ok:
                st.error(hint or "Docker non attivo: avvia Docker Desktop e riprova.")
                return
            _start_preview_and_show_link(ctx)
        return

    _start_preview_and_show_link(ctx)


def _run_brute_reset(slug: str, status_label: str) -> None:
    if slug != "dummy":
        st.error("Il reset manuale e' consentito solo per lo slug 'dummy'.")
        return
    cmd = [sys.executable, "-m", "tools.gen_dummy_kb", "--slug", slug, "--brute-reset"]
    st.caption("Esecuzione comando:")
    st.code(" ".join(shlex.quote(t) for t in cmd), language="bash")
    with st.status(status_label, expanded=True) as status_widget:
        try:
            result = subprocess.run(  # noqa: S603 - slug sanificato, shell disabilitata
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            status_widget.update(label="Reset in timeout (120s)", state="error")
            st.error("Reset non completato entro 120 secondi.")
            return
        except Exception as exc:
            status_widget.update(label="Errore reset", state="error")
            st.error(f"Impossibile avviare il reset: {exc}")
            return
        if result.stdout:
            with st.expander("Output CLI", expanded=False):
                st.text(result.stdout)
        if result.stderr:
            with st.expander("Errori CLI", expanded=False):
                st.text(result.stderr)
        if result.returncode == 0:
            status_widget.update(label="Reset completato", state="complete")
            st.success("Workspace dummy eliminato (solo locale).")
        else:
            status_widget.update(label=f"Reset fallito (codice {result.returncode})", state="error")
            st.error("Reset manuale non riuscito. Verifica i dettagli.")


def _run_and_render(slug: str, cmd: list[str]) -> None:
    st.caption("Esecuzione comando:")
    st.code(" ".join(shlex.quote(t) for t in cmd), language="bash")
    timeout_seconds = 120
    with st.status(f"Genero dataset dummy per '{slug}'", expanded=True) as status_widget:
        try:
            result = subprocess.run(  # noqa: S603 - slug sanificato, shell disabilitata
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            status_widget.update(label="CLI in timeout (120s)", state="error")
            st.error(
                "Vision non ha completato entro 120 secondi. Interrompo senza fallback automatico. "
                "Riprova con l'opzione esplicita '--no-vision' se vuoi saltare la Vision."
            )
            return
        except Exception as exc:
            status_widget.update(label="Errore di esecuzione CLI", state="error")
            st.error(f"Impossibile avviare lo script: {exc}")
            return

        payload = None
        payload_error = None
        if result.stdout:
            try:
                payload = _extract_json_payload(result.stdout)
            except Exception as exc:
                payload_error = str(exc)
            with st.expander("Output CLI", expanded=False):
                st.text(result.stdout)
        if result.stderr:
            with st.expander("Errori CLI", expanded=False):
                st.text(result.stderr)

        if payload_error:
            st.error(f"Health payload non valido: {payload_error}")
        else:
            _render_health_panel(payload)

        if result.returncode == 0:
            status_widget.update(label="Dummy generato correttamente.", state="complete")
            st.toast("Dataset dummy creato. Verifica clients_db/output per i dettagli.")
            st.success("Operazione completata.")
            _render_preview_after_success(slug, payload)
        else:
            status_widget.update(label=f"CLI terminata con codice {result.returncode}", state="error")
            st.error("La generazione della Dummy KB non e' andata a buon fine.")

    st.divider()


def main() -> None:
    if is_beta_strict():
        st.error(
            "Dummy KB disabilitata in Beta strict-only. "
            "Usa il tooling fuori runtime o disattiva TIMMY_BETA_STRICT per ambienti non garantiti.",
        )
        return
    set_active_slug("dummy", persist=False, update_query=True)
    render_chrome_then_require(
        allow_without_slug=True,
        title="Tools > Dummy KB",
        subtitle="Generazione e diagnosi della Dummy KB (slug fisso: dummy).",
    )
    slug = (get_slug() or "dummy").strip().lower() or "dummy"
    try:
        validate_slug(slug)
    except Exception as exc:
        st.error(f"Slug non valido: {exc}")
        return
    set_active_slug(slug, persist=True, update_query=False)

    script = (REPO_ROOT / "tools" / "gen_dummy_kb.py").resolve()
    if not script.exists():
        st.error(f"Script CLI non trovato: {script}")
        return

    st.subheader("Generazione Dummy KB")
    st.caption("Lo slug e' fissato a 'dummy' per questa pagina tools.")

    no_drive = st.checkbox("Disabilita Drive", value=False, help="Salta provisioning/upload su Google Drive")
    no_vision = st.checkbox(
        "Disabilita Vision (usa fallback semantic basico)",
        value=False,
        help="Salta Vision; genera artefatti minimi senza chiamare il modello.",
    )
    no_semantic = st.checkbox(
        "Disabilita Semantic",
        value=False,
        help="Salta la fase Semantic (non scrive artefatti semantic/*).",
    )
    no_enrichment = st.checkbox(
        "Disabilita Enrichment",
        value=False,
        help="Salta l'arricchimento (no modifica artefatti di enrichment).",
    )
    no_preview = st.checkbox(
        "Disabilita Preview",
        value=False,
        help="Salta la preview locale (nessun output preview).",
    )
    deep_testing = st.checkbox(
        "Attiva testing profondo",
        value=False,
        help=(
            "Forza hard check reali (Vision/Drive) e validazioni complete; "
            "fallisce se credenziali/quota/permessi non sono pronti."
        ),
    )
    st.caption(
        "Il deep testing usa Vision/Drive reali e puo' fallire se i secrets/permessi non sono pronti. "
        "Verifica la pagina Secrets Healthcheck prima di attivarlo."
    )

    cleanup = st.button("Reset dummy (solo locale)", type="secondary")
    proceed = st.button("Prosegui", type="primary")
    if cleanup:
        _run_brute_reset(slug, "Reset dummy in corso.")
    if proceed:
        cmd = [sys.executable, "-m", "tools.gen_dummy_kb", "--slug", slug]
        if no_drive:
            cmd.append("--no-drive")
        if no_vision:
            cmd.append("--no-vision")
        if no_semantic:
            cmd.append("--no-semantic")
        if no_enrichment:
            cmd.append("--no-enrichment")
        if no_preview:
            cmd.append("--no-preview")
        if deep_testing:
            cmd.append("--deep-testing")
        _run_and_render(slug, cmd)


if __name__ == "__main__":
    main()


__all__ = ["main"]
