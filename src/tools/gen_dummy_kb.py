# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/gen_dummy_kb.py
# Genera una KB "dummy" passando dalle stesse funzioni usate dalla UI:
# pre_onboarding + Vision (+ Drive opzionale). Con flag per disabilitare Drive/Vision.

from __future__ import annotations

import argparse
import importlib
import io
import json
import logging
import multiprocessing as mp
import os
import shutil
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional, TextIO, TypedDict

try:
    import yaml
except Exception:
    yaml = None  # type: ignore


class _PayloadPaths(TypedDict):
    base: str
    config: str
    vision_pdf: str
    semantic_mapping: str
    cartelle_raw: str


class _PayloadConfigIds(TypedDict, total=False):
    drive_folder_id: Optional[str]
    drive_raw_folder_id: Optional[str]


class _DummyPayload(TypedDict):
    slug: str
    client_name: str
    paths: _PayloadPaths
    drive_min: Dict[str, Any]
    drive_build: Dict[str, Any]
    drive_readmes: Dict[str, Any]
    config_ids: _PayloadConfigIds
    vision_used: bool
    drive_used: bool
    fallback_used: bool
    local_readmes: List[str]


# ------------------------------------------------------------
# Path bootstrap (repo root + src)
# ------------------------------------------------------------
def _add_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]  # <repo>/
    src_dir = repo_root / "src"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return repo_root, src_dir


REPO_ROOT, SRC_DIR = _add_paths()
SRC_ROOT = SRC_DIR
from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.path_utils import (  # noqa: E402
    ensure_within_and_resolve,
    open_for_read_bytes_selfguard,
    read_text_safe,
    to_kebab,
)

try:
    from pipeline.exceptions import ConfigError  # type: ignore
except Exception:  # pragma: no cover
    ConfigError = Exception  # type: ignore[assignment]


def _normalize_relative_path(value: str, *, var_name: str) -> Path:
    candidate = Path(value.strip())
    if not value.strip():
        raise SystemExit(f"{var_name} non può essere vuoto")
    if candidate.is_absolute():
        raise SystemExit(f"{var_name} deve indicare un percorso relativo (es. clients_db/clients.yaml)")
    normalised = Path()
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise SystemExit(f"{var_name}: componenti '..' non sono ammesse")
        normalised /= part
    if not normalised.parts:
        raise SystemExit(f"{var_name} non può essere vuoto")
    return normalised


# ------------------------------------------------------------
# Import delle API usate dalla UI
# ------------------------------------------------------------
# pre_onboarding: workspace locale + salvataggio Vision PDF (se fornito)
from pre_onboarding import ensure_local_workspace_for_ui  # type: ignore

# Vision (stesse firme UI)
_vision_mod = importlib.import_module("ui.services.vision_provision")
run_vision = getattr(_vision_mod, "run_vision")

# Drive runner (opzionale). Se non presente → si prosegue senza Drive.
try:
    _drive_mod = importlib.import_module("ui.services.drive_runner")
    ensure_drive_minimal_and_upload_config = getattr(_drive_mod, "ensure_drive_minimal_and_upload_config", None)
    build_drive_from_mapping = getattr(_drive_mod, "build_drive_from_mapping", None)
    emit_readmes_for_raw = getattr(_drive_mod, "emit_readmes_for_raw", None)
except Exception:
    ensure_drive_minimal_and_upload_config = None
    build_drive_from_mapping = None
    emit_readmes_for_raw = None

try:
    from tools.clean_client_workspace import perform_cleanup as _perform_cleanup  # type: ignore
except Exception:  # pragma: no cover - il cleanup completo può non essere disponibile in ambienti ridotti
    _perform_cleanup = None  # type: ignore[assignment]

# Registry UI (clienti)
try:
    from ui.clients_store import ClientEntry, set_state, upsert_client  # type: ignore
except Exception:
    ClientEntry = None
    upsert_client = None
    set_state = None

# Util pipeline (facoltative)
try:
    from pipeline.config_utils import get_client_config  # type: ignore
except Exception:
    get_client_config = None

try:
    from pipeline.context import ClientContext  # type: ignore
except Exception:
    ClientContext = None

try:
    from pipeline.env_utils import ensure_dotenv_loaded, get_env_var  # type: ignore
except Exception:

    def ensure_dotenv_loaded() -> None:  # type: ignore
        return

    def get_env_var(name: str, default: str | None = None, **_: object) -> str | None:
        return os.environ.get(name, default)


