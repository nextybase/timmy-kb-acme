# scripts/refactor_logging_ui.py
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src" / "ui"

RX_IMPORT_APP_CORE = re.compile(r"from\s+ui\.app_core\.logging\s+import\s+_setup_logging")
RX_SETUP_CALL = re.compile(r"\b_setup_logging\(\)")
RX_IMPORT_LOGGING = re.compile(r"^\s*import\s+logging\s*$", re.MULTILINE)
RX_BASIC_CONFIG = re.compile(r"\blogging\.basicConfig\s*\(")
RX_GET_LOGGER = re.compile(r"\blogging\.getLogger\(\s*__name__\s*\)")
RX_GET_LOGGER_LITERAL = re.compile(r"logging\.getLogger\(\s*(['\"])([^'\"]+)\1\s*\)")
RX_GET_LOGGER_GENERIC = re.compile(r"logging\.getLogger\(")
RX_HAS_PIPELINE_IMPORT = re.compile(
    r"from\s+pipeline\.logging_utils\s+import\s+get_structured_logger"
)
RX_ANY_LOGGING_USE = re.compile(r"\blogging\.")
RX_FROM_UI_UTILS_LOGGING = re.compile(
    r"from\s+ui\.utils\.logging\s+import\s+get_logger\b"
)

def ensure_pipeline_import(text: str) -> str:
    if RX_HAS_PIPELINE_IMPORT.search(text):
        return text
    # Inseriamo l'import in cima, dopo eventuali future annotations
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines[:10]):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
    lines.insert(insert_at, "from pipeline.logging_utils import get_structured_logger")
    result = "\n".join(lines)
    if trailing_newline:
        result += "\n"
    return result

def patch_text(path: Path, text: str) -> tuple[str, bool]:
    changed = False

    # 1) rimuovi import legacy app_core
    if RX_IMPORT_APP_CORE.search(text):
        text = RX_IMPORT_APP_CORE.sub("from pipeline.logging_utils import get_structured_logger", text)
        changed = True

    # 2) rimpiazza _setup_logging() -> get_structured_logger(__name__)
    if RX_SETUP_CALL.search(text):
        text = RX_SETUP_CALL.sub("get_structured_logger(__name__)", text)
        text = ensure_pipeline_import(text)
        changed = True

    # 3) rimpiazza logging.getLogger(__name__) -> get_structured_logger(__name__)
    if RX_GET_LOGGER.search(text):
        text = RX_GET_LOGGER.sub("get_structured_logger(__name__)", text)
        text = ensure_pipeline_import(text)
        changed = True

    # 4) rimpiazza logging.getLogger(\"literal\") -> get_structured_logger(\"literal\")
    def _literal_repl(match: re.Match[str]) -> str:
        quote, name = match.group(1), match.group(2)
        return f"get_structured_logger({quote}{name}{quote})"

    if RX_GET_LOGGER_LITERAL.search(text):
        text = RX_GET_LOGGER_LITERAL.sub(_literal_repl, text)
        text = ensure_pipeline_import(text)
        changed = True

    # 5) fallback: logging.getLogger(<expr>) -> get_structured_logger(<expr>)
    if RX_GET_LOGGER_GENERIC.search(text):
        text = RX_GET_LOGGER_GENERIC.sub("get_structured_logger(", text)
        text = ensure_pipeline_import(text)
        changed = True

    # 6) elimina basicConfig
    if RX_BASIC_CONFIG.search(text):
        # Commentiamo la riga per sicurezza (evitiamo side-effect inattesi)
        text = RX_BASIC_CONFIG.sub("# removed: centralized logging (basicConfig)", text)
        changed = True

    # 7) se prima importava get_logger da ui.utils.logging, rimuovilo (ora tutto passa da pipeline)
    if RX_FROM_UI_UTILS_LOGGING.search(text):
        text = RX_FROM_UI_UTILS_LOGGING.sub("", text)
        changed = True

    # 8) se l'import di logging resta ma non serve, rimuovilo
    if changed and RX_IMPORT_LOGGING.search(text):
        # mantieni l'import se restano riferimenti espliciti a logging (es. logging.INFO)
        if not RX_ANY_LOGGING_USE.search(text):
            text = RX_IMPORT_LOGGING.sub("", text)

    return text, changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refactor logging UI module imports towards pipeline.logging_utils."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra i file che verrebbero modificati senza scrivere su disco.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = sorted(UI_DIR.rglob("*.py"))
    edited: list[Path] = []
    for fp in files:
        if fp.name == "logging.py" and "app_core" in str(fp):
            # verra' cancellato manualmente nel passo successivo
            continue
        old = fp.read_text(encoding="utf-8")
        new, ok = patch_text(fp, old)
        if ok:
            if args.dry_run:
                print(f"[DRY-RUN] {fp.relative_to(ROOT)}")
            else:
                fp.write_text(new, encoding="utf-8")
                print(f"[UPDATED] {fp.relative_to(ROOT)}")
            edited.append(fp.relative_to(ROOT))

    if args.dry_run:
        print(f"\nDry-run completato. File che verrebbero aggiornati: {len(edited)}")
        if edited:
            print("Prossimo passo (reale): rimuovi il file legacy src/ui/app_core/logging.py")
    else:
        print(f"\nRefactor completato. File aggiornati: {len(edited)}")
        print("Prossimo passo: rimuovi il file legacy src/ui/app_core/logging.py")

if __name__ == "__main__":
    main()
