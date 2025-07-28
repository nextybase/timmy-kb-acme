import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from pipeline.gitbook_preview import run_gitbook_docker_preview

BOOK_DIR = Path("output/timmy-kb-dummy/book")
CONTAINER_NAME = "honkit_test_preview"

@pytest.fixture(autouse=True)
def cleanup_container():
    import subprocess
    # Rimuove container se presente prima e dopo il test
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, text=True, check=False)
    yield
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, text=True, check=False)

def test_gitbook_preview_dummybook():
    """
    Test diretto della preview: passa parametri giusti,
    lancia build+serve+stop nella cartella dummy.
    """
    # Costruisci un config minimale, proprio come la pipeline
    config = {
        "md_output_path": str(BOOK_DIR)
    }

    # Lancia la funzione reale: fa build e serve
    run_gitbook_docker_preview(config, container_name=CONTAINER_NAME, port=4000)
    # Preview live su http://localhost:4010 finché non premi INVIO

    # Se non lancia errori, il test è passato
    # (Nessun assert richiesto: lancia eccezione solo se la preview fallisce)

