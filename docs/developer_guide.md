# Guida Sviluppatore – Timmy‑KB (v1.0.4)

Questa guida è rivolta a chi mantiene e sviluppa la pipeline. È allineata a **v1.0.4** (patch release) e include i miglioramenti non‑breaking in logging (redazione centralizzata), Drive, preview e push.

---

## 🎯 Obiettivi e principi

- **Nessun cambio di flusso** negli orchestratori: release di consolidamento.
- **Idempotenza** dove possibile; side‑effect (I/O, rete) confinati in funzioni dedicate.
- **Separazione ruoli**: orchestratori gestiscono UX/CLI; i moduli eseguono lavoro tecnico e **non** chiamano `sys.exit()` né `input()`.
- **Logging strutturato** unico per cliente; **no `print()`** nei moduli.
- **Eccezioni tipizzate** con mappatura stabile verso `EXIT_CODES`.

---

## 🗂️ Struttura del repository (essenziale)

```
src/
 ├─ pre_onboarding.py           # orchestratore fase iniziale
 ├─ onboarding_full.py          # orchestratore completo
 └─ pipeline/
     ├─ context.py             # caricamento env/.env, percorsi cliente, toggle redazione
     ├─ logging_utils.py       # get_structured_logger(...), rotazione + redazione
     ├─ env_utils.py           # get_env_var/get_bool/get_int, redact_secrets
     ├─ exceptions.py          # tassonomia errori + EXIT_CODES
     ├─ config_utils.py        # gestione config.yaml (lettura/scrittura/merge)
     ├─ drive_utils.py         # Google Drive API (BFS ricorsivo, retry con budget)
     ├─ content_utils.py       # PDF→Markdown, README/SUMMARY, validazioni
     ├─ gitbook_preview.py     # build/serve HonKit in Docker (logs redatti su toggle)
     ├─ github_utils.py        # push su GitHub (branch da env, push incrementale)
     ├─ path_utils.py          # safety: is_safe_subpath, validate_slug, sanitize_filename
     └─ constants.py           # nomi file/dir comuni (BOOK_JSON_NAME, ecc.)
docs/
 ├─ index.md
 ├─ user_guide.md
 ├─ developer_guide.md
 ├─ architecture.md
 ├─ coding_rule.md
 ├─ policy_push.md
 └─ versioning_policy.md
```

---

## 🔌 Orchestratori: ruolo e CLI

Gli orchestratori sono gli **unici** autorizzati a:

- leggere **input interattivi** (`input()`/prompt);
- determinare la **modalità** (`--non-interactive`, `--dry-run`, `--no-drive`, `--push|--no-push`);
- gestire la **preview Docker** (pre‑check e scelta utente);
- mappare eccezioni → `EXIT_CODES`.

### Convenzioni CLI (v1.0.4)

- **Slug “soft”**: posizionale oppure `--slug`. In interattivo, se assente, viene chiesto a prompt.
- **Alias deprecati**: `--skip-drive`, `--skip-push` accettati con **warning** e rimappati a `--no-drive`/`--no-push`.
- **Preview**: in **non‑interattivo**, se Docker non è disponibile → **auto‑skip**; in interattivo è prevista conferma/ritentativi.
- **Push**: in **non‑interattivo** è **false** a meno di `--push`; in interattivo viene chiesto (default **NO**). Il push è **incrementale** (pull‑rebase→commit→push), senza `--force` di default.

---

## 🧱 Moduli `pipeline/*`: linee guida

### Logging (aggiornato)

- Usa `get_structured_logger(name, log_file=..., context=..., run_id=..., extra_base=..., rotate=...)`.
- **Redazione centralizzata**: il toggle è in `context.redact_logs` (vedi sotto). Se `True`, gli orchestratori passano il flag ai moduli che trattano dati sensibili (es. preview/push), i quali applicano `env_utils.redact_secrets(...)` ai messaggi potenzialmente sensibili; `logging_utils` non riscrive i record.
- **Vietato** `print()` nei moduli; usa `logger.info/warning/error`.
- Unico file per cliente: `output/timmy-kb-<slug>/logs/onboarding.log` (rotazione opzionale).
- Includi metadati utili (`slug`, `file_path`, ecc.) tramite `extra={...}`.
- Degrado **safe** a console‑only se il file non è scrivibile (warning automatico).

### Error handling

- Solleva solo eccezioni della tassonomia in `exceptions.py` (es. `ConfigError`, `DriveDownloadError`, `PreviewError`).
- **Niente `sys.exit()` nei moduli: l’uscita è gestita negli orchestratori.
- Evita `except Exception` generici; cattura tipi specifici e rilancia `PipelineError`/derivate con contesto.

### Path & IO

- Usa `pathlib.Path`, encoding `utf-8`, e scritture **atomiche** (es. `safe_write_file`).
- Controlla i percorsi con `is_safe_subpath(path, base)` prima di scrivere/leggere.
- Mantieni la struttura `output/timmy-kb-<slug>/{raw,book,config,logs}`.

### Dipendenze esterne

- Drive in `drive_utils.py` (**BFS ricorsivo**, **retry esponenziale con tetto**).
- Conversione in `content_utils.py` (PDF→Markdown + `README.md`/`SUMMARY.md`).
- Preview Docker in `gitbook_preview.py` (container **detached**; `redact_logs` passato dall’orchestratore).
- Git in `github_utils.py` (branch da `GIT_DEFAULT_BRANCH`; **push incrementale** senza `--force` per default).

---

## 🌿 Variabili d’ambiente (per sviluppatori)