try:
    from pipeline.file_utils import safe_write_bytes as _safe_write_bytes  # type: ignore
    from pipeline.file_utils import safe_write_text as _safe_write_text  # type: ignore
except Exception:

    def _safe_write_text(path: Path, text: str, *, encoding="utf-8", atomic=False) -> None:  # type: ignore
        raise RuntimeError("safe_write_text unavailable: install pipeline.file_utils dependency")  # pragma: no cover

    def _safe_write_bytes(path: Path, data: bytes, *, atomic=False) -> None:  # type: ignore
        raise RuntimeError("safe_write_bytes unavailable: install pipeline.file_utils dependency")  # pragma: no cover


# Compat: test_gen_dummy_kb_import_safety si aspetta che gli attributi pubblici siano None finch� non si esegue il tool.
safe_write_text = None  # type: ignore
safe_write_bytes = None  # type: ignore
_fin_import_csv = None  # type: ignore


def _ensure_dependencies() -> None:
    """Carica lazy le dipendenze opzionali e popola i placeholder pubblici."""
    if getattr(_ensure_dependencies, "_done", False):
        return

    for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    global safe_write_text, safe_write_bytes, _fin_import_csv
    safe_write_text = _safe_write_text  # type: ignore
    safe_write_bytes = _safe_write_bytes  # type: ignore

    try:
        from finance.api import import_csv as fin_import_csv  # type: ignore
    except Exception:
        fin_import_csv = None
    _fin_import_csv = fin_import_csv  # type: ignore

    _ensure_dependencies._done = True  # type: ignore[attr-defined]


_ensure_dependencies._done = False  # type: ignore[attr-defined]

_DEFAULT_VISION_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 2\n0000000000 65535 f \n0000000010 00000 n \n"
    b"trailer\n<< /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)


