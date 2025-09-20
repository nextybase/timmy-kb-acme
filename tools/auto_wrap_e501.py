#!/usr/bin/env python3
"""
tools/auto_wrap_e501.py

Obiettivo: ridurre E501 (linee > maxcol) senza cambiare il comportamento.
Strategia:
  1) (Opzionale) Docstring: prova docformatter (se installato) con wrap=100.
  2) Commenti: avvolgi con textwrap (preserva indent e '# ').
  3) Stringhe "lunghe note":
     - argparse: help="..." -> help=("..." "...")
     - logging/st.* caption/warning/error/info/debug: primo arg stringa -> avvolto tra ()
     - linee con stringa letterale singola molto lunga -> avvolte tra ()
  4) Non tocca codice che non contiene letterali/commenti.

Uso:
  python tools/auto_wrap_e501.py --paths src tests --width 100 [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import fill, indent

# pattern: detect long comment lines
COMMENT_RE = re.compile(r"^(\s*)#( ?)(.*\S.*)$")
# detect lines like help="...very long..."
ARGPARSE_HELP_RE = re.compile(r'(\bhelp\s*=\s*)("|\')(.*)("|\')\s*(\)|,)?$')
# detect logging/string functions: logging.info("..."), logger.info("..."), st.caption("..."), st.warning("...")
CALL_STR_FUNCS = (
    r"(?:logging|logger)\.(?:debug|info|warning|error|exception|critical)",
    r"st\.(?:caption|warning|error|info|success)",
    r"print",
)
CALL_LINE_RE = re.compile(rf'^(\s*)(?:{"|".join(CALL_STR_FUNCS)})\s*\(\s*("|\')(.*)("|\')(.*)$')

# naive long literal string on a single line, not preceded by f/r/b/u prefixes
BARE_STR_RE = re.compile(r'^(\s*)([A-Za-z0-9_\.]*\s*=\s*)?("|\')(.{40,})("|\')(.*)$')

TRIPLE_QUOTE_START = re.compile(r'^(\s*)([ruRU]?)("""|\'\'\')')
TRIPLE_QUOTE_END = re.compile(r'("""|\'\'\')')


def have_docformatter() -> bool:
    try:
        subprocess.run(["docformatter", "--version"], capture_output=True, text=True, check=False)
        return True
    except Exception:
        return False


def run_docformatter(paths: list[Path], width: int, dry: bool) -> None:
    if not have_docformatter():
        return
    cmd = ["docformatter", "-ri", f"--wrap-summaries={width}", f"--wrap-descriptions={width}"]
    cmd += [str(p) for p in paths]
    if dry:
        print("[dry-run] would run:", " ".join(cmd))
        return
    subprocess.run(cmd, check=False)


def wrap_comment_line(line: str, width: int) -> str:
    m = COMMENT_RE.match(line)
    if not m:
        return line
    lead_ws, hash_sp, text = m.groups()
    prefix = f"{lead_ws}#{hash_sp}"
    # preserve bullets/code fences: skip wrapping if startswith ``` or '-' or '    '
    if text.strip().startswith("```") or text.strip().startswith("* ") or text.strip().startswith("- "):
        return line
    wrapped = fill(text, width=width - len(prefix))
    return prefix + wrapped.replace("\n", "\n" + prefix)


def split_string_literal(s: str, width: int) -> list[str]:
    """Split a long string into chunks <= width, break on spaces where possible."""
    words = re.split(r"(\s+)", s)
    out, cur, cur_len = [], [], 0
    maxw = max(16, width)  # avoid micro-chunks
    for w in words:
        wlen = len(w)
        if cur_len + wlen <= maxw:
            cur.append(w)
            cur_len += wlen
        else:
            out.append("".join(cur).strip())
            cur = [w]
            cur_len = wlen
    if cur:
        out.append("".join(cur).strip())
    # ensure no empty segments
    return [seg for seg in out if seg]


def wrap_help_arg_line(line: str, width: int) -> str | None:
    m = ARGPARSE_HELP_RE.match(line.rstrip())
    if not m:
        return None
    head, q1, content, q2, trailer = m.groups()
    content = content.replace("\\n", "\n")
    pieces = split_string_literal(content, width=width - 8)
    joined = "\n".join(f'        "{p}"' for p in pieces if p)
    trailer = trailer or ""
    return f"{head}(\n{joined}\n    ){trailer}"


