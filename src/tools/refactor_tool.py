import os
import re
import sys
import logging
from pathlib import Path

# Setup logging (opzionale: puoi loggare anche su file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("refactor_tool")

EXT_INCLUDE = {".py", ".yaml", ".yml", ".md"}
DIR_EXCLUDE = {".git", "venv", "__pycache__", ".mypy_cache", ".idea", ".vscode"}

def should_check_file(fname):
    return any(fname.endswith(ext) for ext in EXT_INCLUDE)

def scan_occurrences(root, find_str):
    all_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DIR_EXCLUDE]
        for fname in filenames:
            if should_check_file(fname):
                fpath = os.path.join(dirpath, fname)
                all_files.append(fpath)
    found_files = []
    total = len(all_files)
    for i, fpath in enumerate(all_files, 1):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            matches = list(re.finditer(re.escape(find_str), text))
            if matches:
                found_files.append((fpath, len(matches)))
        except Exception as e:
            logger.warning(f"⚠️ Errore nel leggere {fpath}: {e}")
        if i % 10 == 0 or i == total:
            perc = int(100 * i / total)
            print(f"  ...{i}/{total} file ({perc}%)", end='\r')
    print()
    return found_files

def replace_in_files(file_list, find_str, replace_str):
    total = len(file_list)
    for i, (fpath, _) in enumerate(file_list, 1):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            new_text = text.replace(find_str, replace_str)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_text)
            logger.info(f"✏️ Sostituzione effettuata in: {fpath}")
        except Exception as e:
            logger.warning(f"⚠️ Errore nel modificare {fpath}: {e}")
        if i % 5 == 0 or i == total:
            perc = int(100 * i / total)
            print(f"  ...{i}/{total} file modificati ({perc}%)", end='\r')
    print()

def find_and_replace_menu():
    print("\n🔎 [Find & Replace] — Ricerca (e sostituzione) interattiva su file di progetto\n")

    find_str = input("Stringa da trovare: ").strip()
    if not find_str:
        print("❌ Stringa di ricerca vuota. Operazione annullata.")
        return

    replace_str = input("Stringa di sostituzione (lascia vuoto per solo ricerca): ")
    do_replace = bool(replace_str)

    # Usa la root del progetto come default!
    default_root = str(Path(__file__).parent.parent.resolve())
    root = input(f"Cartella da cui partire [default: {default_root}]: ").strip() or default_root

    print(f"\n⏳ Scansione in corso nella cartella: {root}")
    found_files = scan_occurrences(root, find_str)

    print(f"\n📝 Risultati per '{find_str}':")
    if not found_files:
        print("✅ Nessuna occorrenza trovata!")
        return
    else:
        for fpath, n in found_files:
            print(f" - {fpath}  ({n} occorrenze)")

    if do_replace:
        conferma = input("\nApplico davvero la sostituzione su questi file? (y/N): ").strip().lower()
        if conferma == "y":
            print("\n✏️ Sostituzione in corso...")
            replace_in_files(found_files, find_str, replace_str)
            print("\n✅ Sostituzione effettuata!")
        else:
            print("\n💡 Dry-run: nessuna modifica fatta.")
    else:
        print("\n💡 Ricerca completata (solo scan, nessuna modifica).")

def main_menu():
    while True:
        print("\n=========== REFACTOR TOOL ===========")
        print("1. Find & Replace (ricerca e sostituzione stringhe)")
        print("2. Esci")
        print("=====================================")
        choice = input("Scegli un'opzione (numero): ").strip()
        if choice == "1":
            find_and_replace_menu()
        elif choice == "2":
            print("👋 Uscita.")
            break
        else:
            print("❌ Scelta non valida. Riprova.\n")

if __name__ == "__main__":
    main_menu()