def _build_generic_vision_template_pdf() -> bytes:
    """
    Genera un VisionStatement.pdf generico con testo esplicativo per Vision, Mission,
    Framework Etico, Goal e Contesto Operativo. Fallback sul PDF minimale se fallisce.
    """

    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        heading = styles["Heading2"]

        story = []

        def add_title(text: str) -> None:
            story.append(Paragraph(text, heading))
            story.append(Spacer(1, 0.4 * cm))

        def add_paragraph(text: str) -> None:
            story.append(Paragraph(text, normal))
            story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("Vision Statement – Template generico", styles["Title"]))
        story.append(Spacer(1, 0.8 * cm))

        add_title("Vision")
        add_paragraph(
            "In questa sezione il cliente descrive la propria Vision, ovvero l’orizzonte di lungo periodo "
            "verso cui tende l’organizzazione. La Vision dovrebbe rispondere alla domanda: "
            "«In che tipo di realtà vogliamo contribuire a vivere tra 5–10 anni grazie al nostro lavoro "
            "e all’uso dell’Intelligenza Artificiale?».",
        )

        add_title("Mission")
        add_paragraph(
            "Qui va descritta la Mission, cioè il modo concreto in cui l’organizzazione intende agire "
            "per avvicinarsi alla Vision. La Mission risponde tipicamente a: "
            "«Cosa facciamo, per chi lo facciamo e con quali modalità operative?».",
        )

        add_title("Framework Etico")
        add_paragraph(
            "In questa parte vanno indicati i principi etici che guidano l’uso dell’AI e dei dati: "
            "trasparenza, tracciabilità, supervisione umana, sostenibilità, inclusione, gestione dei bias, "
            "adesione alle normative (es. AI Act) e alle policy interne. "
            "Il Framework Etico deve chiarire quali pratiche sono accettabili e quali no.",
        )

        add_title("Goal (es. orizzonti 3/6/12 mesi)")
        add_paragraph(
            "Qui si definiscono gli obiettivi operativi a breve, medio e lungo termine. "
            "Un possibile schema è quello a basket temporali: ad esempio 3 mesi (attivazione e primi risultati), "
            "6 mesi (consolidamento e trend), 12 mesi (impatto complessivo e scalabilità). "
            "Per ogni orizzonte temporale è utile indicare obiettivi chiari e, se possibile, alcuni KPI indicativi.",
        )

        add_title("Contesto Operativo")
        add_paragraph(
            "In questa sezione il cliente descrive il contesto in cui opera il progetto: "
            "settore di attività (es. PMI, scuola, PA, territorio), tipologia di utenti coinvolti, "
            "lingue di lavoro, normative chiave di riferimento (es. regolamenti di settore, privacy, "
            "linee guida interne). L’obiettivo è fornire al sistema un quadro di riferimento sintetico ma chiaro.",
        )

        add_paragraph(
            "Questo documento funge da contratto semantico tra l’organizzazione e il sistema: "
            "non deve essere perfetto, ma sufficientemente chiaro da permettere di individuare "
            "le aree tematiche principali e gli obiettivi del progetto.",
        )

        doc.build(story)
        return buf.getvalue()
    except Exception:
        return _DEFAULT_VISION_PDF


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
class _Ctx:
    """Contesto minimo compatibile con run_vision (serve .base_dir)."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


def _client_base(slug: str) -> Path:
    env_root = get_env_var("REPO_ROOT_DIR", default=None)
    if env_root:
        try:
            return Path(env_root).expanduser().resolve()
        except Exception:
            pass
    return REPO_ROOT / "output" / f"timmy-kb-{slug}"


def _pdf_path(slug: str) -> Path:
    return _client_base(slug) / "config" / "VisionStatement.pdf"


def _yaml_quote(value: str) -> str:
    """Serializza stringhe in stile YAML sfruttando json.dumps per escaping."""
    return json.dumps(str(value), ensure_ascii=False)


def _render_default_mapping_yaml(slug: str, client_name: str) -> str:
    return (
        dedent(
            f"""\
            context:
              slug: {_yaml_quote(slug)}
              client_name: {_yaml_quote(client_name)}
            contracts:
              ambito: "Contrattualistica e forniture"
              descrizione: "Documenti contrattuali, NDA, ordini di acquisto, accordi quadro e appendici."
              keywords:
                - "contratto"
                - "NDA"
                - "fornitore"
                - "ordine"
                - "appendice"
            reports:
              ambito: "Reportistica e analisi"
              descrizione: "Report periodici, metriche operative, analisi interne e rendicontazioni."
              keywords:
                - "report"
                - "analisi"
                - "rendiconto"
                - "KPI"
                - "metriche"
            presentations:
              ambito: "Presentazioni e materiali"
              descrizione: "Slide, presentazioni per stakeholder, materiali divulgativi e executive brief."
              keywords:
                - "presentazione"
                - "slide"
                - "deck"
                - "brief"
                - "stakeholder"
            synonyms:
              contracts:
                - "contratti"
                - "accordi"
                - "forniture"
              reports:
                - "rendiconti"
                - "analitiche"
                - "reportistica"
              presentations:
                - "slide"
                - "deck"
                - "presentazioni"
            system_folders:
              identity: "book/identity"
              glossario: "book/glossario"
            """
        ).strip()
        + "\n"
    )


def _render_default_cartelle_yaml(slug: str) -> str:
    return (
        dedent(
            f"""\
            version: 1
            folders:
              - "raw/contracts"
              - "raw/reports"
              - "raw/presentations"
            system_folders:
              identity: "book/identity"
              glossario: "book/glossario"
            meta:
              source: "dummy"
              slug: {_yaml_quote(slug)}
            """
        ).strip()
        + "\n"
    )


def _default_mapping_data(slug: str, client_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = {
        "context": {"slug": slug, "client_name": client_name},
        "contracts": {
            "ambito": "Contrattualistica e forniture",
            "descrizione": "Documenti contrattuali, NDA, ordini di acquisto, accordi quadro e appendici.",
            "keywords": ["contratto", "NDA", "fornitore", "ordine", "appendice"],
        },
        "reports": {
            "ambito": "Reportistica e analisi",
            "descrizione": "Report periodici, metriche operative, analisi interne e rendicontazioni.",
            "keywords": ["report", "analisi", "rendiconto", "KPI", "metriche"],
        },
        "presentations": {
            "ambito": "Presentazioni e materiali",
            "descrizione": "Slide, presentazioni per stakeholder, materiali divulgativi e executive brief.",
            "keywords": ["presentazione", "slide", "deck", "brief", "stakeholder"],
        },
        "synonyms": {
            "contracts": ["contratti", "accordi", "forniture"],
            "reports": ["rendiconti", "analitiche", "reportistica"],
            "presentations": ["slide", "deck", "presentazioni"],
        },
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
    }
    cartelle = {
        "version": 1,
        "folders": ["raw/contracts", "raw/reports", "raw/presentations"],
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
        "meta": {"source": "dummy", "slug": slug},
    }
    return mapping, cartelle


def _mapping_categories_from_default(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    categories: dict[str, dict[str, Any]] = {}
    for key in ("contracts", "reports", "presentations"):
        section = mapping.get(key) or {}
        cat_key = to_kebab(str(key))
        categories[cat_key] = {
            "ambito": str(section.get("ambito") or key.title()),
            "descrizione": str(section.get("descrizione") or ""),
            "keywords": [str(x).strip() for x in section.get("keywords") or [] if str(x).strip()],
        }
    return categories


def _safe_dump_yaml(path: Path, data: Any, *, fallback: str) -> None:
    if yaml is not None:
        _safe_write_text(
            path,
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),  # type: ignore[arg-type]
            encoding="utf-8",
            atomic=True,
        )
        return
    _safe_write_text(path, fallback, encoding="utf-8", atomic=True)


def _write_basic_semantic_yaml(base_dir: Path, *, slug: str, client_name: str) -> dict[str, str]:
    """
    Genera YAML "basici" senza passare da Vision:
      - semantic/semantic_mapping.yaml
      - semantic/cartelle_raw.yaml
    Crea anche le cartelle raw/ di base (contracts/reports/presentations).
    """
    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = base_dir / "raw"
    for name in ("contracts", "reports", "presentations"):
        (raw_dir / name).mkdir(parents=True, exist_ok=True)

    mapping_data, cartelle_data = _default_mapping_data(slug, client_name)
    mapping_path = sem_dir / "semantic_mapping.yaml"
    cartelle_path = sem_dir / "cartelle_raw.yaml"
    _safe_dump_yaml(mapping_path, mapping_data, fallback=_render_default_mapping_yaml(slug, client_name))
    _safe_dump_yaml(cartelle_path, cartelle_data, fallback=_render_default_cartelle_yaml(slug))

    # Genera contenuti minimi in book/ per i test smoke (alpha/beta + README/SUMMARY).
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "alpha.md": "# Alpha\n\nContenuto di esempio per la cartella contracts.\n",
        "beta.md": "# Beta\n\nContenuto di esempio per la cartella reports.\n",
        "README.md": "# Dummy KB\n",
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
    }
    for name, content in defaults.items():
        target = book_dir / name
        if not target.exists():
            _safe_write_text(target, content, encoding="utf-8", atomic=True)

    categories = _mapping_categories_from_default(mapping_data)

    return {"mapping": str(mapping_path), "cartelle": str(cartelle_path), "categories": categories}


def _render_local_readme_bytes(title: str, descr: str, examples: list[str]) -> tuple[bytes, str]:
    """Replica minimale del renderer PDF dei README (fallback su TXT se reportlab assente)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        x, y = 2 * cm, height - 2 * cm

        def draw_line(text: str, font: str = "Helvetica", size: int = 11, leading: int = 14) -> None:
            nonlocal y
            c.setFont(font, size)
            for line in (text or "").splitlines() or [""]:
                c.drawString(x, y, line[:120])
                y -= leading
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm

        c.setTitle(f"README - {title}")
        draw_line(f"README - {title}", font="Helvetica-Bold", size=14, leading=18)
        y -= 4
        draw_line("")
        draw_line("Ambito:", font="Helvetica-Bold", size=12, leading=16)
        draw_line(descr or "")
        draw_line("")
        draw_line("Esempi:", font="Helvetica-Bold", size=12, leading=16)
        for ex in examples or []:
            draw_line(f"- {ex}")
        c.showPage()
        c.save()
        data = buf.getvalue()
        buf.close()
        return data, "application/pdf"
    except Exception:
        lines = [f"README - {title}", "", "Ambito:", descr or "", "", "Esempi:"]
        lines.extend(f"- {ex}" for ex in (examples or []))
        return ("\n".join(lines)).encode("utf-8"), "text/plain"


