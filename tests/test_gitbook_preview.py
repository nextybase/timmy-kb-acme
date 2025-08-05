import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.logging_utils import get_structured_logger

BOOK_DIR = Path("output/timmy-kb-dummy/book")
CONTAINER_NAME = "honkit_test_preview"
logger = get_structured_logger("test_gitbook_preview")

@pytest.fixture(autouse=True)
def cleanup_container():
    import subprocess
    # Cleanup prima del test
    result_before = subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True, text=True, check=False
    )
    if result_before.returncode == 0:
        logger.info(f"🧹 [PRE] Container '{CONTAINER_NAME}' rimosso.")
    else:
        logger.debug(f"[PRE] Nessun container '{CONTAINER_NAME}' da rimuovere.")

    yield

    # Cleanup dopo il test
    result_after = subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True, text=True, check=False
    )
    if result_after.returncode == 0:
        logger.info(f"🧹 [POST] Container '{CONTAINER_NAME}' rimosso.")
    else:
        logger.debug(f"[POST] Nessun container '{CONTAINER_NAME}' da rimuovere.")

def test_gitbook_preview_dummybook():
    """
    Test diretto della preview: passa parametri giusti,
    lancia build+serve+stop nella cartella dummy.
    """
    config = {
        "md_output_path": str(BOOK_DIR)
    }
    # Determina modalità interattiva o batch via variabile d'ambiente
    interactive = os.environ.get("BATCH_TEST", "0") != "1"

    logger.info(
        f"Avvio test preview Docker: interactive={interactive}, container={CONTAINER_NAME}"
    )

    run_gitbook_docker_preview(
        config,
        container_name=CONTAINER_NAME,
        port=4000,
        interactive=interactive
    )
    logger.info("✅ Preview Docker/Honkit testata con successo (nessuna eccezione).")
