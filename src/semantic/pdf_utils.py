# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - dipendenza opzionale in alcuni ambienti
    PdfReader = None


class PdfExtractError(Exception):
    """Errore generico di estrazione testo da PDF."""


def extract_text_from_pdf(path: Path) -> list[str]:
    """
    Estrae il testo da ogni pagina del PDF usando SOLO pypdf.
    Solleva PdfExtractError per file mancanti, corrotti o non leggibili.
    Ritorna una lista di stringhe, una per pagina.
    """
    if PdfReader is None:
        raise PdfExtractError("Dipendenza 'pypdf' non disponibile: installare il pacchetto per l'estrazione PDF.")

    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise PdfExtractError(f"PDF non trovato: {pdf_path}")
    try:
        if pdf_path.stat().st_size <= 0:
            raise PdfExtractError(f"PDF vuoto: {pdf_path}")
    except OSError as exc:
        raise PdfExtractError(f"Impossibile leggere il PDF: {pdf_path}") from exc

    try:
        reader = PdfReader(str(pdf_path))
        pages_text: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)
    except Exception as exc:
        raise PdfExtractError(f"Estrazione fallita da {pdf_path}") from exc

    if not pages_text:
        raise PdfExtractError(f"Nessun contenuto testuale estraibile: {pdf_path}")

    return pages_text
