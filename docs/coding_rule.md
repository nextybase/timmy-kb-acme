# Timmy-KB - Coding Rules (v1.9.2)

Linee guida per contribuire al codice in modo coerente, sicuro e manutenibile.

> Doppio approccio: puoi lavorare da terminale (orchestratori in sequenza) oppure tramite interfaccia (Streamlit).
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Principi
- SSoT (Single Source of Truth): riusa utility già presenti; evita duplicazioni.
- Idempotenza: ogni step deve poter essere rieseguito senza effetti collaterali.
- Path-safety: nessuna write/copy/rm senza passare da utility di sicurezza.
- Fail-fast & messaggi chiari: errori espliciti e log azionabili.
- Compatibilità cross-platform: Windows/Linux (path, encoding, newline).
- Contratti condivisi: per funzioni che richiedono solo `base_dir/raw_dir/md_dir/slug`, usa `semantic.types.ClientContextProtocol` invece di protocolli locali duplicati.
- No side-effects a import-time: nessun I/O o lettura di env vars a livello di modulo.
- Adozione dipendenze: prima di aggiungere una libreria, valuta sicurezza, licenza, maturità, impatto su CI/CD e alternative già adottate.

---

## Struttura & naming
- Slug e nomi cartelle: normalizza con `to_kebab()` dove previsto.
- RAW/BOOK/SEMANTIC: non cambiare convenzioni senza aggiornare orchestratori e documentazione.
- File generati: mantieni posizionamento in `output/timmy-kb-<slug>/...`.

---

## Python style
- Tipizzazione obbligatoria sui moduli core: annota parametri e ritorni. Usa `Optional[...]` in modo esplicito.
- Evita `Any` e i wild import; mantieni import espliciti e ordinati.
- Funzioni corte, una responsabilità; preferisci pure functions dove possibile.
- No side-effects in import (es. no I/O top-level).
- Estrai helper privati (SRP) se una funzione supera ~40-50 righe o mescola traversal/rendering/I/O.
- Aggiorna le docstring delle funzioni core (stile Google o Sphinx).

---

## Linting & Formatting
- Ruff è il linter SSoT: replica regole flake8/bandit in Ruff; se manca qualcosa, aggiungi in `pyproject.toml`.
- Black e isort: obbligatori per formattazione/ordinamento import.

## Typing & Pylance
- Per dependency opzionali usa narrowing esplicito:
  - `if fn is None: raise RuntimeError("...")` prima di chiamare funzioni opzionali.
  - Wrapper come `_require_callable(fn, name)` nei layer adapter/runner.
- Evita accessi a metodi su `None` (es. `.strip`): usa normalizzatori tipo `_norm_str`.
- Streamlit: preferisci API stabili (`st.rerun`) con fallback a `experimental_*` solo se assente.
- Type check rapidi:
  - Mypy: `make type`
  - Pyright: `make type-pyright` (richiede `pyright` o `npx`)
- Linting automatico in CI: ogni PR/build passa Black, Ruff e isort. Dove compare Flake8 negli standard, consideralo allineato a Ruff.

---

## Logging & redazione
- Usa il logger strutturato dove disponibile; fallback a `logging.basicConfig` negli script.
- Redazione automatica attiva quando richiesto (`LOG_REDACTION`): non loggare segreti o payload completi.
- Includi event e metadati essenziali (slug, conteggi, esiti) per ogni operazione rilevante.
- Non loggare secrets, password, token o variabili d'ambiente (mai l'intero `os.environ`). Usa `dotenv` o `vault` per i secrets.

---

## Sicurezza I/O
- Path-safety: usa `ensure_within_and_resolve` (o SSoT equivalenti) per prevenire traversal; evita concatenazioni manuali.
- Scritture atomiche: `safe_write_text/bytes` per generare/aggiornare file (niente write parziali).
- Sanitizzazione nomi file: usa utility dedicate prima di creare file da input esterni.
- DRY validazioni: centralizza controlli ricorrenti (listing sicuro dei Markdown, ecc.).

---

## Orchestratori & UI
- Orchestratori (`pre_onboarding`, `tag_onboarding`, `onboarding_full`) + facade `semantic.api` per la semantica:
  - Niente input bloccanti nei moduli di servizio; tutta la UX rimane negli orchestratori.
  - Gestisci `--non-interactive` per batch/CI.
- UI (`onboarding_ui.py`):
  - Gating a due input (slug, nome cliente), poi mostra le schede.
  - Drive: crea struttura → genera README → download su raw.
  - Semantica: conversione → arricchimento → README/SUMMARY → preview (opz.).
  - Usa `_safe_streamlit_rerun()` per compatibilità con stubs/tipi.

---

## Error handling & exit codes
- Solleva eccezioni tipizzate (es. `ConfigError`, `PreviewError`), non `Exception` generiche.
- Mappa le eccezioni a exit codes coerenti negli script CLI.
- In UI mostra errori con messaggi chiari e non verbosi; logga il dettaglio tecnico.

---

## Drive & Git
- Drive: tutte le operazioni passano da `pipeline/drive_utils.py` o runner dedicati; evita API low-level dirette.
- Download RAW: usa la funzione di alto livello esposta nel runner UI.
- Git: push solo di `.md` in `book/`; ignora `.md.fp` e file binari.

---

## Test
- Genera dataset dummy con `py src/tools/gen_dummy_kb.py --slug dummy`.
- Piramide dei test: unit → middle/contract → smoke E2E (dummy). Niente dipendenze di rete nei test.
- Mocka Drive/Git nei test; verifica invarianti su `book/` e presenza di README/SUMMARY.

---

## Versioning & release
- SemVer + `CHANGELOG.md` (Keep a Changelog).
- Aggiorna README e i documenti in `docs/` quando cambi UX/flow.
- Tag/branch coerenti con la policy di versione (vedi `versioning_policy.md`).

---

## Contributi
- PR piccole, atomic commit, messaggi chiari (imperativo al presente).
- Copri con test i cambi di comportamento; mantieni l'asticella della qualità.

---

## Path-Safety Lettura (Aggiornamento)
- Letture Markdown/CSV/YAML nei moduli `pipeline/*` e `semantic/*`: usa sempre `pipeline.path_utils.ensure_within_and_resolve(base, p)` per ottenere un path risolto e sicuro prima di leggere.
- È vietato usare direttamente `open()` o `Path.read_text()` per file provenienti dalla sandbox utente senza passare dal wrapper.

---
