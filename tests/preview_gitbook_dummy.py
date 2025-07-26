import sys
import os
import shutil
from pathlib import Path
import subprocess

# Import pipeline (src/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from pipeline.gitbook_preview import run_gitbook_docker_preview

def kb_ready(book_dir):
    if not book_dir.exists(): return False
    md_files = [f for f in book_dir.glob("*.md")]
    return len(md_files) > 0 and (book_dir / "README.md").exists() and (book_dir / "SUMMARY.md").exists()

def copy_template_dir(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"✅ Copiata struttura dummy da '{src}' a '{dst}'.")

def docker_build_and_serve(config):
    output_dir = Path(config["md_output_path"]).resolve()
    build_output_dir = output_dir.parent / "gitbook"
    build_output_dir.mkdir(exist_ok=True)

    print(f"📁 Directory Markdown per anteprima: {output_dir}")
    print(f"🗂️ Directory OUTPUT HTML Honkit: {build_output_dir}")

    # Step 1: Build statico Honkit → gitbook/
    build_cmd = [
        "docker", "run", "--rm",
        "--workdir", "/app",
        "-v", f"{output_dir}:/app",
        "-v", f"{build_output_dir}:/app/_book",
        "honkit/honkit", "npx", "honkit", "build", ".", "_book"
    ]
    print("\n[DOCKER BUILD COMMAND]:", " ".join(build_cmd))
    try:
        result = subprocess.run(build_cmd, capture_output=True, text=True)
        print("\n[BUILD STDOUT]:\n", result.stdout)
        print("\n[BUILD STDERR]:\n", result.stderr)
        result.check_returncode()
    except subprocess.CalledProcessError as e:
        print("\n❌ ERRORE DURANTE BUILD HONKIT:")
        print("[BUILD STDOUT]:\n", e.stdout)
        print("[BUILD STDERR]:\n", e.stderr)
        raise

    # Step 2: Serve in modalità detached direttamente dalla build HTML
    container_name = "honkit_preview"
    serve_cmd = [
        "docker", "run", "-d", "--rm",
        "--name", container_name,
        "-p", "4000:4000",
        "--workdir", "/app",
        "-v", f"{build_output_dir}:/app/_book",
        "npx", "honkit", "serve", "_book"
    ]
    print("\n[DOCKER SERVE COMMAND]:", " ".join(serve_cmd))
    try:
        # Avvia container in background
        serve_result = subprocess.run(serve_cmd, capture_output=True, text=True)
        container_id = serve_result.stdout.strip()
        print("\n[SERVE STDOUT]:\n", serve_result.stdout)
        print("\n[SERVE STDERR]:\n", serve_result.stderr)

        if not container_id:
            print("❌ Il container non è partito correttamente.")
            return

        print("✅ Anteprima avviata su http://localhost:4000 (container id: {})".format(container_id))
        print("🔁 Premi INVIO per vedere i log del container e chiudere l’anteprima...")
        input()

        # Mostra i log live del container
        print("\n[DOCKER LOGS]:\n")
        subprocess.run(["docker", "logs", container_id])

        print("🛑 Arresto container Docker...")
        subprocess.run(["docker", "stop", container_id])
    except subprocess.CalledProcessError as e:
        print("\n❌ ERRORE DURANTE SERVE HONKIT:")
        print("[SERVE STDOUT]:\n", e.stdout)
        print("[SERVE STDERR]:\n", e.stderr)
        raise

def main():
    SLUG = "dummy"
    TEST_TEMPLATE = Path("filetest/timmy-kb-dummy")
    OUTPUT_BASE = Path(f"output/timmy-kb-{SLUG}")

    # --- Step 1: Prepara la cartella output/timmy-kb-dummy ---
    if not OUTPUT_BASE.exists():
        print(f"ℹ️ La cartella '{OUTPUT_BASE}' non esiste. Creo da template '{TEST_TEMPLATE}'.")
        copy_template_dir(TEST_TEMPLATE, OUTPUT_BASE)
    else:
        choice = input(f"\nLa cartella '{OUTPUT_BASE}' esiste già. Usare la versione corrente? [y/N]: ").strip().lower()
        if choice == "y":
            print("✅ Uso la versione attuale.")
        else:
            print("🧹 Cancello e ricreo la cartella dummy da template.")
            copy_template_dir(TEST_TEMPLATE, OUTPUT_BASE)

    BOOK_DIR = OUTPUT_BASE / "book"

    if not kb_ready(BOOK_DIR):
        print(f"❌ Cartella {BOOK_DIR} mancante o incompleta (devi prima popolare il template con README.md, SUMMARY.md, almeno un .md).")
        return

    config = {
        "slug": SLUG,
        "md_output_path": str(BOOK_DIR),
        "output_path": str(OUTPUT_BASE),
    }

    print(f"\n🔍 Test preview Docker Honkit su: {BOOK_DIR}")
    try:
        docker_build_and_serve(config)
    except Exception as e:
        print(f"\n❌ Errore durante la preview Docker: {e}")

    # Cleanup finale
    choice = input(f"\nVuoi eliminare la cartella '{OUTPUT_BASE}' dopo il test? [y/N]: ").strip().lower()
    if choice == "y":
        try:
            shutil.rmtree(OUTPUT_BASE)
            print(f"🧹 Cartella '{OUTPUT_BASE}' eliminata.")
        except Exception as ex:
            print(f"⚠️ Errore durante la rimozione di '{OUTPUT_BASE}': {ex}")
    else:
        print(f"❗ Output NON eliminato: rimane '{OUTPUT_BASE}'.")

if __name__ == "__main__":
    main()
