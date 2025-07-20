import os
import logging

logger = logging.getLogger(__name__)

def generate_summary_md(markdown_files, output_path):
    summary_md_path = os.path.join(output_path, "SUMMARY.md")
    try:
        with open(summary_md_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Sommario\n\n")
            f.write("* [Introduzione](README.md)\n")
            for file in sorted(markdown_files):
                if file.lower() in {"readme.md", "summary.md"}:
                    continue
                title = os.path.splitext(os.path.basename(file))[0].replace("_", " ")
                f.write(f"* [{title}]({file})\n")

        logger.info(f"📄 SUMMARY.md generato con {len(markdown_files)} file.")
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di SUMMARY.md: {e}")

def generate_readme_md(output_path, slug):
    readme_path = os.path.join(output_path, "README.md")
    try:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Timmy KB – {slug}\n\n")
            f.write("Benvenuto nella Knowledge Base del cliente **{0}**.\n\n".format(slug))
            f.write("Questa documentazione è generata automaticamente a partire dai PDF forniti durante l’onboarding.\n")

        logger.info("✅ README.md generato con contenuto minimale.")
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di README.md: {e}")
