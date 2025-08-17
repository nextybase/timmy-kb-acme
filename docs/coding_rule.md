# Regole di Codifica – Timmy‑KB (v1.0.3 Stable)

Queste regole valgono per tutto il codice del repository. La 1.0.3 è una **release di consolidamento**: non cambia i flussi, ma chiarisce standard e coerenza con le modifiche fatte in questa sessione (logger “early” negli orchestratori, alias deprecati, pulizia preview).

---

## 1) Linguaggio, stile, formattazione
- **Python ≥ 3.10**.
- Preferisci **type hints** completi per le funzioni pubbliche; almeno gli argomenti principali e il `-> ReturnType`.
- **Docstring** brevi stile Google (Descrizione, Args, Returns, Raises). Evita ripetizioni inutili.
- Usa `pathlib.Path`; encoding **utf‑8** per ogni I/O di testo.
- Niente `print()` nel codice di libreria; tutta la messaggistica passa dal **logger**.
- Facoltativo (ma raccomandato): **Ruff** (lint/auto‑fix), **Black** (format), **Mypy** (type‑check “strict‑ish”), **pre‑commit**.

## 2) Architettura e responsabilità
- **Orchestratori** (`pre_onboarding.py`, `onboarding_full.py`): unica sede per input interattivi, decisioni di flusso (batch vs interattivo), preview Docker e mapping eccezioni → `EXIT_CODES`. In questa sessione sono stati rimossi i `print()` nello `__main__` a favore del **logger early**.
- **Moduli** in `pipeline/*`: zero prompt, zero `sys.exit()`. Espongono funzioni pure dove possibile; side‑effect confinati e documentati.
- **Separazione**: l’orchestratore decide *se* fare qualcosa; il modulo implementa *come* farlo.

## 3) Logging
- Un **unico file di log per cliente**: `output/timmy-kb-<slug>/logs/onboarding.log`.
- Usa `get_structured_logger(name, log_file=..., context=...)`.
- Includi metadati utili via `extra={...}` (es. `slug`, `file_path`), ma **mai segreti** (token, credenziali).
- Livelli: `info` per eventi di flusso, `warning` per comportamenti deprecati o condizioni recuperabili, `error` per failure; niente `print()`.

## 4) Errori ed EXIT_CODES
- Solleva solo eccezioni della tassonomia in `pipeline/exceptions.py` (es. `ConfigError`, `DriveDownloadError`, `PreviewError`, `PushError`).
- I moduli **non** chiamano `sys.exit()`: l’uscita è gestita dagli orchestratori che mappano le eccezioni su `EXIT_CODES` **deterministici**.
- Non sopprimere eccezioni generiche: rilancia con contesto o converti nella tassonomia.

## 5) Sicurezza file‑system e I/O
- Verifica sempre i percorsi con `is_safe_subpath(child, root)` prima di leggere/scrivere.
- Usa scritture **atomiche** (es. `safe_write_file(path, data)`); non sovrascrivere “a mano” file critici.
- Mantieni la struttura standard per cliente: `raw/`, `book/`, `config/`, `logs/` sotto `output/timmy-kb-<slug>/`.
- Non serializzare segreti su disco; il JSON del Service Account resta **fuori** dall’output cliente.

## 6) Regole CLI (coerenza 1.0.3)
- **Slug “soft”**: accetta posizionale o `--slug`; in interattivo, se assente, chiedilo a prompt.
- **Modalità batch** (`--non-interactive`): nessun prompt; se Docker non è disponibile la preview viene **saltata automaticamente**; il push è **false** a meno di `--push`.
- **Alias deprecati**: `--skip-drive` e `--skip-push` sono accettati con **warning** e rimappati a `--no-drive` / `--no-push`.
- **Branch Git**: leggi `GIT_DEFAULT_BRANCH` dall’ambiente (fallback `main`) nei moduli che interagiscono con Git.

## 7) Dipendenze e integrazioni
- **Drive**: API isolate in `drive_utils.py` (download RAW BFS/idempotente, creazione struttura remota).
- **Conversione**: logica in `content_utils.py` (PDF→Markdown strutturato, `SUMMARY.md` e `README.md`, validazioni).
- **Preview**: `gitbook_preview.py` si occupa solo di **build/serve** in Docker; la decisione di eseguire/evitare resta negli orchestratori. In questa sessione: pulizia import inutili, nessun cambio di firma.
- **GitHub**: `github_utils.py` legge `GIT_DEFAULT_BRANCH` e usa `GITHUB_TOKEN` se presente.

## 8) Qualità del codice e PR
- Ogni modifica che impatta la CLI o i flussi **deve** aggiornare la documentazione (README e `docs/*`) e il `CHANGELOG`.
- Mantieni **backward‑compatibility** delle firme pubbliche dei moduli; se rompi la compatibilità, è una **major**.
- Aggiungi esempi manuali per: `--dry-run`, `--no-drive`, interattivo vs non‑interattivo, preview con/ senza Docker.
- Nelle PR evita refactor gratuiti sugli orchestratori: sono **stabili** nella 1.0.3.

## 9) Sicurezza e privacy
- Non loggare contenuti dei documenti del cliente oltre ai metadati strettamente necessari.
- I segreti (token, credenziali) non devono comparire in log, eccezioni, file temporanei.
- Non esportare dati al di fuori dell’output cliente senza consenso esplicito.

---

### Checklist minima per accettare una PR
- [ ] Nessun `print()` nei moduli; orchestratori con **early logger** coerente.
- [ ] Niente `sys.exit()` nei moduli; eccezioni corrette e mappate dagli orchestratori.
- [ ] Path‑safety e scritture atomiche rispettate.
- [ ] Comportamento 1.0.3: slug “soft”, alias deprecati con warning, preview coerente, branch da env.
- [ ] Documentazione e CHANGELOG aggiornati se necessario.

