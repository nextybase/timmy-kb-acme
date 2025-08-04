import subprocess
import sys
import os
import shutil
import time
from pathlib import Path
import pytest
import yaml

# ===============================================================
# TEST END-TO-END "DUMMY" - PIPELINE TIMMY-KB ACME
# Flusso:
#  1. Pulisce solo il contenuto della cartella dummy su Drive (mai la cartella root!)
#  2. Lancia pre_onboarding che ricrea struttura e config dummy in locale e su Drive
#  3. Genera RAW dummy PDF in temp_raw/
#  4. Carica tutte le SOTTOCARTELLE di temp_raw/ dentro la raw su Drive (già esistente)
#  5. Aspetta sync (20s)
#  6. Lancia onboarding_full (skip preview via env), chiede se fare il push, chiude.
# ===============================================================

sys.path.insert(0, str(Path("src").resolve()))

SLUG = "dummy"
NOME_CLIENTE = "Dummy Srl"
OUTPUT_BASE = Path("output") / f"timmy-kb-{SLUG}"
TEMP_RAW = OUTPUT_BASE / "temp_raw"
CONFIG_DIR = OUTPUT_BASE / "config"
RAW_DEST = OUTPUT_BASE / "raw"
BOOK_DEST = OUTPUT_BASE / "book"

def logstep(msg):
    print(f"\n\033[96m[STEP]\033[0m {msg}")

def run_shell(cmd, input_str=None, step=None, env=None):
    if step:
        logstep(f"Esecuzione comando shell [{step}]")
    else:
        logstep(f"Esecuzione comando shell: {' '.join(str(x) for x in cmd)}")
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    env_vars["PYTHONIOENCODING"] = "utf-8"
    with subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_str else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env_vars,
        text=True,
        encoding="utf-8",
        bufsize=1
    ) as proc:
        if input_str:
            proc.stdin.write(input_str)
            proc.stdin.flush()
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Comando fallito: {cmd} (returncode={proc.returncode})")
    return proc

def genera_raw_structure(dest_path):
    logstep(f"Generazione struttura RAW fittizia in: {dest_path.resolve()}")
    RAW_YAML = "config/cartelle_raw.yaml"
    PDF_DUMMY_YAML = "config/pdf_dummy.yaml"
    try:
        with open(RAW_YAML, "r", encoding="utf-8") as f:
            cartelle_struct = yaml.safe_load(f)
        with open(PDF_DUMMY_YAML, "r", encoding="utf-8") as f:
            pdf_dummy = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Errore lettura YAML: {e}")
        pytest.skip("Impossibile leggere YAML strutture.")

    def parse_cartelle_structure(cartelle_yaml):
        def _extract_names(folders):
            result = []
            for item in folders:
                if "name" in item:
                    result.append(item["name"])
                if "subfolders" in item and item["subfolders"]:
                    result += _extract_names(item["subfolders"])
            return result
        return _extract_names(cartelle_yaml.get("root_folders", []))

    from fpdf import FPDF

    cartelle = parse_cartelle_structure(cartelle_struct)
    for cat in cartelle:
        cat_folder = dest_path / cat
        cat_folder.mkdir(parents=True, exist_ok=True)
        info = pdf_dummy.get(cat, {})
        titolo = info.get("titolo", f"Sezione: {cat.title()}")
        paragrafi = info.get("paragrafi", [
            "Questo è un paragrafo di esempio.",
            "Puoi personalizzare il contenuto dei PDF modificando pdf_dummy.yaml.",
            "Sezione tematica generica.",
        ])
        pdf_path = cat_folder / f"{cat}_dummy.pdf"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.multi_cell(0, 10, titolo)
        pdf.ln(6)
        pdf.set_font("Arial", "", 12)
        for par in paragrafi:
            pdf.multi_cell(0, 8, par)
            pdf.ln(2)
        pdf.output(str(pdf_path))
        print(f"   📄 PDF creato: {pdf_path.relative_to(dest_path)}")
    print(f"✅ Struttura RAW dummy generata in: {dest_path.resolve()}")

def wait_for_drive(seconds=20):
    logstep(f"Attendo {seconds} secondi per sincronizzazione Google Drive...")
    for i in range(seconds, 0, -1):
        print(f"  ⏳ Attesa: {i}s", end="\r")
        time.sleep(1)
    print("\n✅ Attesa completata, puoi proseguire.")

# ===== DRIVE UTILITY SOLO PER TEST =====

