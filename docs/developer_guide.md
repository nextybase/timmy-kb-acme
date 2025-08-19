# Guida Sviluppatore – Timmy‑KB (v1.0.4)

Questa guida è rivolta a chi mantiene e sviluppa la pipeline. È allineata a **v1.0.4** (release di consolidamento) e include i miglioramenti non‑breaking su logging (redazione centralizzata), anteprima HonKit in Docker e push GitHub.

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
     ├─ context.py             # env/.env, percorsi cliente, policy redazione, logger iniettato
     ├─ logging_utils.py       # get_structured_logger(...): filtri contesto + redazione, rotazione
     ├─ env_utils.py           # get_env_var/get_bool/get_int, redact_secrets
     ├─ exceptions.py          # tassonomia errori + EXIT_CODES
     ├─ config_utils.py        # gestione config.yaml (lettura/scrittura/merge)
     ├─ drive_utils.py         # Google Drive API (BFS, retry con budget)
     ├─ content_utils.py       # PDF→Markdown, README/SUMMARY, validazioni
     ├─ gitbook_preview.py     # build/serve HonKit in Docker (rispetta logger redatto)
     ├─ github_utils.py        # push su GitHub (branch da env, push incrementale)
     ├─ path_utils.py          # safety: is_safe_subpath, validate_slug, sanitize_filename
     └─ constants.py           # nomi file/dir comuni

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

- leggere **input interattivi** (prompt);
- determinare la **modalità** (`--non-interactive`, `--dry-run`, `--no-drive`, `--push|--no-push`);
- gestire la **preview Docker** (pre‑check e scelte utente);
- mappare eccezioni → `EXIT_CODES`.

### Convenzioni CLI (v1.0.4)

- **Slug “soft”**: posizionale oppure `--slug`. In interattivo, se assente, viene chiesto a prompt.
- **Alias deprecati**: `--skip-drive`, `--skip-push` accettati con **warning** e rimappati a `--no-drive`/`--no-push`.
- **Preview**: in **non‑interattivo**, se Docker non è disponibile → **auto‑skip**; in interattivo è prevista conferma (default **Sì**) o proseguimento senza preview.
- **Push**: in **non‑interattivo** è **false** a meno di `--push`; in interattivo viene chiesto (default **NO**). Il push è **incrementale** (pull‑rebase→commit→push), senza `--force` di default.

---

## 🧱 Moduli `pipeline/*`: linee guida

### Logging (aggiornato)

- Usa `get_structured_logger(name, log_file=..., context=..., run_id=..., extra_base=..., rotate=...)`.
- **Redazione centralizzata nel logger**: se `context.redact_logs` è `True`, i messaggi/argomenti vengono **mascherati** via filtro interno (usa `env_utils.redact_secrets`). I moduli **non** implementano redazione personalizzata.
- **Vietato** `print()` nei moduli; usa `logger.info/warning/error`.
- Unico file per cliente: `output/timmy-kb-<slug>/logs/onboarding.log` (rotazione opzionale).
- Includi metadati utili (`slug`, `file_path`, ecc.) tramite `extra={...}`.
- Degrado **safe** a console‑only se il file non è scrivibile (warning automatico).

### Error handling

- Solleva solo eccezioni della tassonomia in `exceptions.py` (es. `ConfigError`, `DriveDownloadError`, `PreviewError`).
- **Niente `sys.exit()` nei moduli**: l’uscita è gestita negli orchestratori.
- Evita `except Exception` generici; cattura tipi specifici e rilancia `PipelineError`/derivate con contesto.

### Path & IO

- Usa `pathlib.Path`, encoding `utf-8`, e scritture **atomiche** (es. `safe_write_file`).
- Controlla i percorsi con `is_safe_subpath(path, base)` prima di scrivere/leggere.
- Mantieni la struttura `output/timmy-kb-<slug>/{raw,book,config,logs}`.

### Dipendenze esterne

- Drive in `drive_utils.py` (**BFS** e **retry** esponenziale con tetto).
- Conversione in `content_utils.py` (PDF→Markdown + `README.md`/`SUMMARY.md`).
- Preview Docker in `gitbook_preview.py` (container **detached**; rispetta il logger redatto; parametro `redact_logs` resta **supportato per compatibilità** con servizi che emettono log grezzi).
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

### Policy di redazione log (aggiornata)

- Il flag effettivo **vive nel contesto** (`ClientContext.redact_logs`) ed è calcolato in `ClientContext.load()` considerando:
  - `LOG_REDACTION=on|always|1|true|yes|on` ⇒ **redazione attiva**;
  - `LOG_REDACTION=off|never|0|false|no` ⇒ **redazione disattiva**;
  - `LOG_REDACTION=auto` (default): **ON** se `ENV ∈ {prod, production, ci}` **oppure** `CI=true` **oppure** sono presenti credenziali sensibili; **OFF** se `log_level=DEBUG`.
- I moduli usano il logger strutturato con `context` collegato; **nessuna** valutazione duplicata lato orchestratori.

---

## 🧩 Flussi tecnici (sintesi)

1. **pre_onboarding**: crea struttura locale; opzionale struttura su Drive; carica/aggiorna `config.yaml` con backup `.bak`.
2. **onboarding_full**: opzionale download da Drive (RAW) → conversione in Markdown (BOOK) → validazioni → preview Docker → push opzionale (**incrementale**) → cleanup.

Entrambi scrivono sullo **stesso file di log** del cliente.

---

## 🚦 EXIT_CODES e tassonomia errori

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
- **Redazione integrata**: se `context.redact_logs` è `True`, i messaggi/argomenti vengono mascherati prima della formattazione.
- Degrada a **console‑only** se il file non è scrivibile (nessun crash).

### `context.ClientContext.load`

- Parametro `interactive` **deprecato** e ignorato (log DEBUG una sola volta).
- **Calcola** il flag `redact_logs` in base a `ENV`, `CI`, `LOG_REDACTION`, presenza credenziali e `log_level`.
- Ritorna un contesto con logger **iniettato** e path canonici (`output/raw/book/config/logs`).

### `gitbook_preview.run_gitbook_docker_preview`

- Default **detached**.
- Può ricevere `redact_logs: bool` per compatibilità con sorgenti di log esterni; in ogni caso **rispetta** il logger redatto.

### `github_utils.push_output_to_github`

- **Default incrementale**: pull‑rebase → commit (solo se diff) → push (senza `--force`).
- Retry automatico singolo in caso di rifiuto non‑fast‑forward; conflitti bloccano l’operazione con messaggio chiaro.

### `drive_utils` (focus storico)

- **BFS ricorsivo** con **idempotenza** MD5/size; **retry** esponenziale con jitter e tetto.
- Metriche leggere su logger e `context.step_status`.

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

- **Docker non disponibile**: in non‑interattivo la preview viene saltata automaticamente; in interattivo gli orchestratori gestiscono conferme.
- **Service Account file mancante**: i moduli sollevano `ConfigError` con messaggio chiaro; in `pre_onboarding` è possibile operare in `--dry-run`.
- **Rifiuto push (non‑fast‑forward)**: la procedura incrementale tenta un `pull --rebase` automatico; in caso di conflitto, interrompe con indicazioni.

---

*Questo documento aggiorna e sostituisce la precedente versione v1.0.3.*

