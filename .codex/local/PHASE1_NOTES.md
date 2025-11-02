# Fase 1 – Fondamenta e copertura

## Moduli presidio regressioni
- `tests/semantic/test_vision_provision.py`: nuovo caso `prepared_prompt` per bloccare letture PDF indesiderate in `provision_from_vision`.
- `tests/pipeline/test_drive_download_pdfs.py`: regressioni su `_walk_drive_tree`/`download_drive_pdfs_to_local` (skip idempotenza, aggregazione errori).

## Convenzioni helper
- Preferire `pipeline.path_utils.read_text_safe` / `safe_write_text` per IO YAML; evitare `Path.read_text/Path.write_text`.
- Logger: usare `get_structured_logger` o stub con stessa interfaccia (`info|warning|debug(event, extra={})`) nei test.
- Drive download: stubbiamo `_walk_drive_tree` + `_download_one_pdf_atomic`; i test creano file tramite `dest_path.write_bytes` per simulare commit atomico.

## QA minimo
- `pytest tests/semantic/test_vision_provision.py::test_provision_with_prepared_prompt_skips_pdf_read`
- `pytest tests/pipeline/test_drive_download_pdfs.py`
