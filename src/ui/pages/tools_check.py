# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/tools_check.py
# Flusso: mostra prompt → Prosegui → esegue Vision (senza force, con retry auto se gate) → mostra output → STOP.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, cast

from ui.utils.stubs import get_streamlit

st = get_streamlit()

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# servizi Vision
from semantic.vision_provision import prepare_assistant_input
from ui.chrome import render_chrome_then_require
from ui.services.vision_provision import provision_from_vision
from ui.utils.workspace import workspace_root

LOG = get_structured_logger("ui.tools_check")


def _client_pdf_path(base_dir: Path) -> Path:
    cfg = cast(Path, ensure_within_and_resolve(base_dir, base_dir / "config"))
    return cast(Path, ensure_within_and_resolve(cfg, cfg / "VisionStatement.pdf"))


def _is_gate_error(err: Exception) -> bool:
    """
    Rileva il gate Vision:
    - messaggi con 'vision' e radice 'eseguit*' (case/diacritics tolerant)
    - presenza del marker 'file=vision_hash'
    - oppure attributo err.file_path che punta al sentinel '.vision_hash'
    """
    msg = str(err).casefold()
    file_path = getattr(err, "file_path", "") or ""
    has_sentinel = Path(str(file_path)).name == ".vision_hash"
    text_hit = ("vision" in msg and "eseguit" in msg) or ("file=vision_hash" in msg)
    return has_sentinel or text_hit


def main() -> None:
    # Richiede slug selezionato e disegna chrome coerente
    slug = render_chrome_then_require()
    base_dir = workspace_root(slug)
    pdf_path = _client_pdf_path(base_dir)

    st.header("Tools > Check")
    st.caption("Anteprima del prompt, poi esecuzione Vision e visualizzazione dell’output.")

    # 1) Costruzione prompt (no token)
    try:
        with st.spinner("Preparo il prompt Vision..."):
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            # Usa model="" per evitare warning/typing; il parametro è opzionale a livello logico
            prepared_prompt: str = prepare_assistant_input(ctx, slug=slug, pdf_path=pdf_path, model="", logger=LOG)
    except Exception as exc:
        st.error(f"Impossibile generare il prompt: {exc}")
        LOG.warning("ui.tools_check.prompt_error", extra={"slug": slug, "err": str(exc)})
        st.stop()

    # 2) Gate sul prompt
    st.subheader("Prompt Vision generato")
    st.text_area("Prompt", value=prepared_prompt, height=420, label_visibility="collapsed", disabled=True)
    c1, c2 = st.columns(2)
    if c1.button("Annulla", type="secondary"):
        st.info("Operazione annullata.")
        st.stop()
    go = c2.button("Prosegui", type="primary")
    if not go:
        st.stop()

    # 3) Esecuzione Vision: tentativo normale → retry automatico forzato solo se scatta il gate
    forced = False
    result: Dict[str, Any] = {}
    try:
        with st.spinner("Contatto l’assistente..."):
            result = provision_from_vision(
                ctx,
                logger=LOG,
                slug=slug,
                pdf_path=pdf_path,
                prepared_prompt=prepared_prompt,
                force=False,  # primo tentativo: non forzare
                model=None,
            )
    except ConfigError as e:
        if _is_gate_error(e):
            forced = True
            with st.spinner("Vision già eseguita: rigenero forzando..."):
                result = provision_from_vision(
                    ctx,
                    logger=LOG,
                    slug=slug,
                    pdf_path=pdf_path,
                    prepared_prompt=prepared_prompt,
                    force=True,  # retry invisibile all’utente
                    model=None,
                )
        else:
            st.error(str(e))
            LOG.warning("ui.tools_check.run_error", extra={"slug": slug, "type": e.__class__.__name__})
            st.stop()
    except Exception as e:
        st.error(f"Errore durante l'esecuzione della Vision: {e}")
        LOG.warning("ui.tools_check.run_error", extra={"slug": slug, "err": str(e)})
        st.stop()

    # 4) Output Assistente (+ caption sul tipo di esecuzione) → STOP
    st.subheader("Output Assistente")

    # Caption discreta sul tipo di esecuzione
    if forced:
        st.caption("Esecuzione: **rigenerata forzando** (gate rilevato).")
    else:
        st.caption("Esecuzione: **normale** (nessun gate rilevato).")

    shown = False

    # a) YAML del mapping generato (se presente)
    mapping_path = Path(result.get("mapping", "")) if isinstance(result, dict) else None
    if mapping_path and mapping_path.exists():
        try:
            yaml_text = read_text_safe(mapping_path.parent, mapping_path, encoding="utf-8")
            st.code(yaml_text, language="yaml")
            shown = True
        except Exception:
            pass

    # b) Eventuale JSON “raw” affiancato (best effort)
    if mapping_path:
        maybe_json = mapping_path.with_suffix(".json")
        if maybe_json.exists():
            try:
                raw = read_text_safe(maybe_json.parent, maybe_json, encoding="utf-8")
                st.code(json.dumps(json.loads(raw), ensure_ascii=False, indent=2), language="json")
                shown = True
            except Exception:
                pass

    # c) Estratto testuale se disponibile nel risultato
    if isinstance(result, dict) and result.get("assistant_text_excerpt"):
        st.write(result["assistant_text_excerpt"])
        shown = True

    if not shown:
        st.info("Risultato generato. Nessun payload testuale aggiuntivo da mostrare per questa esecuzione.")

    st.success("Completato. Il flusso si ferma qui.")
    st.stop()


if __name__ == "__main__":
    main()
