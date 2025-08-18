# src/tools/refactor_tool.py
import os
import re
import sys
import difflib
from pathlib import Path

# === Setup unico e DRY della SRC_PATH (come in repo) ===
def setup_src_path():
    """
    Trova la root del progetto (dove c'è la cartella 'src/') salendo la gerarchia,
    aggiunge src/ a sys.path se non presente.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        src_path = parent / "src"
        if src_path.exists() and src_path.is_dir():
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))
            return src_path
    raise RuntimeError("Impossibile trovare la cartella 'src/' nella gerarchia.")

SRC_PATH = setup_src_path()

from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.refactor")

EXT_INCLUDE = {".py", ".yaml", ".yml", ".md"}
DIR_EXCLUDE = {".git", "venv", "__pycache__", ".mypy_cache", ".idea", ".vscode"}


def should_check_file(fname: str) -> bool:
    return any(fname.endswith(ext) for ext in EXT_INCLUDE)


def scan_occurrences(root: str, find_str: str, regex_mode: bool = False):
    """Scansiona i file ammessi e restituisce [(path, num_occorrenze), ...] solo per quelli con match."""
    all_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DIR_EXCLUDE]
        for fname in filenames:
            if should_check_file(fname):
                fpath = os.path.join(dirpath, fname)
                all_files.append(fpath)

    found_files = []
    for fpath in all_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            if regex_mode:
                matches = list(re.finditer(find_str, text))
            else:
                matches = list(re.finditer(re.escape(find_str), text))
            if matches:
                found_files.append((fpath, len(matches)))
        except Exception as e:
            logger.warning("⚠️ Errore leggendo file", extra={"file_path": fpath, "error": str(e)})
    return found_files


def _unified_diff(original: str, modified: str, fpath: str) -> str:
    """Crea un diff unificato leggibile per logging."""
    a = original.splitlines(keepends=False)
    b = modified.splitlines(keepends=False)
    diff = difflib.unified_diff(
        a, b,
        fromfile=f"{fpath}:before",
        tofile=f"{fpath}:after",
        lineterm=""
    )
    return "\n".join(diff)


def replace_in_files(file_list, find_str: str, replace_str: str, regex_mode: bool = False, dry_run: bool = True):
    """Esegue la sostituzione sui file passati. In dry-run logga un diff unificato."""
    for fpath, _ in file_list:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                original = f.read()
            if regex_mode:
                modified = re.sub(find_str, replace_str, original)
            else:
                modified = original.replace(find_str, replace_str)
            if original != modified:
                if dry_run:
                    logger.info("📄 [ANTEPRIMA] Modifiche previste", extra={"file_path": fpath})
                    diff_text = _unified_diff(original, modified, fpath)
                    if diff_text.strip():
                        logger.info(diff_text)
                    else:
                        logger.info("Nessuna differenza visualizzabile (possibile variazione di soli EOL).", extra={"file_path": fpath})
                else:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(modified)
                    logger.info("✏️ Sostituzione effettuata", extra={"file_path": fpath})
        except Exception as e:
            logger.warning("⚠️ Errore nel modificare file", extra={"file_path": fpath, "error": str(e)})


# ===========================
# Modalità 1: TROVA (solo ricerca)
# ===========================
def find_only_menu():
    logger.info("🔎 [Trova] — Ricerca nei file di progetto (senza modifiche)")
    find_str = input("🔍 Stringa da trovare (regex supportato): ").strip()
    if not find_str:
        logger.error("❌ Stringa vuota. Annullato.")
        return
    regex_mode = input("🔁 Usa modalità REGEX? [y/N]: ").strip().lower() == "y"
    default_root = str(Path(__file__).parent.parent.resolve())
    root = input(f"📁 Cartella da cui partire [default: {default_root}]: ").strip() or default_root

    logger.info("⏳ Scansione in corso", extra={"file_path": root, "mode": "regex" if regex_mode else "plain"})
    found_files = scan_occurrences(root, find_str, regex_mode=regex_mode)

    logger.info("📊 Risultati ricerca", extra={"query": find_str})
    if not found_files:
        logger.info("✅ Nessuna occorrenza trovata.", extra={"query": find_str})
        return

    for fpath, n in sorted(found_files, key=lambda t: (-t[1], t[0])):
        logger.info("Match trovati", extra={"file_path": fpath, "occurrences": n})
    logger.info("Totale file con occorrenze", extra={"count": len(found_files)})


# ================================
# Modalità 2: TROVA & SOSTITUISCI
# ================================
def find_and_replace_menu():
    logger.info("✏️ [Trova & Sostituisci] — Ricerca e sostituzione nei file di progetto")
    find_str = input("🔍 Stringa da trovare (regex supportato): ").strip()
    if not find_str:
        logger.error("❌ Stringa vuota. Annullato.")
        return
    replace_str = input("✏️ Stringa di sostituzione (vuoto = solo dry-run di diff): ")
    regex_mode = input("🔁 Usa modalità REGEX? [y/N]: ").strip().lower() == "y"
    dry_run = input("🧪 Vuoi solo simulare la sostituzione? [Y/n]: ").strip().lower() != "n"
    default_root = str(Path(__file__).parent.parent.resolve())
    root = input(f"📁 Cartella da cui partire [default: {default_root}]: ").strip() or default_root

    logger.info("⏳ Scansione in corso", extra={"file_path": root, "mode": "regex" if regex_mode else "plain"})
    found_files = scan_occurrences(root, find_str, regex_mode=regex_mode)

    logger.info("📊 Risultati ricerca", extra={"query": find_str})
    if not found_files:
        logger.info("✅ Nessuna occorrenza trovata.", extra={"query": find_str})
        return
    for fpath, n in found_files:
        logger.info("Match trovati", extra={"file_path": fpath, "occurrences": n})

    if dry_run:
        logger.info("🔍 Modalità dry-run: mostrerò i cambiamenti ma non scriverò nulla.")
    else:
        conferma = input("⚠️ Confermi la sostituzione su questi file? (y/N): ").strip().lower()
        if conferma != "y":
            logger.info("❌ Annullato.")
            return

    logger.info("🚀 Avvio sostituzione...", extra={"dry_run": dry_run, "regex_mode": regex_mode})
    replace_in_files(found_files, find_str, replace_str, regex_mode=regex_mode, dry_run=dry_run)
    logger.info("✅ Operazione completata.")


# ===============
# Menu principale
# ===============
def main_menu():
    while True:
        logger.info("=========== REFACTOR TOOL ===========")
        logger.info("1. 🔎 Trova (solo ricerca)")
        logger.info("2. ✏️ Trova & Sostituisci")
        logger.info("3. ❌ Esci")
        logger.info("=====================================")
        choice = input("Scegli un'opzione (numero): ").strip()
        if choice == "1":
            find_only_menu()
        elif choice == "2":
            find_and_replace_menu()
        elif choice == "3":
            logger.info("👋 Uscita.")
            break
        else:
            logger.warning("❌ Scelta non valida. Riprova.", extra={"choice": choice})


if __name__ == "__main__":
    main_menu()
