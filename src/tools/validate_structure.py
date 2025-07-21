import yaml
from pathlib import Path

REQUIRED_KEYS = {"descrizione", "tipo_contenuto", "entita_rilevanti"}

def validate_structure_yaml(path: Path) -> bool:
    if not path.exists():
        print(f"❌ File non trovato: {path}")
        return False

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"❌ Errore di parsing YAML: {e}")
        return False

    if not isinstance(data, dict):
        print("❌ Il file deve contenere un dizionario di sezioni.")
        return False

    ok = True
    for section, content in data.items():
        if not isinstance(content, dict):
            print(f"❌ Sezione '{section}' non è un dizionario.")
            ok = False
            continue

        missing = REQUIRED_KEYS - content.keys()
        if missing:
            print(f"❌ Sezione '{section}' mancano chiavi: {', '.join(missing)}")
            ok = False

        if "tipo_contenuto" in content and not isinstance(content["tipo_contenuto"], list):
            print(f"⚠️  'tipo_contenuto' in '{section}' deve essere una lista.")
            ok = False

        if "entita_rilevanti" in content and not isinstance(content["entita_rilevanti"], list):
            print(f"⚠️  'entita_rilevanti' in '{section}' deve essere una lista.")
            ok = False

    if ok:
        print("✅ raw_structure.yaml valido.")
    return ok

if __name__ == "__main__":
    validate_structure_yaml(Path("config/raw_structure.yaml"))
