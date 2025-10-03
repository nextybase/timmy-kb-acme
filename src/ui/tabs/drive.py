from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence

import streamlit as st

from ui.clients_store import set_state
from ui.services.drive_runner import build_drive_from_mapping, download_raw_from_drive, emit_readmes_for_raw


class _ProgressFn(Protocol):
    def __call__(self, done: int, total: int, label: str) -> None:  # pragma: no cover
        ...


class _DownloadWithProgress(Protocol):
    def __call__(self, *, slug: str, on_progress: _ProgressFn) -> Sequence[Any]:  # pragma: no cover
        ...


# Proviamo a usare la variante con progress; fallback se non disponibile
download_raw_from_drive_with_progress: Optional[_DownloadWithProgress]
try:
    from ui.services.drive_runner import download_raw_from_drive_with_progress as _dl_with_progress

    download_raw_from_drive_with_progress = _dl_with_progress
except Exception:  # pragma: no cover
    download_raw_from_drive_with_progress = None


def render_drive_tab(*, log: Any, slug: str) -> None:
    """Render Google Drive raw flow.

    UI-only layer: no business-logic changes.
    """
    st.subheader("Google Drive: struttura e contenuti RAW")
    st.caption(
        "Crea/aggiorna la struttura su Drive a partire dal mapping rivisto, genera i README in "
        "`raw/` e scarica i PDF localmente. Tutti i passaggi sono idempotenti."
    )

    colA, colB = st.columns(2, gap="large")

    # 1) Crea/aggiorna struttura Drive
    with colA:
        if st.button(
            "1) Crea/aggiorna struttura su Drive",
            key="btn_drive_create",
            width="stretch",
            help=(
                "Crea/allinea la gerarchia su Drive dal mapping rivisto "
                "(cartella cliente -> raw/ -> sottocartelle). Operazione idempotente."
            ),
        ):
            try:
                progress_bar = st.progress(0)
                status_container = None
                status_placeholder = None
                status_api = getattr(st, "status", None)
                if callable(status_api):
                    try:
                        status_container = status_api("Inizializzazione...", expanded=False)
                    except Exception:
                        status_container = None
                if status_container is None:
                    status_placeholder = st.empty()
                    status_placeholder.write("Inizializzazione...")

                def _update_status(message: str) -> None:
                    nonlocal status_container, status_placeholder
                    if status_container is not None:
                        try:
                            status_container.update(label=message)
                            return
                        except Exception:
                            status_container = None
                    if status_placeholder is None:
                        status_placeholder = st.empty()
                    status_placeholder.write(message)

                def _cb(step: int, total: int, label: str) -> None:  # UI: callback unificato
                    pct = int(step * 100 / max(total, 1))
                    progress_bar.progress(pct)
                    _update_status(f"{pct}% · {label}")

                ids = build_drive_from_mapping(
                    slug=slug,
                    client_name=st.session_state.get("client_name", ""),
                    progress=_cb,
                )
                progress_bar.progress(100)
                _update_status("100% · Operazione completata")
                st.success("Struttura Drive aggiornata.")
                st.caption(f"IDs cartelle: {ids}")
                set_state(slug, "inizializzato")
                log.info({"event": "drive_structure_created", "slug": slug, "ids": ids})
            except FileNotFoundError as exc:
                st.error("Mapping non trovato.")
                st.caption("Apri Configurazione, salva il mapping rivisto e riprova.")
                st.caption(f"Dettaglio tecnico: {exc}")
            except Exception as exc:  # pragma: no cover
                st.error("Struttura Drive non aggiornata.")
                st.caption(f"Dettaglio tecnico: {exc}")

    # 2) Genera README
    with colB:
        if st.button(
            "2) Genera README in raw/",
            key="btn_drive_readmes",
            type="primary",
            width="stretch",
            help="Crea README introduttivi in ogni sottocartella di raw/ con istruzioni operative.",
        ):
            try:
                result = emit_readmes_for_raw(slug=slug, ensure_structure=True)
                st.success(f"README creati: {len(result)}")
                log.info({"event": "raw_readmes_uploaded", "slug": slug, "count": len(result)})
                st.session_state["drive_readmes_done"] = True
            except FileNotFoundError as exc:
                st.error("Mapping non trovato.")
                st.caption("Apri Configurazione, salva il mapping rivisto e riprova.")
                st.caption(f"Dettaglio tecnico: {exc}")
            except Exception as exc:  # pragma: no cover
                st.error("Generazione README non riuscita.")
                st.caption(f"Dettaglio tecnico: {exc}")

    # 3) Download PDF in raw/ (abilitato dopo README)
    if st.session_state.get("drive_readmes_done"):
        st.markdown("---")
        st.subheader("Download contenuti su raw/")
        c1, c2 = st.columns([1, 3])

        with c1:
            if st.button(
                "Scarica PDF da Drive in raw/",
                key="btn_drive_download_raw",
                width="stretch",
                help=("Scarica i PDF caricati nelle cartelle di raw/ su Drive verso la tua cartella " "raw/ locale."),
            ):
                try:
                    progress_bar = st.progress(0)
                    status = st.empty()
                    if download_raw_from_drive_with_progress is not None:

                        def _pcb(done: int, total: int, label: str) -> None:
                            pct = int((done * 100) / max(total, 1))
                            progress_bar.progress(pct)
                            status.write(f"{pct}% · {label}")

                        res = download_raw_from_drive_with_progress(slug=slug, on_progress=_pcb)
                    else:
                        status.write("0% · Preparazione download")
                        res = download_raw_from_drive(slug=slug)

                    progress_bar.progress(100)
                    status.write("100% · Download completato")
                    count = len(res) if hasattr(res, "__len__") else None
                    msg_tail = f" ({count} file)" if count is not None else ""
                    st.success(f"Download completato{msg_tail}.")
                    set_state(slug, "pronto")
                    log.info({"event": "drive_raw_downloaded", "slug": slug, "count": count})
                    st.session_state["raw_downloaded"] = True
                    st.session_state["raw_ready"] = True
                except Exception as exc:  # pragma: no cover
                    st.error("Download non riuscito.")
                    st.caption(f"Dettaglio tecnico: {exc}")

        with c2:
            st.write(
                "Dopo il download, puoi procedere agli step di **Semantica (RAW → BOOK)** per la "
                "conversione in Markdown e la generazione dei materiali di navigazione."
            )