def wrap_call_with_string(line: str, width: int) -> str | None:
    m = CALL_LINE_RE.match(line.rstrip())
    if not m:
        return None
    lead, q1, content, q2, rest = m.groups()
    # If there are format args after the literal, keep them on their line
    tail = rest.strip()
    pieces = split_string_literal(content, width=width - 8)
    lit_block = "\n".join(f'{lead}    "{p}"' for p in pieces if p)
    if tail and not tail.startswith(")"):
        # keep tail (e.g., , var1, var2) on next line
        return f"{lead}({lit_block},\n{lead}    {tail}\n{lead})"
    return f"{lead}({lit_block}\n{lead})"


def wrap_bare_string(line: str, width: int) -> str | None:
    m = BARE_STR_RE.match(line.rstrip())
    if not m:
        return None
    lead, lhs, q1, content, q2, tail = m.groups()
    lhs = lhs or ""
    # avoid f-strings or prefixes: heuristically skip if prior char has f/r/u/b just before quote
    if re.search(r'(?:^|[=\(,\s])[fFrRuUbB]("|\')', line):
        return None
    if len(line) <= width:
        return None
    pieces = split_string_literal(content, width=width - max(8, len(lhs)))
    inner = "\n".join(f'{lead}    "{p}"' for p in pieces if p)
    if lhs:
        return f"{lead}{lhs}(\n{inner}\n{lead}){tail or ''}"
    else:
        return f"{lead}(\n{inner}\n{lead}){tail or ''}"


def process_file(path: Path, width: int, dry: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    changed = False

    # 1) Wrap comments
    new_lines = []
    in_triple = False
    triple_quote = None
    for line in lines:
        # detect triple-quoted regions to avoid wrapping comments inside code fences of docstrings
        if not in_triple:
            mstart = TRIPLE_QUOTE_START.match(line)
            if mstart:
                in_triple = True
                triple_quote = mstart.group(3)
                new_lines.append(line)
                continue
        else:
            if TRIPLE_QUOTE_END.search(line):
                in_triple = False
                triple_quote = None
            new_lines.append(line)
            continue

        if len(line) > width:
            m = COMMENT_RE.match(line)
            if m:
                wrapped = wrap_comment_line(line, width)
                if wrapped != line:
                    changed = True
                    new_lines.append(wrapped)
                    continue
        new_lines.append(line)

    lines = new_lines

    # 2) Wrap specific string patterns per line
    out_lines = []
    for line in lines:
        if len(line) <= width:
            out_lines.append(line)
            continue

        new_line = (
            wrap_help_arg_line(line, width) or wrap_call_with_string(line, width) or wrap_bare_string(line, width)
        )
        if new_line is not None:
            changed = True
            out_lines.append(new_line)
        else:
            out_lines.append(line)
    new_text = "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")

    if changed and not dry:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)
        path.write_text(new_text, encoding="utf-8")
    return changed


def collect_targets(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_file() and p.suffix == ".py":
            out.append(p)
        elif p.is_dir():
            out.extend(q for q in p.rglob("*.py") if q.is_file())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="+", default=["src", "tests"], help="Cartelle/file da processare")
    ap.add_argument("--width", type=int, default=100, help="colonna max")
    ap.add_argument("--dry-run", action="store_true", help="non scrive, mostra solo report")
    args = ap.parse_args()

    targets = collect_targets([Path(p) for p in args.paths])
    # Step 0: docformatter (se presente)
    run_docformatter(targets, args.width, args.dry_run)

    changed_total = 0
    for fp in targets:
        try:
            changed = process_file(fp, args.width, args.dry_run)
            if changed:
                changed_total += 1
                print(f"[wrap] {fp}")
        except Exception as e:
            print(f"[skip] {fp}: {e}")

    print(f"Done. Files changed: {changed_total}/{len(targets)}")
    if args.dry_run:
        print("Dry-run: nessuna modifica scritta. Riesegui senza --dry-run per applicare.")


if __name__ == "__main__":
    main()