def _ensure_local_readmes(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]] = None) -> list[str]:
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    catalogue = categories or {}
    candidate_dirs: set[Path] = {p for p in raw_dir.iterdir() if p.is_dir()}
    for key in catalogue.keys():
        candidate_dirs.add(raw_dir / to_kebab(key))

    for subdir in sorted(candidate_dirs):
        subdir.mkdir(parents=True, exist_ok=True)
        cat_key = to_kebab(subdir.name)
        meta = catalogue.get(cat_key) or catalogue.get(subdir.name) or {}
        title = str(meta.get("ambito") or subdir.name.replace("-", " ").title())
        descr = str(meta.get("descrizione") or "")
        raw_keywords = meta.get("keywords")
        if isinstance(raw_keywords, list):
            keywords = [str(x).strip() for x in raw_keywords if str(x).strip()]
        else:
            keywords = []
        data, mime = _render_local_readme_bytes(title, descr, keywords)
        filename = "README.pdf" if mime == "application/pdf" else "README.txt"
        target = subdir / filename
        if mime == "application/pdf":
            _safe_write_bytes(target, data, atomic=True)
        else:
            _safe_write_text(target, data.decode("utf-8"), encoding="utf-8", atomic=True)
        written.append(str(target))
    return written


def _load_mapping_categories(base_dir: Path) -> dict[str, dict[str, Any]]:
    mapping_path = base_dir / "semantic" / "semantic_mapping.yaml"
    if not mapping_path.exists():
        return {}
    if yaml is None:
        return {}
    try:
        text = read_text_safe(base_dir, mapping_path, encoding="utf-8")  # type: ignore[arg-type]
        data = yaml.safe_load(text) or {}
    except Exception:
        return {}

    categories: dict[str, dict[str, Any]] = {}

    areas = data.get("areas")
    if isinstance(areas, list):
        for area in areas:
            if not isinstance(area, dict):
                continue
            key = to_kebab(str(area.get("key") or area.get("ambito") or area.get("title") or ""))
            if not key:
                continue
            keywords: list[str] = []
            for field in ("documents", "artefatti", "chunking_hints"):
                raw = area.get(field)
                if isinstance(raw, list):
                    keywords.extend(str(x).strip() for x in raw if str(x).strip())
            descr = str(
                area.get("descrizione_breve") or area.get("descrizione") or area.get("ambito") or key.replace("-", " ")
            )
            categories[key] = {
                "ambito": str(area.get("ambito") or key.replace("-", " ").title()),
                "descrizione": descr,
                "keywords": keywords,
            }
    if categories:
        return categories

    for key, section in data.items():
        if key in {"context", "synonyms", "system_folders"}:
            continue
        if not isinstance(section, dict):
            continue
        cat_key = to_kebab(str(key))
        if not cat_key:
            continue
        keywords = section.get("keywords") if isinstance(section.get("keywords"), list) else []
        categories[cat_key] = {
            "ambito": str(section.get("ambito") or cat_key.replace("-", " ").title()),
            "descrizione": str(section.get("descrizione") or section.get("descrizione_breve") or ""),
            "keywords": [str(x).strip() for x in keywords if str(x).strip()],
        }
    return categories


