# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/tabs/finance.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ui.utils.streamlit_fragments import show_error_with_details


def _resolve_base_dir(slug: str, log: Optional[logging.Logger] = None) -> Path:
    """Determina la base_dir del workspace cliente privilegiando ClientContext.

    ClientContext è lo SSoT per i path: in caso di indisponibilità si segnala l'errore.
    """
    error_msg = (
        "ClientContext non disponibile. Esegui " "pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
    )

    try:
        from pipeline.context import ClientContext  # import lazy
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(error_msg) from exc

    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception as exc:
        raise RuntimeError(error_msg) from exc

    base_dir = getattr(ctx, "base_dir", None)
    if isinstance(base_dir, Path):
        return base_dir

    raw_dir = getattr(ctx, "raw_dir", None)
    if isinstance(raw_dir, Path):
        return raw_dir.parent

    raise RuntimeError(error_msg)


def render_finance_tab(*, st: Any, log: logging.Logger, slug: str) -> None:
    """Tab Finanza (CSV → finance.db), estratta da onboarding_ui.py.

    Dipendenze runtime:
      - finance.api.import_csv
      - finance.api.summarize_metrics
      - pipeline.context.ClientContext (per i path del workspace)
    """
    # Import lazy (evita side-effects a import-time del modulo)
    from finance.api import import_csv as fin_import_csv
    from finance.api import summarize_metrics as fin_summarize

    # Scrittura sicura e guardie path obbligatorie
    try:
        from pipeline.file_utils import safe_write_bytes
        from pipeline.path_utils import ensure_within
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Dipendenze di I/O sicuro non disponibili") from exc

    st.subheader("Finanza (CSV → finance.db)")
    st.caption("Ingestione opzionale di metriche numeriche in un DB SQLite separato (`semantic/finance.db`).")

    colA, colB = st.columns([1, 1], gap="large")

    # ——————————————————————————————————————————————————————————
    # Colonna A: uploader + import
    # ——————————————————————————————————————————————————————————
    with colA:
        # Base dir coerente con ClientContext (override inclusi)
        base_dir: Path = _resolve_base_dir(slug, log)

        file = st.file_uploader(
            "Carica CSV: metric, period, value, [unit], [currency], [canonical_term]",
            type=["csv"],
            accept_multiple_files=False,
        )
        st.caption("Schema CSV: metric, period, value, [unit], [currency], [canonical_term]")
        if st.button(
            "Importa in finance.db",
            key="btn_fin_import",
            width="stretch",
            disabled=(file is None),
        ):
            if file is None:
                st.warning("Seleziona prima un file CSV.")
            else:
                sem_dir: Path = base_dir / "semantic"
                ensure_within(base_dir, sem_dir)
                sem_dir.mkdir(parents=True, exist_ok=True)

                tmp_name = f"tmp-finance-{st.session_state.get('run_id','run')}.csv"
                tmp_csv = sem_dir / tmp_name
                ensure_within(sem_dir, tmp_csv)

                data: bytes = file.read() if file is not None else b""
                try:
                    # Scrittura atomica e valida rispetto ai confini
                    safe_write_bytes(tmp_csv, data, atomic=True)

                    # Import nel DB e messaggistica
                    res: Dict[str, object] = fin_import_csv(base_dir, tmp_csv)
                    st.success(
                        "Import OK - righe: {rows}  in {db}".format(
                            rows=res.get("rows", 0),
                            db=res.get("db", str(sem_dir / "finance.db")),
                        )
                    )
                    if log:
                        log.info({"event": "finance_import_ok", "slug": slug, "rows": res.get("rows")})
                except Exception as e:  # pragma: no cover - mostrato in UI
                    show_error_with_details(
                        log,
                        "Import CSV non riuscito. Controlla i log per i dettagli.",
                        e,
                        event="ui.finance.import_failed",
                        extra={"slug": slug},
                    )
                finally:
                    # Cleanup deterministico anche in caso d'errore
                    try:
                        tmp_csv.unlink(missing_ok=True)
                    except Exception:
                        # Non interrompe il flusso UI
                        pass

    # ——————————————————————————————————————————————————————————
    # Colonna B: riepilogo metriche
    # ——————————————————————————————————————————————————————————
    with colB:
        try:
            base_dir = _resolve_base_dir(slug, log)
            summary: List[tuple[str, int]] = fin_summarize(base_dir)
            if summary:
                st.caption("Metriche presenti:")
                st.table(
                    {
                        "metric": [m for m, _ in summary],
                        "osservazioni": [n for _, n in summary],
                    }
                )
            else:
                st.info("Nessuna metrica importata al momento.")
        except Exception as e:  # pragma: no cover - mostrato in UI
            show_error_with_details(
                log,
                "Impossibile mostrare le metriche importate. Controlla i log per i dettagli.",
                e,
                event="ui.finance.summary_failed",
                extra={"slug": slug},
            )
