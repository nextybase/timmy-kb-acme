from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from finance.api import (
    import_csv as fin_import_csv,
    summarize_metrics as fin_summarize,
)


def render_finance_tab(*, st: Any, log: logging.Logger, slug: str) -> None:
    """
    Tab Finanza (CSV → finance.db), estratta da onboarding_ui.py.

    Dipendenze runtime:
      - finance.api.import_csv
      - finance.api.summarize_metrics
      - semantic.api.get_paths
    """
    # Import lazy (evita side-effects a import-time del modulo)
    from semantic.api import get_paths as sem_get_paths

    # Opzionale: scrittura atomica se disponibile
    try:
        from pipeline.file_utils import safe_write_bytes
    except Exception:
        safe_write_bytes = None  # fallback

    st.subheader("Finanza (CSV → finance.db)")
    st.caption(
        "Ingestione opzionale di metriche numeriche in un DB SQLite separato (`semantic/finance.db`)."
    )

    colA, colB = st.columns([1, 1], gap="large")

    # ——————————————————————————————————————————————————————————
    # Colonna A: uploader + import
    # ——————————————————————————————————————————————————————————
    with colA:
        file = st.file_uploader(
            "Carica CSV: metric, period, value, [unit], [currency], [note], [canonical_term]",
            type=["csv"],
            accept_multiple_files=False,
        )
        if st.button(
            "Importa in finance.db",
            key="btn_fin_import",
            use_container_width=True,
            disabled=(file is None),
        ):
            try:
                base = sem_get_paths(slug)["base"]  # Path del workspace cliente
                sem_dir: Path = base / "semantic"
                sem_dir.mkdir(parents=True, exist_ok=True)

                tmp_name = f"tmp-finance-{st.session_state.get('run_id','run')}.csv"
                tmp_csv = sem_dir / tmp_name

                data: bytes = file.read() if file is not None else b""
                if safe_write_bytes is not None:
                    safe_write_bytes(tmp_csv, data, atomic=True)
                else:
                    tmp_csv.write_bytes(data)

                res: Dict[str, object] = fin_import_csv(base, tmp_csv)
                st.success(
                    "Import OK - righe: {rows}  in {db}".format(
                        rows=res.get("rows", 0),
                        db=res.get("db", str(sem_dir / "finance.db")),
                    )
                )
                log.info({"event": "finance_import_ok", "slug": slug, "rows": res.get("rows")})

                try:
                    tmp_csv.unlink(missing_ok=True)
                except Exception:
                    pass
            except Exception as e:  # pragma: no cover - mostrato in UI
                st.exception(e)

    # ——————————————————————————————————————————————————————————
    # Colonna B: riepilogo metriche
    # ——————————————————————————————————————————————————————————
    with colB:
        try:
            base = sem_get_paths(slug)["base"]
            summary: List[Tuple[str, int]] = fin_summarize(base)
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
            st.exception(e)
