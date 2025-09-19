from __future__ import annotations

from pathlib import Path

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

REPLACEMENTS: dict[str, str] = {
    # Dashes, quotes, ellipsis
    "â€”": "—",
    "â€“": "—",
    "â€œ": "“",
    "â€�": "”",
    "â€˜": "‘",
    "â€™": "’",
    "â€¦": "…",
    # Accents
    "Ã©": "é",
    "Ã¨": "è",
    "Ã²": "ò",
    "Ã¹": "ù",
    "Ã¬": "ì",
    "Ã ": "à",
    "Ã ": "à",
    # Common words
    "puÃ²": "può",
    "modalitÃ ": "modalità",
    "funzionalitÃ ": "funzionalità",
    # Apostrophes
    "lâ€™": "l’",
    "dâ€™": "d’",
    "câ€™": "c’",
    "Lâ€™": "L’",
    "Dâ€™": "D’",
}


def fix_text(s: str) -> str:
    out = s
    for k, v in REPLACEMENTS.items():
        out = out.replace(k, v)
    return out


def main() -> None:
    changed = []
    for p in TARGETS:
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        new = fix_text(txt)
        if new != txt:
            p.write_text(new, encoding="utf-8")
            changed.append(str(p))
    if changed:
        print("Fixed mojibake in:", ", ".join(changed))
    else:
        print("No changes")


if __name__ == "__main__":
    main()
