# Timmy-KB — Knowledge Base Pipeline

Pipeline modulare per trasformare i PDF del cliente in una **KB Markdown AI‑ready** (GitBook/HonKit), con anteprima Docker opzionale e (opzionale) push su GitHub.

> **Stato**: v1.0.3 Stable (documento aggiornato con i micro‑fix di robustezza introdotti in questa sessione; il bump versione verrà finalizzato nel `CHANGELOG.md`).

---

## TL;DR
1. **Pre‑onboarding** (setup locale + Drive opzionale)  
   ```bash
   py src/pre_onboarding.py --slug acme --non-interactive --dry-run
   ```
2. **Onboarding completo** (download → conversione → preview → push)  
   ```bash
   # senza Drive e senza push (anteprima *detached* se Docker è disponibile)
   py src/onboarding_full.py --slug acme --no-drive --non-interactive
   ```

---

## Requisiti
- **Python ≥ 3.10**
- **Docker** (solo per la preview HonKit; se assente la preview viene saltata in batch)
- **Google Drive API**: credenziali Service Account (.json)
- **GitHub**: `GITHUB_TOKEN` (solo se si vuole eseguire il push)

### Variabili d’ambiente
- `SERVICE_ACCOUNT_FILE` / `GOOGLE_APPLICATION_CREDENTIALS` — credenziali GCP
- `DRIVE_ID` (o `DRIVE_PARENT_FOLDER_ID`) — radice per i PDF del cliente
- `GITHUB_TOKEN` — PAT per il push (opzionale)
- `GIT_DEFAULT_BRANCH` — branch di default per il push (fallback `main`)

---

## Struttura di output per cliente
```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF scaricati (opzionale)
  ├─ book/       # Markdown generati + SUMMARY.md + README.md
  ├─ config/     # config.yaml, mapping semantico
  └─ logs/       # onboarding.log (logger unico per cliente)
```

---

## Flussi

### 1) Pre‑onboarding
Crea la struttura locale, inizializza/aggiorna `config.yaml` e, se richiesto, prepara/aggiorna la struttura su Drive.

Esempi:
```bash
# setup minimale, senza servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# setup con Drive (richiede variabili d'ambiente corrette)
py src/pre_onboarding.py --slug acme
```

### 2) Onboarding completo
Converte i PDF in Markdown strutturato, genera `SUMMARY.md` e `README.md`, avvia la **preview HonKit** (se Docker disponibile) e, se richiesto, pubblica su GitHub.

Esempi:
```bash
# batch/CI: niente prompt, preview saltata se Docker non c'è, push disabilitato
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# interattivo: se Docker assente chiede se proseguire; chiede conferma push
py src/onboarding_full.py --slug acme --no-drive
```

---

## Anteprima (HonKit + Docker)
- L’anteprima viene eseguita **sempre in modalità _detached_** (non blocca il flusso).
- L’**orchestratore** arresta **automaticamente** il container **alla fine** dell’esecuzione.
- Se Docker **non è disponibile**:  
  - in `--non-interactive` la preview è **auto‑skip**;  
  - in modalità interattiva viene chiesto se proseguire senza anteprima (default **NO**).

Porta e container:
- Porta default: `4000` (override: `--port 4000`)
- Nome container: `honkit_preview_<slug>`

---

## Push su GitHub (opzionale)
- Eseguito da `src/pipeline/github_utils.py`
- Richiede `GITHUB_TOKEN`
- Branch letto da `GIT_DEFAULT_BRANCH` (fallback `main`)
- In batch il push **non** avviene a meno di `--push`; in interattivo viene richiesto all’utente
- Pubblica **solo** i file `.md` sotto `book/` (esclusi `.bak`)

Esempi:
```bash
# push esplicito in batch
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push
```

---

## Regole operative (estratto)
- **Orchestratori**: UX/CLI, prompt e mapping deterministico eccezioni→EXIT_CODES
- **Moduli**: azioni tecniche, **niente `input()`/`sys.exit()`**
- **Logging**: solo logger strutturati (`onboarding.log`), **no `print()`**
- **Sicurezza I/O**: `is_safe_subpath`, scritture atomiche, niente segreti nei log
- **Slug**: validazione via regex (da `config/config.yaml`), con **cache** e funzione di `clear`

---

## Exit codes (estratto)
- `0` — esecuzione completata
- `2` — `ConfigError` (es. variabili mancanti, slug invalido in batch)
- `30` — `PreviewError`
- `40` — `PushError`

> La mappatura completa è nella documentazione utente.

---

## Tools

Gli strumenti in `src/tools/` sono **standalone e interattivi** (si eseguono da terminale).

- **cleanup_repo.py** — pulizia sicura degli artefatti locali di uno *slug* e, opzionalmente, eliminazione del repo GitHub convenzionale via `gh`.  
  *Uso:* `py src/tools/cleanup_repo.py` → segui i prompt (slug, global, remote, conferma).

- **gen_dummy_kb.py** — genera una KB di test completa con **slug `dummy`**, cartelle RAW da `config/cartelle_raw.yaml` e PDF dummy da `config/pdf_dummy.yaml` (fallback `.txt` se `fpdf` non è disponibile).  
  *Uso:* `py src/tools/gen_dummy_kb.py` → opzionale creazione `output/timmy-kb-dummy/repo`.

- **refactor_tool.py** — utility con due modalità: **Trova** (solo ricerca) e **Trova & Sostituisci** (anteprima e backup `.bak`).  
  *Uso:* `py src/tools/refactor_tool.py` → scegli dal menu (Trova / Trova & Sostituisci / Esci).

> Nota: logging strutturato; “path assenti/skip non critici” sono a livello **DEBUG**.

---

## Troubleshooting
- **Docker non installato** → la preview è saltata in batch; in interattivo puoi scegliere se proseguire senza anteprima.
- **Token GitHub mancante** → il push fallisce: imposta `GITHUB_TOKEN` o usa `--no-push`.
- **Slug invalido** → in batch errore; in interattivo ti verrà richiesto di correggerlo.

---

## Licenza
TBD.
