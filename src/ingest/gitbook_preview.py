import os
import subprocess
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def launch_gitbook_preview(slug: str):
    load_dotenv()
    docker_image = os.getenv("GITBOOK_IMAGE", "honkit/honkit")

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    output_dir = os.path.join(root_dir, "output", f"timmy_kb_{slug}")

    if not os.path.isdir(output_dir):
        logger.error(f"❌ Directory non trovata: {output_dir}")
        return

    logger.info(f"📁 Directory corrente: {output_dir}")
    logger.info(f"🐳 Avvio anteprima GitBook in locale con Docker...")

    try:
        proc = subprocess.Popen(
            [
                "docker", "run", "--rm", "-p", "4000:4000",
                "-v", f"{output_dir}:/book",
                docker_image, "npx", "honkit", "serve", "/book"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        print("🔄 Premi INVIO per continuare dopo aver chiuso l’anteprima o per forzare l’interruzione...")
        input()
        proc.terminate()
        logger.info("✅ Anteprima Docker terminata.")
    except Exception as e:
        logger.error(f"❌ Errore durante l'avvio dell'anteprima: {e}")
