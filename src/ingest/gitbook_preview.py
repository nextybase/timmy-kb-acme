import subprocess
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Carica variabili da .env
load_dotenv()
docker_image = os.getenv("GITBOOK_IMAGE", "gitbook/docker-gitbook")

def preview_with_docker(output_path: str):
    print("\n🚀 Avvio anteprima GitBook in locale con Docker...")
    print("🌐 Anteprima disponibile su http://localhost:4000")
    print("⏸ Premi INVIO per interrompere la preview e continuare...")

    abs_path = str(Path(output_path).resolve())
    container_name = "gitbook_preview_temp"

    try:
        # Stop forzato se il container è già attivo
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Avvio container GitBook in background
        subprocess.run([
            "docker", "run", "-d", "--rm",
            "--name", container_name,
            "-v", f"{abs_path}:/gitbook",
            "-p", "4000:4000",
            docker_image,
            "serve"
        ], check=True)

        input()  # Attende INVIO da parte dell'utente

        subprocess.run(["docker", "stop", container_name], check=True)
        print("🛑 Preview Docker terminata.")

    except subprocess.CalledProcessError as e:
        print("❌ Errore durante l'avvio della preview GitBook con Docker.")
        print(e)

def cleanup_output(output_path: str):
    if os.path.isdir(output_path):
        shutil.rmtree(output_path)
        print(f"🧹 Cartella '{output_path}' eliminata.")
    else:
        print("ℹ️ Nessun file da eliminare.")
