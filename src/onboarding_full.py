from pathlib import Path
import subprocess
import os
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import load_client_config
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup import cleanup_output_folder, safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_recursively
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.exceptions import PipelineError
from pipeline.settings import get_settings
from pipeline.utils import is_valid_slug

def check_docker_running():
    try:
        subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return True
    except Exception:
        return False

# Sopprime warning MuPDF in CLI (opzionale)
os.environ["MUPDF_WARNING_SUPPRESS"] = "1"

def main():
    logger = get_structured_logger("onboarding_full", "logs/onboarding.log")
    logger.info("▶️ Avvio pipeline onboarding Timmy-KB")
    print("▶️ Onboarding completo Timmy-KB")

    # --- Centralizzazione config ---
    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Configurazione globale non valida: {e}")
        logger.error(f"❌ Errore configurazione globale: {e}")
        return

    if not check_docker_running():
        print("❌ Docker non risulta attivo o non è raggiungibile.")
        print("🔧 Avvia Docker Desktop o il servizio Docker prima di continuare.")
        logger.error("Docker non attivo: pipeline bloccata.")
        return

    try:
        # --- Input slug ---
        raw_slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug cliente non valido. Ammessi solo lettere minuscole, numeri, trattini (es: acme-srl).")
            logger.error(f"❌ Slug cliente non valido: '{raw_slug}' -> '{slug}'")
            return

        print("📥 Caricamento configurazione...")
        config = load_client_config(slug)
        logger.info(f"✅ Config caricato e arricchito per cliente: {slug}")
        logger.debug(f"Config: {config}")

        print(f"📝 Onboarding per: {config['cliente_nome']}")

        # --- Step 1: Download da Drive e pulizia output ---
        cleanup_output_folder(config)
        service = get_drive_service()
        raw_dir = Path(config["output_path"]) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        download_drive_pdfs_recursively(
            service=service,
            folder_id=config["drive_folder_id"],
            destination=raw_dir,
            drive_id=config["drive_id"]
        )
        logger.info("📥 Download PDF da Drive completato.")

        config["raw_dir"] = str(raw_dir)
        logger.debug(f"PATCH: config['raw_dir'] impostato a {config['raw_dir']}")

        pdf_files = list(Path(config["raw_dir"]).rglob("*.pdf"))
        if not pdf_files:
            logger.warning("⚠️ Nessun PDF trovato nella cartella raw dopo il download. Controllare che il cliente abbia caricato i file su Drive.")
            print("❌ Nessun PDF trovato: pipeline interrotta.")
            return

        # --- Step 2: Conversione PDF → Markdown strutturato ---
        print("📚 Conversione PDF → Markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown(config, mapping)
        logger.info("✅ Conversione PDF → Markdown completata.")

        # --- Step 3: Enrichment semantico ---
        print("🧠 Estrazione semantica (enrichment)...")
        enrich_markdown_folder(config["md_output_path"], slug)
        logger.info("✅ Enrichment semantico completato.")

        # --- Step 4: Generazione README.md e SUMMARY.md ---
        print("📑 Generazione SUMMARY.md e README.md...")
        md_path = config["md_output_path"]
        md_files = [f for f in os.listdir(md_path) if f.endswith(".md")]
        generate_summary_markdown(md_files, md_path)
        generate_readme_markdown(md_path, slug)
        logger.info("✅ SUMMARY.md e README.md generati.")

        # --- Step 5: Preview GitBook ---
        print("🔍 Avvio anteprima GitBook in locale con Docker...")
        run_gitbook_docker_preview(config)
        logger.info("✅ Anteprima GitBook completata.")

        # --- Step 6: Push GitHub SOLO della knowledge base pulita (cartella book) ---
        risposta = input("❓ Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
        logger.debug(f"Risposta push GitHub: {risposta}")
        temp_dir = None
        if risposta == "y":
            print("🚀 Esecuzione push su GitHub SOLO per la knowledge base (cartella book)...")
            book_config = dict(config)
            book_config["output_path"] = str(Path(config["md_output_path"]).resolve())
            # PATCH: aggiungi github_repo dinamicamente dal settings centrale
            github_org = getattr(settings, "github_org", "nextybase")
            book_config["github_repo"] = f"{github_org}/timmy-kb-{slug}"
            logger.info(f"🔗 Repo di destinazione GitHub: {book_config['github_repo']}")
            temp_dir = push_output_to_github(book_config)
            logger.info(f"✅ Push su GitHub completato SOLO per la cartella book. Temp dir: {temp_dir}")
            print(f"✅ Push su GitHub completato SOLO per la cartella book. I file temporanei rimangono in: {temp_dir}")
        else:
            logger.info("⏹️ Push su GitHub annullato dall’utente.")
            print("⏹️ Push annullato. Operazione completata.")

        # --- Step 7: UX finale, cleanup guidato ---
        if temp_dir:
            while True:
                finale = input(f"\n✅ Possiamo definire completo l'onboarding del cliente {config['cliente_nome']}? [y/N] ").strip().lower()
                if finale == "y":
                    safe_clean_dir(temp_dir)
                    print("🧹 Pulizia completata. Onboarding chiuso.")
                    logger.info("🧹 Temp dir rimossa, onboarding completato.")
                    break
                elif finale == "n":
                    reset = input("🔄 Vuoi azzerare la procedura? [y/N] ").strip().lower()
                    if reset == "y":
                        also_conf = input("🗑️ Vuoi cancellare anche i file di configurazione? Dovrai ripartire dal pre-onboarding. [y/N] ").strip().lower()
                        if also_conf == "y":
                            config_dir = Path(config["output_path"]) / "config"
                            safe_clean_dir(config_dir)
                            print("🗑️ Tutto azzerato, inclusa la configurazione.")
                            logger.warning("🗑️ Tutto azzerato, inclusa la configurazione.")
                        safe_clean_dir(temp_dir)
                        print("🧹 Pulizia completata. Onboarding azzerato.")
                        logger.info("🧹 Temp dir rimossa, onboarding azzerato.")
                        break
                    elif reset == "n":
                        print(f"❗ Attenzione: la temp dir ({temp_dir}) e la config rimangono. Puoi rilanciare o ispezionare i file.")
                        logger.warning("❗ Temp dir e config non rimosse: attesa nuova azione utente.")
                        break
                else:
                    print("Risposta non valida. Inserisci 'y' o 'n'.")
        else:
            print(f"🏁 Onboarding pipeline completata per cliente: {slug}")
            logger.info(f"🏁 Onboarding pipeline completata per cliente: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore bloccante nella pipeline: {e}")
        print(f"❌ Errore bloccante: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore non gestito: {e}", exc_info=True)
        print(f"❌ Errore imprevisto: {e}")
        return

if __name__ == "__main__":
    main()
