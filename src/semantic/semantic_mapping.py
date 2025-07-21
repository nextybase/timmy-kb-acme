import yaml
from pathlib import Path

# Path al file di mapping semantico (relativo alla root progetto)
SEMANTIC_YAML_PATH = Path("config/cartelle_semantica.yaml")

def load_semantic_mapping():
    """
    Carica il file YAML della struttura semantica delle cartelle.
    """
    with open(SEMANTIC_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_semantic_info_for_folder(folder_name):
    """
    Dato il nome di una cartella (es: 'glossario'), restituisce il mapping semantico.
    """
    mapping = load_semantic_mapping()
    return mapping.get(folder_name, {
        "ambito": "unknown",
        "descrizione": "Cartella non mappata",
        "esempio": [],
    })

def get_semantic_info_for_file(filepath):
    """
    Dato un path file (Markdown), cerca la prima cartella tematica nell'albero
    e restituisce il mapping semantico relativo.
    """
    p = Path(filepath)
    for part in p.parts:
        # Salta le directory di root/output, cerca solo la cartella tematica
        info = get_semantic_info_for_folder(part)
        if info["ambito"] != "unknown":
            return info
    # Nessuna cartella tematica trovata
    return {
        "ambito": "unknown",
        "descrizione": "File fuori struttura semantica",
        "esempio": [],
    }

# Esempio d'uso (rimuovi in produzione o sposta in test!)
if __name__ == "__main__":
    print("== Test cartella ==")
    print(get_semantic_info_for_folder("glossario"))

    print("\n== Test file path ==")
    print(get_semantic_info_for_file("output/timmy-kb-prova/glossario/Glossario.md"))
    print(get_semantic_info_for_file("output/timmy-kb-prova/unknown-dir/test.md"))
