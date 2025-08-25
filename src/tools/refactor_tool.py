#!/usr/bin/env python3
# src/tools/refactor_tool.py
from __future__ import annotations

import os
import re
import sys
import difflib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple, Optional, Dict

# ───────────────────────── Bootstrap import "pipeline.*" ─────────────────────────
def _setup_src_and_root() -> Tuple[Path, Path]:
    """
    Risale la gerarchia a partire da questo file per trovare la cartella 'src'
    e la root di progetto (genitore di 'src'). Aggiunge 'src/' a sys.path.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        src_dir = parent / "src"
        if src_dir.is_dir():
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            return src_dir, parent
    raise RuntimeError("Impossibile trovare 'src/' nella gerarchia del progetto.")

SRC_DIR, PROJECT_ROOT = _setup_src_and_root()

# ────────────────────────── Import infrastruttura pipeline ──────────────────────
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, is_safe_subpath
from pipeline.file_utils import safe_write_text

# ────────────────────────────── Costanti / policy ───────────────────────────────
EXT_INCLUDE = {".py", ".yaml", ".yml", ".md"}
DIR_EXCLUDE = {".git", "venv", "__pycache__", ".mypy_cache", ".idea", ".vscode", "node_modules"}

# Logger creato in main() (evita handler duplicati)
logger = None  # type: ignore[assignment]


# ──────────────────────────────── Utils base ───────────────────────────────────
def _iter_candidate_files(root: Path) -> Iterable[Path]:
    """Itera tutti i file ammessi partendo da root, saltando le dir escluse."""
    for dirpath, dirnames, filenames in os.walk(root):
        # filtra directory in-place
        dirnames[:] = [d for d in dirnames if d not in DIR_EXCLUDE]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in EXT_INCLUDE:
                yield p


def _compile_pattern(find_str: str, *, regex_mode: bool, ignore_case: bool) -> re.Pattern:
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    return re.compile(find_str if regex_mode else re.escape(find_str), flags)


def _unified_diff(original: str, modified: str, fpath: Path) -> str:
    a = original.splitlines(keepends=False)
    b = modified.splitlines(keepends=False)
    diff = difflib.unified_diff(
        a, b,
        fromfile=f"{fpath}:before",
        tofile=f"{fpath}:after",
        lineterm=""
    )
    return "\n".join(diff)


# ───────────────────────────── Scansione / sostituzione ────────────────────────
@dataclass
class ScanOptions:
    regex_mode: bool = False
    ignore_case: bool = False


def scan_occurrences(root: Path, find_str: str, opts: ScanOptions) -> List[Tuple[Path, int]]:
    """
    Scansiona i file di testo ammessi sotto 'root' e ritorna
    [(path, num_match), ...] per i file con almeno un match.
    """
    pat = _compile_pattern(find_str, regex_mode=opts.regex_mode, ignore_case=opts.ignore_case)
    results: List[Tuple[Path, int]] = []
    for fpath in _iter_candidate_files(root):
        try:
            if not is_safe_subpath(fpath, root):
                # Soft check: non autorizza scritture, ma evita letture sospette fuori scope
                continue
            text = fpath.read_text(encoding="utf-8")
            n = len(list(pat.finditer(text)))
            if n > 0:
                results.append((fpath, n))
        except Exception as e:
            logger.warning("⚠️ Errore leggendo file", extra={"file_path": str(fpath), "error": str(e)})
    return results


@dataclass
class ReplaceOptions:
    regex_mode: bool = False
    ignore_case: bool = False
    dry_run: bool = True
    create_backup: bool = False  # in prospettiva si può abilitare come default=True


def replace_in_files(
    files: List[Tuple[Path, int]],
    find_str: str,
    replace_str: str,
    root: Path,
    opts: ReplaceOptions,
) -> Dict[str, int]:
    """
    Applica la sostituzione sui file passati.
    - In dry-run mostra i diff senza scrivere.
    - In modalità scrittura: path-safety STRONG + commit atomico tramite safe_write_text.
    Ritorna un piccolo report: {"files_changed": X, "replacements": Y}.
    """
    pat = _compile_pattern(find_str, regex_mode=opts.regex_mode, ignore_case=opts.ignore_case)
    changed_files = 0
    total_repl = 0

    for fpath, _ in files:
        try:
            original = fpath.read_text(encoding="utf-8")
            if opts.regex_mode:
                modified, n = pat.subn(replace_str, original)
            else:
                # Se non regex, pat è comunque compilato su re.escape(find_str) -> usiamo subn per contare
                modified, n = pat.subn(replace_str, original)

            if n == 0 or original == modified:
                continue

            if opts.dry_run:
                logger.info("📄 [ANTEPRIMA] Modifiche previste", extra={"file_path": str(fpath), "replacements": n})
                diff_text = _unified_diff(original, modified, fpath)
                if diff_text.strip():
                    logger.info(diff_text)
                else:
                    logger.info("Nessuna differenza visualizzabile (possibile variazione di soli EOL).", extra={"file_path": str(fpath)})
            else:
                # STRONG guard: autorizza la write SOLO se fpath sta sotto root
                ensure_within(root, fpath)

                # Opzionale: backup fianco-a-fianco
                if opts.create_backup:
                    bak = fpath.with_suffix(fpath.suffix + ".bak")
                    ensure_within(root, bak)
                    safe_write_text(bak, original, encoding="utf-8", atomic=True)

                safe_write_text(fpath, modified, encoding="utf-8", atomic=True)
                logger.info("✏️ Sostituzione effettuata", extra={"file_path": str(fpath), "replacements": n})

            changed_files += 1
            total_repl += n
        except Exception as e:
            logger.warning("⚠️ Errore nel modificare file", extra={"file_path": str(fpath), "error": str(e)})

    return {"files_changed": changed_files, "replacements": total_repl}


# ──────────────────────────────── Azioni menu ─────────────────────────────────
def _prompt_bool(prompt: str, default_no: bool = False) -> bool:
    ans = input(f"{prompt} [{'Y/n' if not default_no else 'y/N'}]: ").strip().lower()
    if not ans:
        return not default_no
    return ans in ("y", "yes", "s", "si", "sí")


def _ask_root(default: Path) -> Path:
    root_in = input(f"📁 Cartella da cui partire [default: {default}]: ").strip()
    root = Path(root_in) if root_in else default
    if not root.exists() or not root.is_dir():
        logger.error("❌ Cartella non valida.", extra={"file_path": str(root)})
        raise SystemExit(1)
    return root.resolve()


def action_find_only() -> None:
    logger.info("🔎 [Trova] — Ricerca nei file di progetto (senza modifiche)")
    find_str = input("🔍 Stringa da trovare: ").strip()
    if not find_str:
        logger.error("❌ Stringa vuota. Annullato.")
        return
    regex_mode = _prompt_bool("Usare modalità REGEX?", default_no=True)
    ignore_case = _prompt_bool("Ignorare maiuscole/minuscole (case-insensitive)?", default_no=True)
    default_root = PROJECT_ROOT
    root = _ask_root(default_root)

    logger.info("⏳ Scansione in corso", extra={"file_path": str(root), "mode": "regex" if regex_mode else "plain", "ignore_case": ignore_case})
    found_files = scan_occurrences(root, find_str, ScanOptions(regex_mode=regex_mode, ignore_case=ignore_case))

    logger.info("📊 Risultati ricerca", extra={"query": find_str})
    if not found_files:
        logger.info("✅ Nessuna occorrenza trovata.", extra={"query": find_str})
        return

    for fpath, n in sorted(found_files, key=lambda t: (-t[1], str(t[0]))):
        logger.info("Match trovati", extra={"file_path": str(fpath), "occurrences": n})
    logger.info("Totale file con occorrenze", extra={"count": len(found_files)})


def action_find_and_replace() -> None:
    logger.info("✏️ [Trova & Sostituisci] — Ricerca e sostituzione nei file di progetto")
    find_str = input("🔍 Stringa da trovare: ").strip()
    if not find_str:
        logger.error("❌ Stringa vuota. Annullato.")
        return
    replace_str = input("✏️ Stringa di sostituzione (vuoto = cancella/match → stringa vuota): ")
    regex_mode = _prompt_bool("Usare modalità REGEX?", default_no=True)
    ignore_case = _prompt_bool("Ignorare maiuscole/minuscole (case-insensitive)?", default_no=True)
    dry_run = _prompt_bool("Eseguire prima una anteprima (dry-run)?", default_no=False)
    default_root = PROJECT_ROOT
    root = _ask_root(default_root)

    logger.info("⏳ Scansione in corso", extra={"file_path": str(root), "mode": "regex" if regex_mode else "plain", "ignore_case": ignore_case})
    found_files = scan_occurrences(root, find_str, ScanOptions(regex_mode=regex_mode, ignore_case=ignore_case))

    if not found_files:
        logger.info("✅ Nessuna occorrenza trovata.", extra={"query": find_str})
        return

    for fpath, n in sorted(found_files, key=lambda t: (-t[1], str(t[0]))):
        logger.info("Match trovati", extra={"file_path": str(fpath), "occurrences": n})

    if dry_run:
        logger.info("🔍 Modalità anteprima: mostrerò i cambiamenti ma non scriverò nulla.")
    else:
        conferma = input("⚠️ Confermi la sostituzione su questi file? (y/N): ").strip().lower()
        if conferma != "y":
            logger.info("❌ Annullato.")
            return

    report = replace_in_files(
        found_files,
        find_str,
        replace_str,
        root,
        ReplaceOptions(regex_mode=regex_mode, ignore_case=ignore_case, dry_run=dry_run, create_backup=False),
    )
    logger.info("✅ Operazione completata.", extra=report)


def action_find_todo_fixme() -> None:
    """Cerca TODO/FIXME nei sorgenti e stampa un report con righe e numeri di riga."""
    logger.info("🧩 [Cerca TODO/FIXME] — Individua note di sviluppo nei file di progetto")
    ignore_case = _prompt_bool("Ignorare maiuscole/minuscole (case-insensitive)?", default_no=False)
    default_root = PROJECT_ROOT
    root = _ask_root(default_root)

    tokens = r"(?:TODO|FIXME)"
    flags = re.IGNORECASE if ignore_case else 0
    pat = re.compile(rf"\b{tokens}\b", flags)

    results: Dict[Path, List[Tuple[int, str]]] = {}
    total = 0

    for fpath in _iter_candidate_files(root):
        try:
            if not is_safe_subpath(fpath, root):
                continue
            # Lettura riga-per-riga per numerare velocemente
            with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, start=1):
                    if pat.search(line):
                        snippet = line.rstrip()
                        if len(snippet) > 160:
                            snippet = snippet[:157] + "…"
                        results.setdefault(fpath, []).append((i, snippet))
                        total += 1
        except Exception as e:
            logger.warning("⚠️ Errore leggendo file", extra={"file_path": str(fpath), "error": str(e)})

    if not results:
        logger.info("✅ Nessun TODO/FIXME trovato.", extra={"file_path": str(root)})
        return

    # Report
    for fpath in sorted(results.keys(), key=lambda p: str(p)):
        items = results[fpath]
        logger.info("📄 File con TODO/FIXME", extra={"file_path": str(fpath), "count": len(items)})
        for ln, txt in items:
            logger.info(f"  L{ln:>5}: {txt}")

    logger.info("📊 Riepilogo TODO/FIXME", extra={"files": len(results), "occurrences": total})


# ────────────────────────────── Menu & renderer ────────────────────────────────
MENU_ITEMS: List[Tuple[str, str, callable]] = [
    ("1", "🔎 Trova (solo ricerca)", action_find_only),
    ("2", "✏️ Trova & Sostituisci", action_find_and_replace),
    ("3", "🧩 Cerca TODO/FIXME", action_find_todo_fixme),
    # Facile da estendere:
    # ("4", "📦 Rinominare package/modulo", future_action),
    # ("5", "🧹 Normalizzare import", future_action),
]

def _render_menu(items: List[Tuple[str, str, callable]]) -> str:
    """
    Restituisce una stringa con un menu “grafico” usando box-drawing Unicode.
    (Stampiamo con print() per evitare i prefissi del logger.)
    """
    title = "REFACTOR TOOL"
    subtitle = "Trova / Sostituisci · TODO/FIXME · regex · case-insensitive"
    lines = [f"{key}) {label}" for key, label, _ in items] + ["X) ❌ Esci"]

    w = max(
        42,
        len(title) + 4,
        len(subtitle) + 4,
        max(len(ln) for ln in lines) + 4,
    )

    top = "┌" + "─" * (w - 2) + "┐"
    sep = "├" + "─" * (w - 2) + "┤"
    bot = "└" + "─" * (w - 2) + "┘"

    def pad(s: str) -> str:
        return "│ " + s + " " * (w - 3 - len(s)) + "│"

    body = [
        top,
        pad(title.center(w - 4)),
        pad(subtitle.center(w - 4)),
        sep,
        *[pad(ln) for ln in lines],
        bot,
    ]
    return "\n".join(body)


def main_menu() -> None:
    while True:
        # menu “pulito” senza prefissi del logger
        print(_render_menu(MENU_ITEMS))
        choice = input("Scegli un'opzione: ").strip().lower()
        if choice in {"x", "q", "quit", "exit"}:
            logger.info("👋 Uscita.")
            break
        matched = [cb for key, _, cb in MENU_ITEMS if key == choice]
        if not matched:
            logger.warning("❌ Scelta non valida. Riprova.", extra={"choice": choice})
            continue
        try:
            matched[0]()  # esegue l'azione selezionata
        except SystemExit:
            raise
        except Exception as e:
            logger.exception(f"Errore durante l'azione selezionata: {e}")


# ────────────────────────────────── CLI entry ─────────────────────────────────
def main() -> int:
    global logger
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("tools.refactor", run_id=run_id)
    try:
        main_menu()
        return 0
    except KeyboardInterrupt:
        logger.info("⏹️ Interrotto dall'utente (Ctrl+C).")
        return 130
    except Exception as e:
        logger.exception(f"Errore non gestito: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