def _vision_worker(queue: mp.Queue, slug: str, base_dir: str, pdf_path: str) -> None:
    """Esegue run_vision in un sottoprocesso e restituisce esito tramite queue."""
    ctx = _Ctx(Path(base_dir))
    logger = get_structured_logger("tools.gen_dummy_kb.vision", context={"slug": slug})
    try:
        run_vision(ctx, slug=slug, pdf_path=Path(pdf_path), logger=logger)
        queue.put({"status": "ok"})
    except Exception as exc:  # noqa: BLE001
        payload: dict[str, Any] = {
            "status": "error",
            "error": str(exc),
            "exc_type": exc.__class__.__name__,
        }
        file_path = getattr(exc, "file_path", None)
        if file_path:
            payload["file_path"] = str(file_path)
        queue.put(payload)


def _run_vision_with_timeout(
    *,
    base_dir: Path,
    slug: str,
    pdf_path: Path,
    timeout_s: float,
    logger: logging.Logger,
) -> tuple[bool, Optional[dict[str, Any]]]:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_vision_worker, args=(queue, slug, str(base_dir), str(pdf_path)))
    proc.daemon = False
    proc.start()
    proc.join(timeout_s)
    if proc.is_alive():
        logger.warning(
            "tools.gen_dummy_kb.vision_timeout",
            extra={"slug": slug, "timeout_s": timeout_s},
        )
        proc.terminate()
        proc.join(5)
        queue.close()
        queue.join_thread()
        return False, {"reason": "timeout"}
    try:
        result = queue.get_nowait()
    except Exception:
        result = {"status": "error", "reason": "no-result"}
    finally:

        queue.close()
        queue.join_thread()
    exit_code = proc.exitcode
    if exit_code not in (0, None) and result.get("status") == "ok":
        result = {"status": "error", "exit_code": exit_code}
    if result.get("status") == "ok":
        return True, None
    return False, result  # type: ignore[return-value]


