# salva come: scripts/check_structure.py  (esegui dalla root del repo)
import sys, os, argparse, unicodedata, yaml
from pathlib import Path


def kebabify(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return "".join(ch for ch in s if ch.isalnum() or ch in "-")


def load_yaml(p: Path):
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def categories_from_cartelle(d: dict) -> set:
    # formati attesi: {"raw": {"contratti": {}, "privacy": {}}, "contrattualistica": {}}
    raw = d.get("raw") or d.get("RAW") or {}
    if isinstance(raw, dict):
        return {kebabify(k) for k in raw.keys()}
    # fallback legacy: lista di stringhe
    if isinstance(raw, list):
        return {kebabify(x) for x in raw}
    return set()


def categories_from_mapping(d: dict) -> set:
    # mapping UI → categorie: prendiamo i "nomi concetto" top-level come base
    # e li normalizziamo in kebab-case. Ignoriamo chiavi note non strutturali.
    ignore = {"meta", "tags", "keywords", "examples", "title", "description"}
    cats = set()
    for k, v in (d or {}).items():
        if k in ignore:
            continue
        # se il mapping ha un nodo "concetti: {...}" usiamo i figli
        if k.lower() in ("concetti", "concepts") and isinstance(v, dict):
            cats |= {kebabify(x) for x in v.keys()}
        elif isinstance(v, dict):
            cats.add(kebabify(k))
    return cats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    args = ap.parse_args()
    root = Path.cwd()

    # percorsi standard
    base = root / "output" / f"timmy-kb-{args.slug}"
    sem_dir = base / "semantic"
    cfg_dir = root / "config"

    cartelle_paths = [
        sem_dir / "cartelle_raw.yaml",
        cfg_dir / "cartelle_raw.yaml",
    ]
    mapping_paths = [
        sem_dir / "semantic_mapping.yaml",
        sem_dir / "tags_reviewed.yaml",  # se la UI ha già consolidato i tag
    ]

    # carica yaml
    cartelle = {}
    for p in cartelle_paths:
        cartelle = load_yaml(p)
        if cartelle:
            cartelle_path = p
            break
    else:
        cartelle_path = None

    mapping = {}
    mapping_path = None
    for p in mapping_paths:
        mapping = load_yaml(p)
        if mapping:
            mapping_path = p
            break

    # categorie attese
    cats_from_cartelle = categories_from_cartelle(cartelle)
    cats_from_mapping = categories_from_mapping(mapping) if mapping else set()

    # cosa c'è davvero in locale
    local_raw = base / "raw"
    local_dirs = {p.name for p in local_raw.iterdir() if p.is_dir()} if local_raw.exists() else set()

    print("=== INPUT ===")
    print("cartelle_raw.yaml:", cartelle_path if cartelle_path else "NON TROVATO")
    print("semantic_mapping/tags_reviewed:", mapping_path if mapping_path else "NON TROVATO")
    print("\n=== CATEGORIE ATTESE ===")
    print("Da cartelle_raw.yaml:", sorted(cats_from_cartelle))
    if mapping_path:
        print("Derivate dal mapping UI :", sorted(cats_from_mapping))

    # set di riferimento: priorità a cartelle_raw.yaml; se vuoto, usa mapping
    expected = cats_from_cartelle or cats_from_mapping

    print("\n=== CONFRONTO CON LOCALE ===")
    print("Presenti in locale (raw/):", sorted(local_dirs))
    missing = expected - local_dirs
    extra = local_dirs - expected
    if not expected:
        print("ATTENZIONE: nessuna categoria attesa rilevata. Controlla i YAML.")
        sys.exit(2)

    if missing:
        print("MANCANO in raw/ →", sorted(missing))
    else:
        print("OK: nessuna cartella mancante in raw/.")

    if extra:
        print("EXTRA non previste dai YAML →", sorted(extra))
    else:
        print("OK: nessuna cartella extra rispetto ai YAML.")

    # diff tra cartelle_raw e mapping (se entrambi presenti)
    if cats_from_cartelle and cats_from_mapping:
        only_cartelle = cats_from_cartelle - cats_from_mapping
        only_mapping = cats_from_mapping - cats_from_cartelle
        print("\n=== DIFF cartelle_raw vs mapping ===")
        if only_cartelle:
            print("Solo in cartelle_raw:", sorted(only_cartelle))
        if only_mapping:
            print("Solo in mapping     :", sorted(only_mapping))
        if not (only_cartelle or only_mapping):
            print("Allineati.")

    # exit code utile per CI
    if missing or (cats_from_cartelle and cats_from_mapping and (only_cartelle or only_mapping)):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
