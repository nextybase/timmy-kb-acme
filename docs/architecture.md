# Architettura Tecnica – Timmy-KB (v1.0.3 Stable)

Questa pagina descrive l’architettura **attuale** (release di consolidamento). È allineata al CHANGELOG 1.0.3 e recepisce i fix di robustezza introdotti (preview *detached* con stop automatico, logging centralizzato in `context.py`, cache regex slug in `path_utils.py`). **Flusso invariato.**

---

## 1) Principi architetturali

- **Separazione ruoli**: gli **orchestratori** gestiscono UX/CLI, scelte interattive e mapping errori; i **moduli** eseguono operazioni tecniche e non terminano il processo.
- **HiTL pragmatico**: prompt solo negli orchestratori; in batch (`--non-interactive`) tutto è deterministico.
- **Idempotenza e sicurezza**: path-safety (`is_safe_subpath`), scritture atomiche, singolo log per cliente, nessun segreto nei log.
- **Coerenza documentale**: ogni modifica che impatta il comportamento aggiorna contestualmente la documentazione.

---

## 2) Mappa dei componenti

```
src/
 ├─ pre_onboarding.py          # orchestratore Fase 0 (setup cliente + Drive opzionale)
 ├─ onboarding_full.py         # orchestratore Fase 1 (download→conversione→preview→push)
 └─ pipeline/
     ├─ context.py             # carica .env/ambiente e risolve percorsi; logging centralizzato (no print)
     ├─ logging_utils.py       # get_structured_logger(name, log_file=?, context=?)
     ├─ exceptions.py          # tassonomia + EXIT_CODES (mapping orchestratori)
     ├─ path_utils.py          # is_safe_subpath(...); cache regex slug + clear esplicito
     ├─ config_utils.py        # lettura/scrittura/merge config.yaml (backup .bak)
     ├─ drive_utils.py         # Google Drive API: BFS ricorsivo download RAW, creazione struttura remota
     ├─ content_utils.py       # PDF→Markdown + generate_summary_markdown + generate_readme_markdown + validate_markdown_dir
     ├─ gitbook_preview.py     # ensure_{book,package}.json; build+serve HonKit (mai prompt, mai bloccare)
     └─ github_utils.py        # push su GitHub (branch da env: GIT_DEFAULT_BRANCH, fallback main)
```

**Dati e output** per cliente: `output/timmy-kb-<slug>/{raw,book,config,logs}` con file log unico `onboarding.log`.

---

## 3) Flussi end-to-end (immutati)

### A) `pre_onboarding.py`

1. **Input**: `slug` (posizionale o `--slug`), `--name`, `--dry-run`, `--non-interactive`.
2. **Setup locale**: crea struttura `raw/`, `book/`, `config/`, `logs/`; crea/aggiorna `config.yaml` (backup automatico).
3. **Drive (opzionale)**: se non `--dry-run`, crea cartella cliente nello Shared Drive (o cartella padre), struttura remota da YAML, carica `config.yaml`, aggiorna config locale con gli **ID** Drive.
4. **Log**: scrive su `output/.../logs/onboarding.log` (nessun `print()`).

### B) `onboarding_full.py`

1. **Input**: `slug`, `--non-interactive`, `--dry-run`, `--no-drive`, `--push|--no-push`, `--port` (4000).
2. **Download RAW (opz.)**: se abilitato e non `--dry-run`, scarica i PDF dalla `drive_raw_folder_id` in `raw/` (BFS ricorsivo).
3. **Conversione**: genera Markdown strutturato in `book/` e produce `SUMMARY.md` + `README.md`; valida la directory.
4. **Preview (Docker)**:
   - Se Docker è presente: **build + serve HonKit in modalità *****detached*** (non blocca).\
     L’**orchestratore** esegue **stop automatico del container all’uscita**, indipendentemente dal push.
   - Se Docker non c’è →\
     **non-interattivo**: **auto-skip**;\
     **interattivo**: prompt “proseguire senza anteprima?” (default NO).
5. **Push (opz.)**: se esplicitato `--push` (o confermato in interattivo) e c’è `GITHUB_TOKEN`, esegue `push_output_to_github(...)` sul branch da `GIT_DEFAULT_BRANCH` (fallback `main`).
6. **Log/Exit**: log strutturati; mapping eccezioni → `EXIT_CODES` deterministici.

---

## 4) Decisioni runtime (state machine minimale)

- **Slug**: posizionale > `--slug`; in interattivo se assente → prompt.
- **Modalità**:
  - `--non-interactive` → nessun prompt; preview **auto-skip** se Docker assente; push **false** a meno di `--push`.
  - interattivo → prompt per anteprima (se Docker assente) e per push (default **NO**).
- **Alias deprecati**: `--skip-drive`/`--skip-push` rimappati a `--no-drive`/`--no-push` con **warning**.
- **Branch Git**: letto da `GIT_DEFAULT_BRANCH` (env/.env) per checkout/push.

---

## 5) Logging, errori, sicurezza

- **Logger unico** per cliente: `get_structured_logger("pre_onboarding"|"onboarding_full", log_file=...)`.
- **No **`` nei moduli e negli orchestratori (solo prompt dove previsto e output informativi via logger).
- **Tassonomia errori** (esempi): `ConfigError`, `DriveDownloadError`, `PreviewError`, `PushError` → mappati a `EXIT_CODES` (2, 21, 30, 40, ...).
- **Path-safety**: ogni operazione su file/dir verifica `is_safe_subpath`; scritture atomiche.
- **Segreti**: mai in log; credenziali solo via env/`.env`/`GOOGLE_APPLICATION_CREDENTIALS`.

---

## 6) Modifiche di questa sessione (coerenza con il codice)

- **Orchestratori**: early-logger nello `__main__`; correzione alias deprecati; **stop automatico** del container preview all’uscita.
- **Preview** (`gitbook_preview.py`): nessun prompt nel modulo; build→serve HonKit; invocazione sempre *detached*.
- **Push** (`github_utils.py`): validazione token esplicita; branch da `GIT_DEFAULT_BRANCH` (fallback `main`).
- **Slug** (`path_utils.py`): cache della regex letta da `config/config.yaml` + funzione di **clear** esplicita.
- **Documentazione**: pagine allineate al comportamento effettivo.

> Nota: tutte le modifiche sono **backward-compatible** e non alterano il flusso.

---

## 7) Variabili d’ambiente (rilevanti in architettura)

- `GIT_DEFAULT_BRANCH` – branch di default per push/checkout (es. `main`)
- `GITHUB_TOKEN` – token necessario per il push
- `DRIVE_ID` / `DRIVE_PARENT_FOLDER_ID` – radice Drive o cartella padre
- `GOOGLE_APPLICATION_CREDENTIALS` – path JSON del Service Account

---

## 8) Appendice – Sequenza sintetica (ASCII)

```
[pre_onboarding]                [onboarding_full]
    │                                 │
    │ slug/name/env                   │ slug/env/flags
    ▼                                 ▼
 struttura locale                     (opt) download RAW da Drive
    │                                 │
 config.yaml (±Drive IDs)             conversione PDF→MD (book/)
    │                                 │
 (opt) struttura Drive + upload cfg   genera SUMMARY.md / README.md
    │                                 │
 log unico onboarding.log             preview Docker (build/serve DETACHED | skip)
    │                                 │
    └────────► pronto per Fase 1      (opt) push su GitHub (branch da env)
                                       ↓
                                stop automatico container
```

**Stato**: architettura consolidata, pronta per estensioni future senza rompere gli orchestratori.