def _call_drive_min(slug: str, client_name: str, base_dir: Path, logger: logging.Logger) -> Optional[dict[str, Any]]:
    """Chiama ensure_drive_minimal_and_upload_config con firme UI. Skip silenzioso se non disponibile."""
    if not callable(ensure_drive_minimal_and_upload_config):
        return None
    ctx = _Ctx(base_dir)
    try:
        # firma principale (ctx, slug, client_folder_id=None, logger=None)
        return ensure_drive_minimal_and_upload_config(ctx, slug=slug, client_folder_id=None, logger=logger)  # type: ignore[arg-type]
    except TypeError:
        # fallback legacy: (slug, client_name)
        return ensure_drive_minimal_and_upload_config(slug=slug, client_name=client_name)  # type: ignore[misc]


def _call_drive_build_from_mapping(
    slug: str, client_name: str, base_dir: Path, logger: logging.Logger
) -> Optional[dict[str, Any]]:
    """Chiama build_drive_from_mapping come fa la UI (se disponibile)."""
    if not callable(build_drive_from_mapping):
        return None
    return build_drive_from_mapping(slug=slug, client_name=client_name)  # type: ignore[misc]


def _call_drive_emit_readmes(slug: str, base_dir: Path, logger: logging.Logger) -> Optional[dict[str, Any]]:
    """Upload dei README delle cartelle RAW su Drive (best-effort)."""
    if not callable(emit_readmes_for_raw):
        return None
    try:
        base_root = base_dir.parent
        return emit_readmes_for_raw(  # type: ignore[misc]
            slug,
            base_root=base_root,
            require_env=False,
            ensure_structure=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tools.gen_dummy_kb.drive_readmes_failed",
            extra={"slug": slug, "error": str(exc)},
        )
        return None


def _register_client(slug: str, client_name: str) -> None:  # pragma: no cover - mantenuto per compatibilità test
    """
    In precedenza registrava il cliente nel registry UI.
    Per la dummy KB lo lasciamo come no-op per evitare side-effect nel DB clienti.
    """
    return


def _purge_previous_state(slug: str, client_name: str, logger: logging.Logger) -> None:
    """
    Rimuove eventuali residui precedenti (locale + Drive + registry) prima di rigenerare la Dummy KB.

    - Usa `tools.clean_client_workspace.perform_cleanup` se disponibile.
    - In ogni caso prova a cancellare la cartella locale `output/timmy-kb-<slug>`.
    """

    if callable(_perform_cleanup):
        try:
            results = _perform_cleanup(slug, client_name=client_name)
            exit_code = results.get("exit_code")
            logger.info(
                "tools.gen_dummy_kb.cleanup.completed",
                extra={"slug": slug, "exit_code": exit_code, "results": results},
            )
        except Exception as exc:
            logger.warning(
                "tools.gen_dummy_kb.cleanup.failed",
                extra={"slug": slug, "error": str(exc)},
            )

    base_dir = _client_base(slug)
    try:
        if base_dir.exists():
            shutil.rmtree(base_dir)
            logger.info("tools.gen_dummy_kb.cleanup.local_deleted", extra={"slug": slug})
    except Exception as exc:
        logger.warning(
            "tools.gen_dummy_kb.cleanup.local_failed",
            extra={"slug": slug, "error": str(exc)},
        )

    sentinel = base_dir / "semantic" / ".vision_hash"
    try:
        if sentinel.exists():
            sentinel.unlink()
    except Exception as exc:
        # L'assenza del sentinel è già sufficiente; eventuali errori qui non sono bloccanti.
        logger.debug(
            "tools.gen_dummy_kb.cleanup.sentinel_unlink_failed",
            extra={"slug": slug, "error": str(exc)},
        )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Genera una KB dummy usando gli entry-point della UI (pre_onboarding + Vision + (Drive opz.))."
    )
    ap.add_argument("--slug", default="dummy", help="Slug del cliente (default: dummy)")
    ap.add_argument("--name", default=None, help='Nome visuale del cliente (default: "Dummy <slug>")')
    ap.add_argument("--no-drive", action="store_true", help="Disabilita tutti i passi Drive")
    ap.add_argument("--no-vision", action="store_true", help="Non invocare Vision: genera YAML basici")
    ap.add_argument("--with-drive", action="store_true", help="(Legacy) Abilita Drive se possibile")
    ap.add_argument(
        "--base-dir",
        default=None,
        help="(Legacy) Directory radice in cui creare il workspace (override di REPO_ROOT_DIR).",
    )
    ap.add_argument(
        "--clients-db",
        dest="clients_db",
        default=None,
        help="(Legacy) Percorso relativo (clients_db/clients.yaml); imposta CLIENTS_DB_DIR/FILE per la UI.",
    )
    ap.add_argument(
        "--records",
        default=None,
        help="(Legacy) Numero di record finanza da generare (non più utilizzato).",
    )
    return ap.parse_args(argv)


