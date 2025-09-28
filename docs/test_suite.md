# Suite di test&#x20;

Questa guida riflette **l’assetto reale** della suite Pytest del repo, raggruppando i file per categoria e indicando marker/flag utili. Vale per l’esecuzione locale e per CI.

---

## Come eseguire

```powershell
# dal venv attivo
make test           # esegue la suite locale
make test-vscode    # variante per VS Code

# oppure direttamente
pytest -ra          # tutto tranne i test marcati con marker esclusi in pytest.ini
pytest -ra -m "push"   # include test che richiedono push su GitHub
pytest -ra -m "drive"  # include test che richiedono Google Drive
pytest -ra -m "slow"   # include smoke/end-to-end lenti
```

**Default:** in CI conviene mantenere l'esclusione di `push` e `drive`.

---

## Categorie & file

> I nomi qui sotto sono rappresentativi dei file realmente presenti in `tests/`. Alcuni casi possono essere *skipped* su Windows (symlink non disponibili).

### 1) Unit — core utility & path safety

- `tests/test_file_io_append.py` — robustezza di `safe_append_text` in concorrenza e su failure controllati.
- `tests/test_embeddings_property.py` — property/fuzz per normalizzazione embeddings e limiti `cosine`.
- `tests/test_path_utils.py` — guardie `ensure_within*` e risoluzione path.
- `tests/test_content_utils_symlink_category.py` — classificazione symlink (può essere **skipped** su Windows).
- `tests/test_pdf_iteration_symlink.py` — iterazione PDF con symlink/unsafe (può essere **skipped** su Windows).

### 2) Semantic API — summary/readme & indicizzazione

- `tests/test_semantic_api_summary_readme.py` — generazione `SUMMARY.md`/`README.md`, gestione errori e logging strutturato.
- `tests/test_semantic_index_markdown_db.py` — indicizzazione Markdown→SQLite: coerenza vettori, esclusione `README/SUMMARY`, gestione generatori/array/vec vuoti, logging fase/avvisi.
- `tests/test_auto_tagger_writer.py` — emissione `tags.csv` (header, prefissi POSIX `raw/`, atomicità).

### 3) Orchestratori & contratti

- `tests/test_smoke_dummy_e2e.py`  **(slow)** — flusso `pre → dummy → tag(local) → semantic(no preview)` con asserzioni minime.
- `tests/test_contract_defaults.py` — contratti di default (es. `source=drive` per tag\_onboarding).
- `tests/test_cli_env_missing.py` — error code e messaggi chiari su env mancanti.

### 4) UI (Streamlit) & integrazioni opzionali

- `tests/test_ui_paths_box.py` — box dei percorsi assoluti dopo provisioning in landing.
- `tests/test_ui_drive_services_guards.py` — guardie UI quando le funzioni Drive non sono installate (`pip install .[drive]`).

### 5) Retriever

- `tests/test_retriever_calibrate_io.py` — coerenza I/O del tool di calibrazione, logging strutturato, nessuna rete.

### 6) Script & qualità repo

- `tests/scripts/test_forbid_control_chars.py` — hook/script di normalizzazione e rimozione caratteri di controllo.

---

## Marker & convenzioni

- `slow` — test lenti/smoke end‑to‑end.
- `push` — richiedono `GITHUB_TOKEN`/rete.
- `drive` — richiedono credenziali/permessi Google Drive (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`).
- **Logging strutturato:** evento + `extra` con `slug`, `file_path`, `scope` dove applicabile.
- **Path safety:** tutte le operazioni file-system passano per `ensure_within_and_resolve` + scritture atomiche (`safe_write_text/bytes`).

---

## Esecuzione mirata

```powershell
# singolo file
pytest tests/test_semantic_index_markdown_db.py -ra
# singolo test
pytest tests/test_semantic_api_summary_readme.py::test_write_summary_and_readme_generators_fail_raise -ra
# filtro per substring
pytest -k "embedding_pruned" -ra
```

---

## Note & manutenzione

- **File legacy:** se presente `tests/est_retriever_calibrate_io.py` (prefisso `est_`), è da considerarsi **obsoleto**: allinearlo allo schema `test_*.py` o rimuoverlo per evitare confusione.
- **Aggiornamento documentazione:** mantenere questa pagina allineata quando si aggiungono/cambiano test (nuovi moduli semantic/UI/retriever).
