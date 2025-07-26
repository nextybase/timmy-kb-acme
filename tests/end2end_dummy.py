import subprocess
import sys
import os
import shutil
import time
from pathlib import Path

# Permette di importare pipeline.* come se fossi nella src/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# === CONFIGURAZIONE CLIENTE DUMMY ===
SLUG = "dummy"
NOME_CLIENTE = "Dummy Srl"
RAW_SRC = Path("filetest/raw")
OUTPUT_BASE = Path("output") / f"timmy-kb-{SLUG}"
CONFIG_DIR = OUTPUT_BASE / "config"
RAW_DEST = OUTPUT_BASE / "raw"
BOOK_DEST = OUTPUT_BASE / "book"

# === CONFIGURAZIONE REPO / DRIVE ===
from pipeline.settings import get_settings
from pipeline.drive_utils import get_drive_service, upload_folder_to_drive_raw
settings = get_settings()
GITHUB_ORG = getattr(settings, "github_org", "nextybase")
GITHUB_REPO = f"{GITHUB_ORG}/timmy-kb-{SLUG}"

def print_sep():
    print("\n" + "="*60 + "\n")

def run_shell(cmd, input_str=None, step=""):
    print(f"▶️ Eseguo: {' '.join(cmd)}")
    try:
        res = subprocess.run(
            cmd,
            input=input_str,
            text=True,
            capture_output=False
        )
        if res.returncode != 0:
            print(f"❌ Errore bloccante in fase {step if step else '[unknown step]'} (exit code {res.returncode})")
        return res.returncode == 0
    except Exception as e:
        print(f"❌ Errore eseguendo {cmd}: {e}")
        return False

def check_and_delete_github_repo():
    print_sep()
    print(f"🔎 Controllo se esiste la repo su GitHub: {GITHUB_REPO}")
    cmd_check = ["gh", "repo", "view", GITHUB_REPO]
    if subprocess.run(cmd_check, capture_output=True).returncode == 0:
        print("🗑️ Repo trovata, elimino...")
        cmd_del = ["gh", "repo", "delete", GITHUB_REPO, "--yes"]
        res = subprocess.run(cmd_del)
        if res.returncode == 0:
            print("✅ Repo eliminata.")
            return True
        else:
            print("⚠️ Impossibile eliminare la repo (controlla i permessi).")
            return False
    else:
        print("✅ Repo non presente.")
        return True

def check_and_delete_local_output():
    print_sep()
    paths = [
        OUTPUT_BASE,
        RAW_DEST,
        BOOK_DEST,
        CONFIG_DIR,
    ]
    success = True
    for p in paths:
        if p.exists():
            try:
                shutil.rmtree(p)
                print(f"🧹 Cartella eliminata: {p}")
            except Exception as e:
                print(f"⚠️ Errore eliminando {p}: {e}")
                success = False
        else:
            print(f"✅ Cartella non presente (nessuna azione): {p}")
    return success

def check_and_delete_drive_folder():
    print_sep()
    print(f"🔎 Controllo Drive per cartella cliente '{SLUG}'")
    service = get_drive_service()
    from pipeline.drive_utils import find_drive_folder_by_name
    folder = find_drive_folder_by_name(service, SLUG, drive_id=settings.drive_id)
    if folder:
        print(f"🗑️ Cartella trovata su Drive: {folder['name']} (id: {folder['id']}) — elimino ricorsivamente...")
        try:
            service.files().delete(fileId=folder['id'], supportsAllDrives=True).execute()
            print("✅ Cartella cliente eliminata da Drive.")
            return True
        except Exception as e:
            print(f"⚠️ Errore eliminando la cartella su Drive: {e}")
            return False
    else:
        print("✅ Cartella cliente NON presente su Drive.")
        return True

def upload_raw_to_drive():
    print_sep()
    print(f"🚚 Upload automatico di {RAW_SRC} nella cartella raw su Google Drive")
    config_file = CONFIG_DIR / "config.yaml"
    if not config_file.exists():
        print(f"❌ Config file non trovato: {config_file} — impossibile procedere all'upload.")
        return False
    import yaml
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    service = get_drive_service()
    try:
        upload_folder_to_drive_raw(service, RAW_SRC, config["drive_id"], config["drive_folder_id"])
        print("✅ Upload completato su Drive.")
        return True
    except Exception as e:
        print(f"❌ Errore nell'upload automatico su Drive: {e}")
        return False

def countdown(t=30):
    print_sep()
    print(f"⏳ Attendo {t} secondi per sincronizzazione Drive...")
    for i in range(t, 0, -1):
        print(f"\r⏳ Attesa: {i}s", end="")
        time.sleep(1)
    print("\n✅ Fine attesa.")

def check_final_output():
    expected_book_path = BOOK_DEST
    if not expected_book_path.exists():
        print("⚠️ [CHECK] Cartella book/ NON creata dalla pipeline.")
    else:
        print("✅ [CHECK] Cartella book/ trovata.")

    output_dir = OUTPUT_BASE
    print("\n📂 Contenuto della cartella output finale:")
    for p in output_dir.rglob("*"):
        print("   -", p.relative_to(output_dir))

def main():
    print_sep()
    print(f"🧹 [1/5] PULIZIA PRE-TEST")
    all_clean = True
    all_clean &= check_and_delete_github_repo()
    all_clean &= check_and_delete_local_output()
    all_clean &= check_and_delete_drive_folder()

    print_sep()
    if all_clean:
        print("✅ Ambiente di test pulito. Pronto a procedere.")
    else:
        print("⚠️ Alcuni file/cartelle non sono stati eliminati. Pulisci manualmente prima di continuare!")
        input("Premi INVIO per continuare (a tuo rischio!)...")

    print_sep()
    go = input(f"🟩 Confermi avvio pre-onboarding per slug '{SLUG}' e nome '{NOME_CLIENTE}'? [y/N] ").strip().lower()
    if go != "y":
        print("⛔ Test interrotto dall'utente.")
        sys.exit(1)

    print(f"\n🚀 Avvio pre-onboarding per slug '{SLUG}', nome '{NOME_CLIENTE}'")
    preonb_input = f"{SLUG}\n{NOME_CLIENTE}\n"
    ok = run_shell(["py", "src/pre_onboarding.py"], input_str=preonb_input, step="pre-onboarding")
    if not ok:
        print("❌ Pre-onboarding fallito! Test interrotto.")
        sys.exit(1)
    print("✅ Pre-onboarding completato.")

    # --- UPLOAD RAW SU DRIVE ---
    if not upload_raw_to_drive():
        print("❌ Upload automatico fallito! Test interrotto.")
        sys.exit(1)

    countdown(30)

    print_sep()
    go = input(f"🟩 Confermi avvio onboarding per slug '{SLUG}'? [y/N] ").strip().lower()
    if go != "y":
        print("⛔ Test interrotto dall'utente.")
        sys.exit(1)

    print(f"\n🚀 Avvio onboarding completo per slug '{SLUG}'")
    onboarding_input = f"{SLUG}\n"
    ok = run_shell(["py", "src/onboarding_full.py"], input_str=onboarding_input, step="onboarding_full")
    if not ok:
        print("❌ Onboarding fallito! Test interrotto.")
        sys.exit(1)
    print("✅ Onboarding completato.")

    print_sep()
    print("🎉 Test end-to-end completato con SUCCESSO!")
    check_final_output()
    print(f"- Repo GitHub (dovrebbe esistere ora): {GITHUB_REPO}")
    print(f"- Output locale in: {BOOK_DEST}")
    print("Verifica log, anteprima e contenuti generati per confermare l'esito.")

if __name__ == "__main__":
    main()
