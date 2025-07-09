import sys
import os

# Permette l'import cross-directory dal template
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'ingest')))
from config_loader import load_config

# Carica la config per questa istanza
cfg = load_config()

# Percorsi degli script pipeline (conversione + summary)
PDF_TO_MD = os.path.join(os.path.dirname(__file__), 'ingest', 'pdf_to_md.py')
BUILD_SUMMARY = os.path.join(os.path.dirname(__file__), 'ingest', 'build_summary.py')

def run_pipeline():
    # Conversione PDF → MD
    print("🚀 Lancio conversione PDF → MD...")
    os.system(f'python "{PDF_TO_MD}"')
    # Generazione sommario/README
    print("🚀 Genero README/SUMMARY...")
    os.system(f'python "{BUILD_SUMMARY}"')
    print("✅ Onboarding pipeline completata!")

if __name__ == "__main__":
    run_pipeline()
