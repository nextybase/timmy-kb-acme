
#!/usr/bin/env python3
# Audit unified logging usage across a Python repo.
#
# What it does
# ------------
# - Scans all *.py under `--src` (default: src/), excluding any path matching `--exclude` (default: tools).
# - Flags any use of local/legacy logging patterns (basicConfig, getLogger, handlers) in pipeline modules.
# - Ensures orchestrators use the central logger and (ideally) pass a single log_file (onboarding.log).
# - Generates a Markdown report (+ JSON) with per-file findings and suggested fixes.
#
# Usage
# -----
#   python audit_logging.py --src src --exclude tools --report audit_logging_report.md
#
# Exit codes
# ----------
#   0 => No issues found (all good) or only warnings
#   1 => At least one 'FAIL' issue detected

import argparse
import re
import sys
import datetime
from pathlib import Path
from typing import Dict, List, Any

DEFAULT_ORCHESTRATORS = {"pre_onboarding.py", "onboarding_full.py"}

PATTERNS = {
    "basicConfig": re.compile(r"\blogging\.basicConfig\s*\("),
    "getLogger": re.compile(r"\blogging\.getLogger\s*\("),
    "fileHandler": re.compile(r"\b(FileHandler|RotatingFileHandler|TimedRotatingFileHandler)\s*\("),
    "streamHandler": re.compile(r"\bStreamHandler\s*\("),
    "addHandler": re.compile(r"\.addHandler\s*\("),
    "setLevel": re.compile(r"\.setLevel\s*\("),
    "getStructuredLogger": re.compile(r"\bget_structured_logger\s*\("),
    "getStructuredLoggerCall": re.compile(r"\bget_structured_logger\s*\((?P<args>.*?)\)", re.DOTALL),
}

def read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(errors="ignore")

def analyze_file(py_file: Path, orchestrators: set) -> Dict[str, Any]:
    text = read_text_safe(py_file)
    rel = str(py_file)

    is_orchestrator = py_file.name in orchestrators
    is_pipeline = "src/pipeline/" in rel.replace("\\", "/") or "/pipeline/" in rel.replace("\\", "/")

    findings: Dict[str, Any] = {
        "file": rel,
        "category": "orchestrator" if is_orchestrator else ("pipeline" if is_pipeline else "other"),
        "issues": [],
        "warnings": [],
        "notes": [],
        "suggestions": [],
    }

    # Pattern matches
    has_basic = bool(PATTERNS["basicConfig"].search(text))
    has_getLogger = bool(PATTERNS["getLogger"].search(text))
    has_fileHandler = bool(PATTERNS["fileHandler"].search(text))
    has_streamHandler = bool(PATTERNS["streamHandler"].search(text))
    has_addHandler = bool(PATTERNS["addHandler"].search(text))
    has_setLevel = bool(PATTERNS["setLevel"].search(text))
    has_getStructured = bool(PATTERNS["getStructuredLogger"].search(text))

    structured_calls = [m.group("args") for m in PATTERNS["getStructuredLoggerCall"].finditer(text)]
    passes_log_file = any("log_file=" in c for c in structured_calls)

    # Heuristics per-category
    if is_pipeline:
        # Pipeline modules must not self-configure logging nor pass log_file
        if has_basic:
            findings["issues"].append("Uses logging.basicConfig() (pipeline modules must not configure logging).")
        if has_fileHandler or has_streamHandler or has_addHandler:
            findings["issues"].append("Creates/attaches logging handlers (should rely on central logger only).")
        if has_setLevel:
            findings["issues"].append("Calls logger.setLevel() (levels should be configured centrally).")
        if passes_log_file:
            findings["issues"].append("Passes log_file= to get_structured_logger (only orchestrators should set the file).")
        if has_getLogger and not has_getStructured:
            findings["issues"].append("Uses logging.getLogger() but not get_structured_logger().")
        if not has_getStructured:
            findings["warnings"].append("Does not import/use get_structured_logger() explicitly (double-check).")

        # Suggestions for pipeline modules
        if findings["issues"] or findings["warnings"]:
            findings["suggestions"].append("from pipeline.logging_utils import get_structured_logger")
            findings["suggestions"].append("logger = get_structured_logger(__name__)  # no log_file here")
            if has_basic:
                findings["suggestions"].append("# remove logging.basicConfig(...)")
            if has_fileHandler or has_streamHandler or has_addHandler:
                findings["suggestions"].append("# remove local handler creation / logger.addHandler(...)")
            if has_setLevel:
                findings["suggestions"].append("# remove logger.setLevel(...); set levels centrally")
            if passes_log_file:
                findings["suggestions"].append("# remove log_file=... in pipeline modules")
            if has_getLogger:
                findings["suggestions"].append("# replace logging.getLogger(...) with get_structured_logger(__name__)")

    elif is_orchestrator:
        # Orchestrators may set the file sink (single, unified)
        if has_basic:
            findings["issues"].append("Uses logging.basicConfig() (use get_structured_logger with log_file instead).")
        if has_fileHandler or has_streamHandler or has_addHandler:
            findings["issues"].append("Manually creates/attaches handlers (use get_structured_logger with log_file).")
        if has_setLevel:
            findings["warnings"].append("Calls logger.setLevel(); ensure final level is still controlled centrally.")
        if not has_getStructured:
            findings["issues"].append("Does not use get_structured_logger().")
        if not passes_log_file:
            findings["warnings"].append("Consider passing log_file=<output_dir>/onboarding.log for unified sink.")

        # Suggestions for orchestrators
        if findings["issues"] or findings["warnings"]:
            findings["suggestions"].append("from pipeline.logging_utils import get_structured_logger")
            findings["suggestions"].append("logger = get_structured_logger('pre_onboarding' if 'pre_onboarding' in __file__ else 'onboarding_full', log_file=context.output_dir / 'onboarding.log')")
            if has_basic:
                findings["suggestions"].append("# remove logging.basicConfig(...)")
            if has_fileHandler or has_streamHandler or has_addHandler:
                findings["suggestions"].append("# remove manual handler creation; rely on get_structured_logger(...)")

    else:
        # Other scripts in src root: should behave like pipeline modules unless explicitly orchestrators
        if has_basic:
            findings["issues"].append("Uses logging.basicConfig() (should use central logger).")
        if has_fileHandler or has_streamHandler or has_addHandler:
            findings["issues"].append("Creates/attaches logging handlers (should rely on central logger).")
        if has_setLevel:
            findings["warnings"].append("Calls logger.setLevel(); levels should be set centrally.")
        if has_getLogger and not has_getStructured:
            findings["issues"].append("Uses logging.getLogger() but not get_structured_logger().")
        if not has_getStructured:
            findings["warnings"].append("Does not import/use get_structured_logger() explicitly.")
        if passes_log_file:
            findings["warnings"].append("Passes log_file= to get_structured_logger (only orchestrators should set the file).")

        if findings["issues"] or findings["warnings"]:
            findings["suggestions"].append("from pipeline.logging_utils import get_structured_logger")
            findings["suggestions"].append("logger = get_structured_logger(__name__)  # or orchestrator pattern if main entrypoint")

    return findings

