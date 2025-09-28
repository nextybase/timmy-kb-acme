from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

TARGETS = [
    Path("README.md"),
    Path("docs/developer_guide.md"),
    Path("docs/user_guide.md"),
    Path("docs/index.md"),
    Path("docs/policy_push.md"),
    Path("docs/versioning_policy.md"),
    Path("docs/guida_ui.md"),
    Path("docs/architecture.md"),
]


def _latin1(hex_bytes: str) -> str:
    """Decode a mojibake sequence expressed with latin-1 bytes."""
    return bytes.fromhex(hex_bytes).decode("latin1")


REPLACEMENTS: dict[str, str] = {
    _latin1("E28094"): "—",  # em dash
    _latin1("E28093"): "–",  # en dash
    _latin1("E2809C"): "“",  # left double quote
    _latin1("E2809D"): "”",  # right double quote
    _latin1("E28098"): "‘",  # left single quote
    _latin1("E28099"): "’",  # right single quote
    _latin1("E280A6"): "…",  # ellipsis
    _latin1("C3A9"): "é",
    _latin1("C3A8"): "è",
    _latin1("C3B2"): "ò",
    _latin1("C3B9"): "ù",
    _latin1("C3AC"): "ì",
    _latin1("C3A0"): "à",
    _latin1("C3A0") + " ": "à ",
    "pu" + _latin1("C3B2"): "può",
    "modalit" + _latin1("C3A0"): "modalità",
    "funzionalit" + _latin1("C3A0"): "funzionalità",
    "l" + _latin1("E28099"): "l’",
    "d" + _latin1("E28099"): "d’",
    "c" + _latin1("E28099"): "c’",
    "L" + _latin1("E28099"): "L’",
    "D" + _latin1("E28099"): "D’",
}


def fix_text(text: str) -> str:
    fixed = text
    for corrupted, clean in REPLACEMENTS.items():
        fixed = fixed.replace(corrupted, clean)
    return fixed


def _atomic_write(path: Path, content: str) -> None:
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, newline="") as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)
    os.replace(temp_path, path)


def main() -> None:
    changed: list[str] = []
    for target in TARGETS:
        if not target.exists():
            continue
        original = target.read_text(encoding="utf-8", errors="ignore")
        fixed = fix_text(original)
        if fixed != original:
            _atomic_write(target, fixed)
            changed.append(str(target))
    if changed:
        print("Fixed mojibake in:", ", ".join(changed))
    else:
        print("No changes")


if __name__ == "__main__":
    main()