- `GIT_DEFAULT_BRANCH` → branch di default per push/checkout (es. `main`).
- `GITHUB_TOKEN` → token per il push su GitHub.
- `DRIVE_ID` / `DRIVE_PARENT_FOLDER_ID` → radice su Google Drive.
- `SERVICE_ACCOUNT_FILE` / `GOOGLE_APPLICATION_CREDENTIALS` → path JSON del Service Account.
- `LOG_REDACTION` → **policy redazione**: `auto|on|off` (vedi sotto).
- `ENV` → ambiente logico `dev|prod|production|ci` (influenza `auto`).
- `CI` → se presente/true, influenza `auto`.

> Non committare `.env` o il JSON delle credenziali.

### Policy di redazione log (QW7)

- Il valore viene valutato dagli orchestratori con `env_utils.is_log_redaction_enabled(context)`; non è memorizzato nel contesto.
- `LOG_REDACTION=on|always|1|true|yes|on` ⇒ **redazione attiva**.
- `LOG_REDACTION=off|never|0|false|no` ⇒ **redazione disattiva**.
- `LOG_REDACTION=auto` (default): **ON** se `ENV ∈ {prod, production, ci}` **oppure** `CI=true` **oppure** sono presenti credenziali sensibili nel contesto; **OFF** se `log_level=DEBUG`.
- I moduli **non** devono implementare logiche custom: usano `get_structured_logger(..., context=context)` e passano eventuale `redact_logs` ai servizi esterni (es. preview/push).

---

## 🧩 Flussi tecnici (sintesi)

1. **pre_onboarding**: crea struttura locale; opzionale struttura su Drive, carica `config.yaml` e aggiorna gli ID nel config locale.
2. **onboarding_full**: opzionale download da Drive (RAW) → conversione in Markdown (BOOK) → validazioni → preview Docker → push opzionale (**incrementale**).

Entrambi scrivono sullo **stesso file di log** del cliente.

---

## 🚦 EXIT\_CODES e tassonomia errori

Gli orchestratori mappano le eccezioni dei moduli verso codici deterministici. Mantieni la tassonomia aggiungendo nuove eccezioni solo quando necessario e aggiornando la tabella.

Esempi comuni:

- `ConfigError` → `2`
- `PreviewError` → `30`
- `DriveDownloadError` → `21`
- `PushError` → `40`

---

## 🔁 Novità e comportamenti chiave in v1.0.4

### `logging_utils.get_structured_logger`

- Supporta **rotazione** opzionale via `RotatingFileHandler`.
- Accetta `run_id` per correlare i log di una singola esecuzione e `extra_base` per campi extra costanti.
- Inietta automaticamente `slug`/`run_id` nei record via filtro contestuale.
- **Nota**: la redazione dei messaggi è demandata ai moduli che gestiscono dati sensibili; `logging_utils` non altera i record.
- Degrada a **console‑only** se il file non è scrivibile (nessun crash).

### `context.ClientContext.load`

- Parametro `interactive` **deprecato** e ignorato (log DEBUG una sola volta).
- Non calcola un flag di redazione; la valutazione è demandata agli orchestratori tramite `is_log_redaction_enabled(context)`.
- Ritorna un contesto con logger **iniettato** e path canonici (`output/raw/book/config/logs`).

### `gitbook_preview.run_gitbook_docker_preview`

- Default **detached**: `wait_on_exit=False`.
- Accetta `redact_logs: bool`: redazione dei messaggi di log (non delle eccezioni), passato dagli orchestratori.
- Build/serve HonKit **idempotenti**, con creazione `book.json`/`package.json` minimi se mancanti (scrittura **atomica**).

### `github_utils.push_output_to_github`

- **Default incrementale**: clone in `output/timmy-kb-<slug>/.push_<rand>` → `git pull --rebase` → `commit` (solo se diff) → `git push` (senza `--force`).
- Retry automatico singolo in caso di rifiuto non‑fast‑forward; conflitti bloccano l’operazione con messaggio chiaro.

### `drive_utils` (focus storico)

- **BFS ricorsivo** con **idempotenza** MD5/size; **retry esponenziale** con jitter e tetto (`max_total_delay`).
- Metriche leggere su logger e `context.step_status`.
- `redact_logs` propagato ai log sensibili.

---

## 🧪 Qualità e strumenti (facoltativi ma raccomandati)

- **Ruff** per lint/format veloci (`ruff check --fix src`).
- **Black** per formattazione consistente.
- **Mypy** (profilo “strict‑ish”) per type‑checking dei moduli toccati.
- **pre‑commit** per hook (`black`, `ruff`, `check‑yaml`, trimming).

> Questi strumenti non cambiano il runtime; aiutano a evitare regressioni.

---

## 🔄 Linee guida per PR

- Aggiorna la **documentazione** se tocchi logica o CLI.
- Non introdurre `print()` o `sys.exit()` nei moduli.
- Mantieni backwards‑compat delle firme pubbliche nei moduli richiamati dagli orchestratori.
- Aggiungi test manuali: dry‑run, no‑drive, interattivo/non‑interattivo.

---

## 🛠️ Troubleshooting rapido

- **Docker non disponibile**: in non‑interattivo la preview viene saltata automaticamente; in interattivo gli orchestratori gestiscono conferme/ritentativi.
- **Service Account file mancante**: i moduli sollevano `ConfigError` con messaggio chiaro; in `pre_onboarding` è possibile operare in `--dry-run`.
- **Rifiuto push (non‑fast‑forward)**: la procedura incrementale tenta un `pull --rebase` automatico; in caso di conflitto, interrompe con indicazioni.

---

*Questo documento aggiorna e sostituisce la precedente versione v1.0.3.*