def build_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    records_hint: Optional[str],
    logger: logging.Logger,
) -> _DummyPayload:
    if records_hint:
        try:
            _ = int(records_hint)
        except Exception:
            logger.debug(
                "tools.gen_dummy_kb.records_hint_non_numeric",
                extra={"value": records_hint, "slug": slug},
            )

    repo_pdf = REPO_ROOT / "config" / "VisionStatement.pdf"
    if repo_pdf.exists():
        try:
            safe_pdf = ensure_within_and_resolve(REPO_ROOT, repo_pdf)
            with open_for_read_bytes_selfguard(safe_pdf) as handle:
                pdf_bytes = handle.read()
        except Exception:
            logger.warning(
                "tools.gen_dummy_kb.vision_template_unreadable",
                extra={"file_path": str(repo_pdf), "slug": slug},
            )
            pdf_bytes = _build_generic_vision_template_pdf()
    else:
        logger.warning(
            "tools.gen_dummy_kb.vision_template_missing",
            extra={"file_path": str(repo_pdf), "slug": slug},
        )
        pdf_bytes = _build_generic_vision_template_pdf()
        try:
            repo_pdf.parent.mkdir(parents=True, exist_ok=True)
            with repo_pdf.open("wb") as handle:
                handle.write(pdf_bytes)
        except Exception:
            logger.debug(
                "tools.gen_dummy_kb.vision_template_write_failed",
                extra={"file_path": str(repo_pdf), "slug": slug},
            )

    ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=pdf_bytes)

    base_dir = _client_base(slug)
    pdf_path = _pdf_path(slug)

    cfg_out: _PayloadConfigIds = _PayloadConfigIds()
    drive_min_info: Dict[str, Any] | None = None
    drive_build_info: Dict[str, Any] | None = None
    drive_readmes_info: Dict[str, Any] | None = None
    categories_for_readmes: Dict[str, Dict[str, Any]] = {}
    fallback_info: Optional[Dict[str, Any]] = None
    vision_completed = False

    if enable_vision:
        success, vision_meta = _run_vision_with_timeout(
            base_dir=base_dir,
            slug=slug,
            pdf_path=pdf_path,
            timeout_s=120.0,
            logger=logger,
        )
        if success:
            vision_completed = True
            categories_for_readmes = _load_mapping_categories(base_dir)
        else:
            reason = vision_meta or {}
            message = str(reason.get("error") or "")
            sentinel = str(reason.get("file_path") or "")
            normalized = message.casefold().replace("à", "a")
            if reason.get("reason") == "timeout":
                logger.warning(
                    "tools.gen_dummy_kb.vision_fallback_no_vision",
                    extra={"slug": slug, "mode": "timeout"},
                )
                fallback_info = _write_basic_semantic_yaml(base_dir, slug=slug, client_name=client_name)
                categories_for_readmes = fallback_info.get("categories", {})
            elif ".vision_hash" in sentinel or "vision gia eseguito" in normalized:
                logger.info(
                    "tools.gen_dummy_kb.vision_already_completed",
                    extra={"slug": slug, "sentinel": sentinel or ".vision_hash"},
                )
                vision_completed = True
                categories_for_readmes = _load_mapping_categories(base_dir)
            else:
                raise ConfigError(message or "Vision fallita", slug=slug, file_path=reason.get("file_path"))
    else:
        fallback_info = _write_basic_semantic_yaml(base_dir, slug=slug, client_name=client_name)
        categories_for_readmes = fallback_info.get("categories", {})

    if not categories_for_readmes:
        categories_for_readmes = _load_mapping_categories(base_dir)

    local_readmes = _ensure_local_readmes(base_dir, categories_for_readmes)

    if enable_drive:
        try:
            drive_min_info = _call_drive_min(slug, client_name, base_dir, logger)
            drive_build_info = _call_drive_build_from_mapping(slug, client_name, base_dir, logger)
            drive_readmes_info = _call_drive_emit_readmes(slug, base_dir, logger)
        except Exception as exc:
            logger.warning(
                "tools.gen_dummy_kb.drive_provisioning_failed",
                extra={"error": str(exc), "slug": slug},
            )

    fallback_used = bool(fallback_info)

    cfg_out: dict[str, Any] = {}
    if callable(get_client_config) and ClientContext:
        try:
            ctx_cfg = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)  # type: ignore[misc]
            cfg = get_client_config(ctx_cfg) or {}
            cfg_out = {
                "drive_folder_id": cfg.get("drive_folder_id"),
                "drive_raw_folder_id": cfg.get("drive_raw_folder_id"),
            }
        except Exception:
            cfg_out = _PayloadConfigIds()

    return {
        "slug": slug,
        "client_name": client_name,
        "paths": {
            "base": str(base_dir),
            "config": str(base_dir / "config" / "config.yaml"),
            "vision_pdf": str(pdf_path),
            "semantic_mapping": str(base_dir / "semantic" / "semantic_mapping.yaml"),
            "cartelle_raw": str(base_dir / "semantic" / "cartelle_raw.yaml"),
        },
        "drive_min": drive_min_info or {},
        "drive_build": drive_build_info or {},
        "drive_readmes": drive_readmes_info or {},
        "config_ids": cfg_out,
        "vision_used": bool(vision_completed),
        "drive_used": bool(enable_drive),
        "fallback_used": fallback_used,
        "local_readmes": local_readmes,
    }