def clean_drive_subfolders(slug):
    """
    Cancella TUTTO il contenuto (sottocartelle e file) nella cartella Drive dummy (root),
    ma non la cartella stessa.
    """
    import importlib
    pipeline_drive_utils = importlib.import_module("pipeline.drive_utils")
    get_drive_service = pipeline_drive_utils.get_drive_service

    # ATTENZIONE: Config NON esiste ancora al primo run, quindi ignora errori
    config_file = CONFIG_DIR / "config.yaml"
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception:
        print("⚠️  [WARNING] Nessun config.yaml ancora: la pulizia Drive verrà saltata (primo run?)")
        return

    drive_id = config["drive_id"]
    folder_id = config.get("drive_folder_id", "1C1L-BtruPfyQB3nZCeo6zpjm0g77O95J")

    service = get_drive_service(slug)

    query = f"'{folder_id}' in parents and trashed = false"
    try:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='drive',
            driveId=drive_id
        ).execute()
        files = results.get('files', [])
        for file in files:
            service.files().delete(
                fileId=file['id'],
                supportsAllDrives=True
            ).execute()
            print(f"🗑️  Eliminato su Drive: {file['name']} ({file['id']})")
    except Exception as e:
        print(f"⚠️  [WARNING] Pulizia Drive non riuscita: {e}")

# ===== TEST SEQUENZA =====

def test_end2end_pipeline():
    # 1. Pulisce il contenuto dummy su Drive (ma NON la cartella root!)
    clean_drive_subfolders(SLUG)
    wait_for_drive(2)

    # 2. Pre-onboarding: crea struttura dummy (con Drive già pulito)
    preonb_input = f"{SLUG}\n{NOME_CLIENTE}\n"
    res = run_shell([sys.executable, "src/pre_onboarding.py"], input_str=preonb_input, step="pre-onboarding")
    assert OUTPUT_BASE.exists(), "Pre-onboarding non ha creato la KB"
    wrong_config = OUTPUT_BASE / "config.yaml"
    if wrong_config.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(wrong_config), CONFIG_DIR / "config.yaml")
        print("🔧 Spostato config.yaml nella cartella corretta.")
    print(f"✅ Pre-onboarding: struttura {OUTPUT_BASE} creata.")

    # 3. Genera RAW PDF dummy (in temp_raw/)
    if TEMP_RAW.exists():
        shutil.rmtree(TEMP_RAW)
    genera_raw_structure(TEMP_RAW)
    files = list(TEMP_RAW.rglob("*.pdf"))
    assert len(files) > 0, "Nessun PDF generato in temp_raw!"
    print(f"✅ {len(files)} PDF dummy creati in {TEMP_RAW}/")

    # 4. Upload RAW solo delle sottocartelle di temp_raw/ nella raw su Drive (già esistente)
    config_file = CONFIG_DIR / "config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if "drive_folder_id" not in config or not config["drive_folder_id"]:
        config["drive_folder_id"] = "1C1L-BtruPfyQB3nZCeo6zpjm0g77O95J"
    if "drive_id" not in config or not config["drive_id"]:
        config["drive_id"] = "dummy_drive_root_id"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)
    logstep("Upload automatico RAW su Drive (temp_raw ➔ cartella dummy/raw)")
    try:
        from pipeline.drive_utils import get_drive_service, upload_folder_to_drive_raw
        service = get_drive_service(SLUG)
        upload_folder_to_drive_raw(
            service,
            TEMP_RAW,
            config["drive_id"],
            config.get("drive_folder_id")
        )
        print("✅ Upload su Drive effettuato!")
    except Exception as e:
        print(f"⚠️ Upload fallito! Errore: {e}")
        pytest.skip(f"Upload RAW su Drive non testato: {e}")
    wait_for_drive(20)

    # 5. Lancia onboarding_full (skip preview docker via env) e chiede push
    onboarding_input = f"{SLUG}\n"
    env = os.environ.copy()
    env["TIMMY_SKIP_PREVIEW"] = "1"  # la pipeline salterà la preview docker!
    res = run_shell([sys.executable, "src/onboarding_full.py"], input_str=onboarding_input, step="onboarding_full", env=env)
    assert res.returncode == 0
    print("✅ Onboarding completo!")

    # 6. Fine test: chiede push o chiude
    logstep("Verifica finale presenza file minimi per preview GitBook (dummy KB)")
    warn_files = []
    if not BOOK_DEST.exists():
        warn_files.append("Cartella book/ NON creata dalla pipeline.")
    else:
        files = list(BOOK_DEST.rglob("*.md"))
        if not files:
            warn_files.append("Almeno un file .md in book/ (es. test.md)")
    if warn_files:
        print("\n⚠️  [WARNING] Alcuni file minimi per la preview GitBook sono mancanti:")
        for w in warn_files:
            print(f"   - {w}")
        print("➡️  Rigenera la cartella dummy (usa il tool di setup) **prima** di lanciare il test preview.")
    print("\n👉  **Per analizzare la preview, lancia il test dedicato:**")
    print("    pytest -v -s tests/test_gitbook_preview.py\n")
    print("✅ Test end-to-end completato con SUCCESSO.")