def main():
    ap = argparse.ArgumentParser(description="Audit unified logging usage across src/")
    ap.add_argument("--src", default="src", help="Path to the src/ folder (default: src)")
    ap.add_argument("--exclude", default="tools", help="Subfolder to exclude (default: tools)")
    ap.add_argument("--report", default="audit_logging_report.md", help="Output Markdown report path")
    ap.add_argument("--json", default="audit_logging_report.json", help="Also write a JSON report here")
    ap.add_argument("--orchestrators", nargs="*", default=list(DEFAULT_ORCHESTRATORS),
                    help="Orchestrator filenames allowed to set log_file (default: pre_onboarding.py onboarding_full.py)")
    args = ap.parse_args()

    src_path = Path(args.src).resolve()
    exclude = args.exclude
    orchestrators = set(args.orchestrators)

    if not src_path.exists():
        print(f"ERROR: src path not found: {src_path}", file=sys.stderr)
        sys.exit(1)

    py_files: List[Path] = []
    for p in src_path.rglob("*.py"):
        # skip excluded subfolder
        norm = str(p).replace("\\", "/")
        if f"/{exclude}/" in norm or norm.endswith(f"/{exclude}"):
            continue
        py_files.append(p)

    all_findings: List[Dict[str, Any]] = []
    for f in sorted(py_files):
        all_findings.append(analyze_file(f, orchestrators))

    # Summaries
    fail = [x for x in all_findings if x["issues"]]
    warn = [x for x in all_findings if (not x["issues"] and x["warnings"])]
    ok = [x for x in all_findings if not x["issues"] and not x["warnings"]]

    # Write Markdown report
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines: List[str] = []
    md_lines.append("# Unified Logging Audit Report")
    md_lines.append("")
    md_lines.append(f"- Generated: {now}")
    md_lines.append(f"- Source: `{src_path}` (excluding `/{exclude}/`)")
    md_lines.append(f"- Orchestrators: {', '.join(sorted(orchestrators))}")
    md_lines.append("")
    md_lines.append("**Summary**")
    md_lines.append("")
    md_lines.append(f"- Files scanned: **{len(all_findings)}**")
    md_lines.append(f"- FAIL (issues): **{len(fail)}**")
    md_lines.append(f"- WARN (only warnings): **{len(warn)}**")
    md_lines.append(f"- OK: **{len(ok)}**")
    md_lines.append("")

    def render_block(items: List[Dict[str, Any]], title: str):
        if not items:
            md_lines.append(f"## {title}")
            md_lines.append("None 🎉")
            md_lines.append("")
            return
        md_lines.append(f"## {title}")
        md_lines.append("")
        for it in items:
            md_lines.append(f"### `{it['file']}`  \n*Category*: `{it['category']}`")
            if it["issues"]:
                md_lines.append("- **Issues**:")
                for s in it["issues"]:
                    md_lines.append(f"  - {s}")
            if it["warnings"]:
                md_lines.append("- **Warnings**:")
                for s in it["warnings"]:
                    md_lines.append(f"  - {s}")
            if it["suggestions"]:
                md_lines.append("- **Suggested changes**:")
                md_lines.append("  ```python")
                for s in it["suggestions"]:
                    md_lines.append(f"  {s}")
                md_lines.append("  ```")
            md_lines.append("")

    render_block(fail, "Files requiring FIX (FAIL)")
    render_block(warn, "Files to review (WARN)")
    render_block(ok, "Files OK")

    report_path = Path(args.report).resolve()
    report_path.write_text("\n".join(md_lines), encoding="utf-8")

    json_path = Path(args.json).resolve()
    import json as _json
    json_path.write_text(_json.dumps(all_findings, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Report written to: {report_path}")
    print(f"JSON written to:   {json_path}")
    print("")
    if fail:
        print(f"FAIL: {len(fail)} file(s) need fixes.")
        sys.exit(1)
    else:
        print("OK: no blocking issues (some warnings may still be present).")
        sys.exit(0)

if __name__ == "__main__":
    main()
