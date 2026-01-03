# SPDX-License-Identifier: GPL-3.0-only
# tools/e2e_smoke_test.py
import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(cmd, check=True):
    print(">>", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=False)
    if check and p.returncode != 0:
        raise SystemExit(p.returncode)


def derive_paths(slug: str, raw_dir: str | None, db_path: str | None):
    base = ROOT / "output" / f"timmy-kb-{slug}"
    raw = Path(raw_dir) if raw_dir else (base / "raw")
    db = Path(db_path) if db_path else (base / "semantic" / "tags.db")
    return raw, db


def check_optional_deps(lang: str):
    import importlib

    missing = []

    def _check(mod: str, label: str | None = None):
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(label or mod)

    _check("spacy")
    _check("yake")
    _check("sentence_transformers", label="sentence-transformers")
    _check("sklearn", label="scikit-learn")
    _check("pypdf")
    if missing:
        print("\n[WARN] Dipendenze opzionali mancanti:", ", ".join(missing))
        print("Installale con:\n  pip install -r requirements-optional.txt")
    # modelli spaCy
    if lang.startswith("it"):
        model = "it_core_news_md"
    else:
        model = "en_core_web_md"
    try:
        importlib.import_module(model)
    except Exception:
        print(f"\n[WARN] Modello spaCy assente: {model}")
        print(f"Installa con:\n  python -m spacy download {model}")


def sqlite_summary(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    def one(q):
        return cur.execute(q).fetchone()[0]

    data = {
        "folders": one("SELECT COUNT(*) FROM folders"),
        "documents": one("SELECT COUNT(*) FROM documents"),
        "doc_terms": one("SELECT COUNT(*) FROM doc_terms"),
        "terms": one("SELECT COUNT(*) FROM terms"),
        "aliases": one("SELECT COUNT(*) FROM term_aliases"),
        "folder_terms": one("SELECT COUNT(*) FROM folder_terms"),
    }
    print("\n[DB] Counts:", data)
    print("\n[DB] Sample folders:")
    for r in cur.execute("SELECT path FROM folders ORDER BY path LIMIT 10"):
        print(" -", r["path"])
    print("\n[DB] Top doc_terms:")
    for r in cur.execute(
        """
        SELECT d.filename AS file, dt.phrase, printf('%.3f',dt.score) AS score
        FROM doc_terms dt JOIN documents d ON d.id=dt.document_id
        ORDER BY dt.score DESC LIMIT 10
    """
    ):
        print(f" {r['file']:40s} | {r['phrase'][:40]:40s} | {r['score']}")
    print("\n[DB] Top aliases per term:")
    for r in cur.execute(
        """
        SELECT t.canonical, COUNT(a.alias) AS alias_count
        FROM terms t LEFT JOIN term_aliases a ON a.term_id=t.id
        GROUP BY t.id ORDER BY alias_count DESC, t.canonical LIMIT 10
    """
    ):
        print(f" {r['canonical']:40s} | aliases={r['alias_count']}")
    print("\n[DB] Top folder_terms:")
    for r in cur.execute(
        """
        SELECT f.path, t.canonical, printf('%.3f',ft.weight) AS weight, ft.status
        FROM folder_terms ft
        JOIN terms t ON t.id=ft.term_id
        JOIN folders f ON f.id=ft.folder_id
        ORDER BY f.path, ft.weight DESC LIMIT 20
    """
    ):
        print(f" {r['path']:30s} | {r['canonical'][:28]:28s} | {r['weight']} | {r['status']}")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True, help="es. acme")
    ap.add_argument("--raw-dir", help="override path RAW")
    ap.add_argument("--db", help="override path DB")
    ap.add_argument("--lang", default="it")
    ap.add_argument("--topn-doc", type=int, default=10)
    ap.add_argument("--topk-folder", type=int, default=15)
    ap.add_argument("--cluster-thr", type=float, default=0.82)
    ap.add_argument("--model", default="all-MiniLM-L6-v2")
    ap.add_argument("--only-missing", action="store_true", default=True)
    ap.add_argument(
        "--auto-dummy",
        action="store_true",
        help="Se RAW è vuota genera sandbox dummy prima dello scan",
    )
    args = ap.parse_args()

    raw_dir, db_path = derive_paths(args.slug, args.raw_dir, args.db)
    print(f"[INFO] RAW={raw_dir} | DB={db_path}")

    # 0) opzionale: genera sandbox dummy se richiesto e RAW vuota
    if args.auto_dummy:
        need_gen = (not raw_dir.exists()) or (not any(raw_dir.rglob("*.pdf")))
        if need_gen:
            print("[INFO] RAW vuota: genero sandbox dummy…")
            run([sys.executable, "-m", "tools.gen_dummy_kb", "--slug", args.slug], check=True)

    # 1) preflight
    check_optional_deps(args.lang)

    # 1) scan RAW → DB
    run(
        [
            sys.executable,
            "-m",
            "timmy_kb.cli.tag_onboarding",
            "--slug",
            args.slug,
            "--scan-raw",
            "--raw-dir",
            str(raw_dir),
            "--db",
            str(db_path),
        ],
        check=True,
    )

    # 2) NLP → DB
    run(
        [
            sys.executable,
            "-m",
            "timmy_kb.cli.tag_onboarding",
            "--slug",
            args.slug,
            "--nlp",
            "--lang",
            args.lang,
            "--topn-doc",
            str(args.topn_doc),
            "--topk-folder",
            str(args.topk_folder),
            "--cluster-thr",
            str(args.cluster_thr),
            "--model",
            args.model,
            "--only-missing",
            "--raw-dir",
            str(raw_dir),
            "--db",
            str(db_path),
        ],
        check=True,
    )

    # 3) DB check
    sqlite_summary(str(db_path))
    print("\n[OK] E2E smoke test completato.")


if __name__ == "__main__":
    main()