def emit_structure(payload: _DummyPayload | Dict[str, Any], *, stream: TextIO = sys.stdout) -> None:
    stream.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    stream.write("\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ensure_dotenv_loaded()

    args = parse_args(argv)

    slug = args.slug.strip()
    client_name = (args.name or f"Dummy {slug}").strip()
    enable_drive = (not args.no_drive) or args.with_drive
    enable_vision = not args.no_vision
    records_hint = args.records

    if records_hint is not None and not args.no_vision:
        enable_vision = False
        enable_drive = False

    if not args.with_drive and (args.base_dir or args.clients_db):
        enable_drive = False
        if not args.no_vision:
            enable_vision = False

    prev_repo_root_dir = os.environ.get("REPO_ROOT_DIR")
    prev_clients_db_dir = os.environ.get("CLIENTS_DB_DIR")
    prev_clients_db_file = os.environ.get("CLIENTS_DB_FILE")
    workspace_override: Optional[Path] = None
    try:
        if args.base_dir:
            base_override = Path(args.base_dir).expanduser().resolve()
            workspace_override = base_override / f"timmy-kb-{slug}"
            os.environ["REPO_ROOT_DIR"] = str(workspace_override)

        if args.clients_db:
            clients_db_relative = _normalize_relative_path(args.clients_db, var_name="--clients-db")
            if len(clients_db_relative.parts) < 2:
                raise SystemExit("--clients-db deve includere anche il nome file (es. clients_db/clients.yaml)")
            if clients_db_relative.parts[0] != "clients_db":
                raise SystemExit("--clients-db deve iniziare con 'clients_db/'")
            db_dir_override = Path(*clients_db_relative.parts[:-1])
            db_file_override = Path(clients_db_relative.parts[-1])
            os.environ["CLIENTS_DB_DIR"] = str(db_dir_override)
            os.environ["CLIENTS_DB_FILE"] = str(db_file_override)

        logger = get_structured_logger("tools.gen_dummy_kb", context={"slug": slug})
        logger.setLevel(logging.INFO)

        _purge_previous_state(slug, client_name, logger)

        try:
            payload = build_payload(
                slug=slug,
                client_name=client_name,
                enable_drive=enable_drive,
                enable_vision=enable_vision,
                records_hint=records_hint,
                logger=logger,
            )
            emit_structure(payload)
            return 0
        except Exception as exc:
            logger.error(
                "tools.gen_dummy_kb.run_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            emit_structure({"error": str(exc)}, stream=sys.stderr)
            return 1
    finally:
        try:
            from ui.utils.workspace import clear_base_cache  # late import per evitare dipendenze circolari
        except Exception:  # pragma: no cover
            clear_base_cache = None  # type: ignore[assignment]
        if callable(clear_base_cache):
            clear_base_cache(slug=slug)
        if args.base_dir:
            if prev_repo_root_dir is None:
                os.environ.pop("REPO_ROOT_DIR", None)
            else:
                os.environ["REPO_ROOT_DIR"] = prev_repo_root_dir
        if args.clients_db:
            if prev_clients_db_dir is None:
                os.environ.pop("CLIENTS_DB_DIR", None)
            else:
                os.environ["CLIENTS_DB_DIR"] = prev_clients_db_dir
            if prev_clients_db_file is None:
                os.environ.pop("CLIENTS_DB_FILE", None)
            else:
                os.environ["CLIENTS_DB_FILE"] = prev_clients_db_file


if __name__ == "__main__":
    raise SystemExit(main())
