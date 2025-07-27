import os
import re
import sys

from pathlib import Path

# Trova sempre la root del progetto (dove c’è src/)
HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parents[2]  # Modifica se il livello è diverso

SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pipeline.logging_utils import get_structured_logger

ROOT = Path(__file__).parent.parent.parent.resolve()
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

logger = get_structured_logger("pipeline.refactor")

EXT_INCLUDE = {".py", ".yaml", ".yml", ".md"}
DIR_EXCLUDE = {".git", "venv", "__pycache__", ".mypy_cache", ".idea", ".vscode"}

def should_check_file(fname):
    return any(fname.endswith(ext) for ext in EXT_INCLUDE)

def scan_occurrences(root, find_str, regex_mode=False):
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
            logger.warning(f"⚠️ Errore leggendo {fpath}: {e}")
    return found_files

def replace_in_files(file_list, find_str, replace_str, regex_mode=False, dry_run=True):
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
                    print(f"\n📄 [ANTEPRIMA] Modifiche in: {fpath}")
                    print("-" * 60)
                    lines_old = original.splitlines()
                    lines_new = modified.splitlines()
                    for old, new in zip(lines_old, lines_new):
                        if old != new:
                            print(f"- {old}")
                            print(f"+ {new}")
                else:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(modified)
                    logger.info(f"✏️ Sostituzione effettuata in: {fpath}")
        except Exception as e:
            logger.warning(f"⚠️ Errore nel modificare {fpath}: {e}")

def refactor_pipeline_settings():
    print("\n🔁 Refactor massivo pipeline.config_utils → config_utils")
    default_root = str(Path(__file__).parent.parent.resolve())
    root = input(f"📁 Cartella da cui partire [default: {default_root}]: ").strip() or default_root
    dry_run = input("🧪 Solo anteprima/dry-run? [Y/n]: ").strip().lower() != "n"

    # Pattern 1: import diretto
    regex1 = r"from\s+pipeline\.settings\s+import\s+([^\n]+)"
    repl1 = r"from pipeline.config_utils import \1"

    # Pattern 2: uso modulo (import semplice o referenze)
    regex2 = r"pipeline\.settings"
    repl2 = "pipeline.config_utils"

    # Pattern 3: chiamate a get_config()
    regex3 = r"get_settings\s*\("
    repl3 = "get_config("

    # Sostituzioni in sequenza
    patterns = [
        (regex1, repl1, True, "import diretto"),
        (regex2, repl2, True, "referenze modulo"),
        (regex3, repl3, True, "chiamate funzione"),
    ]

    for regex, repl, regex_mode, descr in patterns:
        print(f"\n🔎 Cerca/Sostituisci: {descr} — Pattern: {regex} -> {repl}")
        found_files = scan_occurrences(root, regex, regex_mode=regex_mode)
        print(f"\n📊 Risultati per pattern '{regex}':")
        if not found_files:
            print("✅ Nessuna occorrenza trovata.")
            continue
        for fpath, n in found_files:
            print(f" - {fpath}  ({n} occorrenze)")
        replace_in_files(found_files, regex, repl, regex_mode=regex_mode, dry_run=dry_run)

    print("\n✅ Refactor completato.")

def find_and_replace_menu():
    print("\n🔎 [Find & Replace] — Ricerca e sostituzione nei file di progetto")
    find_str = input("🔍 Stringa da trovare (regex supportato): ").strip()
    if not find_str:
        print("❌ Stringa vuota. Annullato.")
        return
    replace_str = input("✏️ Stringa di sostituzione (vuoto = solo dry-run): ")
    regex_mode = input("🔁 Usa modalità REGEX? [y/N]: ").strip().lower() == "y"
    dry_run = input("🧪 Vuoi solo simulare la sostituzione? [Y/n]: ").strip().lower() != "n"
    default_root = str(Path(__file__).parent.parent.resolve())
    root = input(f"📁 Cartella da cui partire [default: {default_root}]: ").strip() or default_root
    print(f"\n⏳ Scansione in corso nella cartella: {root}")
    found_files = scan_occurrences(root, find_str, regex_mode=regex_mode)
    print(f"\n📊 Risultati per '{find_str}':")
    if not found_files:
        print("✅ Nessuna occorrenza trovata.")
        return
    for fpath, n in found_files:
        print(f" - {fpath}  ({n} occorrenze)")
    if dry_run:
        print("\n🔍 Modalità dry-run: mostrerò i cambiamenti ma non scriverò nulla.")
    else:
        conferma = input("\n⚠️ Confermi la sostituzione su questi file? (y/N): ").strip().lower()
        if conferma != "y":
            print("❌ Annullato.")
            return
    print("\n🚀 Avvio sostituzione...")
    replace_in_files(found_files, find_str, replace_str, regex_mode=regex_mode, dry_run=dry_run)
    print("\n✅ Operazione completata.")

def main_menu():
    while True:
        print("\n=========== REFACTOR TOOL ==========")
        print("1. 🔁 Refactor pipeline.config_utils → config_utils (automatico, sicuro)")
        print("2. 🔎 Find & Replace personalizzato")
        print("3. ❌ Esci")
        print("====================================")
        choice = input("Scegli un'opzione (numero): ").strip()
        if choice == "1":
            refactor_pipeline_settings()
        elif choice == "2":
            find_and_replace_menu()
        elif choice == "3":
            print("👋 Uscita.")
            break
        else:
            print("❌ Scelta non valida. Riprova.")

if __name__ == "__main__":
    main_menu()
