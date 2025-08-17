# Guida Sviluppatore – Timmy‑KB (v1.0.3)

Questa guida è rivolta a chi mantiene e sviluppa la pipeline. È allineata a **v1.0.3** e non introduce cambi di flusso: consolida standard e chiarisce confini tra orchestratori e moduli `pipeline/*`.

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
     ├─ context.py             # caricamento env/.env e percorsi cliente
     ├─ logging_utils.py       # get_structured_logger(...)
     ├─ exceptions.py          # tassonomia errori + EXIT_CODES
     ├─ config_utils.py        # gestione config.yaml (lettura/scrittura/merge)
     ├─ drive_utils.py         # Google Drive API (BFS ricorsivo, download RAW)
     ├─ content_utils.py       # PDF→Markdown, README/SUMMARY, validazioni
     ├─ gitbook_preview.py     # build/serve HonKit in Docker
     ├─ github_utils.py        # push su GitHub (branch da env)
     ├─ path_utils.py          # safety: is_safe_subpath, utilità path
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

### Convenzioni CLI (v1.0.3)
- **Slug “soft”**: puoi passarlo come **posizionale** oppure `--slug`. In interattivo, se assente, viene chiesto a prompt.
- **Alias deprecati**: `--skip-drive`, `--skip-push` sono accettati con **warning** e rimappati a `--no-drive`/`--no-push`.
- **Preview**: in **non‑interattivo**, se Docker non è disponibile → **auto‑skip**; in interattivo viene chiesta conferma a proseguire senza anteprima.
- **Push**: in **non‑interattivo** è **false** a meno di `--push`; in interattivo viene chiesto (default **NO**).

---

## 🧱 Moduli `pipeline/*`: linee guida
### Logging
- Usa `get_structured_logger(name, log_file=..., context=...)`.
- **Vietato** `print()` nei moduli; usa `logger.info/warning/error`.
- Unico file per cliente: `output/timmy-kb-<slug>/logs/onboarding.log`.
- Includi metadati utili (`slug`, `file_path`, ecc.) tramite `extra={...}`.
- Evita di loggare segreti (token, credenziali).

### Error handling
- Solleva solo eccezioni della tassonomia in `exceptions.py` (es. `ConfigError`, `DriveDownloadError`, `PreviewError`).
- **Niente `sys.exit()`** nei moduli: l’uscita è gestita negli orchestratori.
- Non catturare eccezioni generiche senza rilanciarle con contesto.

### Path & IO
- Usa `pathlib.Path`, encoding `utf-8`, e scritture **atomiche** (es. `safe_write_file`).
- Controlla i percorsi con `is_safe_subpath(base, root)` prima di scrivere/leggere.
- Mantieni la struttura `output/timmy-kb-<slug>/{raw,book,config,logs}`.

### Dipendenze esterne
- Isola chiamate a Google Drive in `drive_utils.py` (BFS ricorsivo, idempotente).
- Isola conversioni in `content_utils.py` (PDF→Markdown con generazione `README.md`/`SUMMARY.md`).
- Isola preview Docker in `gitbook_preview.py` (build/serve HonKit); la **decisione** di eseguire/saltare resta all’orchestratore.
- Isola Git in `github_utils.py`; il **branch** si legge da `GIT_DEFAULT_BRANCH` (fall‑back su `main` se non definito).

---

## 🌿 Variabili d’ambiente (per sviluppatori)
Le principali variabili lette via `context.py`/`.env`:
- `GIT_DEFAULT_BRANCH` → branch di default per push/checkout (es. `main`).
- `GITHUB_TOKEN` → token per il push su GitHub.
- `DRIVE_ID` o `DRIVE_PARENT_FOLDER_ID` → radice su Google Drive.
- `GOOGLE_APPLICATION_CREDENTIALS` → path al JSON del Service Account.

> Non committare `.env` o il JSON delle credenziali.

---

## 🧩 Flussi tecnici (sintesi)
1. **pre_onboarding**: crea struttura locale; opzionalmente crea struttura su Drive, carica `config.yaml` e aggiorna gli ID nel config locale.
2. **onboarding_full**: opzionale download da Drive (RAW) → conversione in Markdown (BOOK) → validazioni → preview Docker → push opzionale.

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
- Mantieni backward‑compat delle firme pubbliche nei moduli richiamati dagli orchestratori.
- Aggiungi test manuali: dry‑run, no‑drive, interattivo/non‑interattivo.

---

## Gestione del logging e del contesto

Tutti i moduli che gestiscono contesto e configurazioni devono utilizzare il **logger strutturato**
(`logging_utils.get_structured_logger`) per qualsiasi output diagnostico o operativo.  
L’uso di `print()` è vietato.  

Le eccezioni interattive sono ammesse solo nei casi in cui l’utente debba confermare
o correggere valori critici (ad esempio lo *slug* del cliente). In questi scenari viene
utilizzata la funzione `input()`, limitatamente all’esecuzione in modalità interattiva.  

Questa regola garantisce:
- **Centralizzazione dei log**, con tracciabilità uniforme.
- **Pulizia della console**, senza messaggi informali o “silenti”.
- **Coerenza con le pipeline**, che intercettano gli eventi solo dal logger.


