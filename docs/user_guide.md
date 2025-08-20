# User Guide — Timmy‑KB (v1.0.4 Stable)

Questa guida spiega come usare la pipeline per generare una **KB Markdown AI‑ready** a partire da PDF del cliente, con anteprima HonKit (Docker) e, se vuoi, push su GitHub.

> Nota: i micro‑fix introdotti (preview *detached* con **stop automatico** in uscita, logging centralizzato, cache regex slug) sono già riflessi qui. Il bump versione verrà finalizzato nel `CHANGELOG.md` quando chiudiamo il giro.

---

## 1) Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima)
- **Credenziali Google** (Service Account JSON) per Google Drive
- (Opz.) **GitHub Token** (`GITHUB_TOKEN`) per il push

### Variabili d’ambiente

Imposta le variabili (via `.env` o ambiente di sistema):

- `SERVICE_ACCOUNT_FILE` oppure `GOOGLE_APPLICATION_CREDENTIALS` → path al JSON del Service Account
- `DRIVE_ID` (o `DRIVE_PARENT_FOLDER_ID`) → radice/parent dello spazio Drive
- `GITHUB_TOKEN` → necessario solo se vuoi pubblicare su GitHub
- `GIT_DEFAULT_BRANCH` → branch di default per il push (fallback `main`)
- `YAML_STRUCTURE_FILE` → **override opzionale** del file YAML di struttura cartelle usato dal *pre_onboarding* (default `config/cartelle_raw.yaml`; fallback `src/config/cartelle_raw.yaml`)

---

## 2) Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF scaricati (opzionale)
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ config/     # config.yaml, mapping semantico
  └─ logs/       # onboarding.log (logger unico per cliente)
```

> Lo **slug** deve rispettare la regex definita in `config/config.yaml`. In interattivo, se non valido ti verrà chiesto di correggerlo.

---

## 3) Flussi operativi

### A) Pre‑onboarding (setup) — *flusso interattivo di base*

```bash
py src/pre_onboarding.py
```

**Sequenza tipica**

1. **Slug cliente** → richiesto lo *slug* (es. `acme`). Se non valido, il sistema spiega e chiede nuovo valore.
2. **Creazione struttura locale** → genera cartelle `raw/`, `book/`, `config/`, `logs/` e `config.yaml` (con backup `.bak` se già presente).
3. **Google Drive (opzionale)**  
   - Se le variabili sono configurate: mostra l’ID e chiede se creare/aggiornare la struttura su Drive.  
   - Se mancano credenziali: chiede se proseguire senza Drive.  
4. **Riepilogo finale** → mostra azioni eseguite e dove trovare i file.

> In questa fase non ci sono anteprima né push: serve solo a predisporre l’ambiente.

---

### B) Onboarding completo — *flusso interattivo di base*

```bash
py src/onboarding_full.py
```

**Sequenza tipica**

1. **Slug cliente** → richiesto e validato.  
2. **Conversione PDF → Markdown** → avvio automatico con log; genera `SUMMARY.md` e `README.md` in `book/`.  
3. **Anteprima HonKit (Docker)**  
   - Se Docker disponibile: *«Avviare l’anteprima ora?»* (default **Sì**). Parte *detached*, non blocca la pipeline e viene fermata automaticamente.  
   - Se Docker assente: *«Proseguire senza anteprima?»* (default **No**). Se confermi, la pipeline continua.  
4. **Pubblicazione su GitHub (opzionale)**  
   - *«Eseguire il push su GitHub?»* (default **No**). Se accetti, controlla `GITHUB_TOKEN` e propone branch (`GIT_DEFAULT_BRANCH`, fallback `main`).  
5. **Pulizia finale**  
   - *«Eseguire il cleanup?»* (default **Sì**). Elimina file temporanei/backup e ferma eventuale preview rimasta attiva.

**Dettagli tecnici anteprima**

- Porta: `4000` (cambiabile via prompt o `--port 4000`).  
- Nome container: `honkit_preview_<slug>`.

---

## 4) Comandi rapidi

### Interattivo (consigliato)

```bash
# Setup cliente
py src/pre_onboarding.py

# Onboarding completo (conversione, anteprima, push opzionale, cleanup)
py src/onboarding_full.py
```

### Varianti batch/CI

```bash
# Setup minimale, nessun accesso a servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# Generazione Markdown + auto-skip preview se Docker manca, niente push
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# Con push esplicito
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push
```

> Su Linux/Mac puoi usare `python` invece di `py`.

---

## 5) Log ed Exit Codes

- Log centralizzati in `output/timmy-kb-<slug>/logs/onboarding.log`.
- Nessun `print()` nei moduli; prompt solo negli orchestratori.

**Exit codes (estratto)**

- `0`  → ok  
- `2`  → `ConfigError` (variabili mancanti, slug invalido in batch)  
- `30` → `PreviewError`  
- `40` → `PushError`  

---

## 6) Troubleshooting

- **Docker non installato** → interattivo: domanda se proseguire senza anteprima.  
- **Anteprima non raggiungibile** → verifica porta `4000`, forzare stop con `docker rm -f honkit_preview_<slug>`.  
- **Push fallito** → controlla `GITHUB_TOKEN` e `GIT_DEFAULT_BRANCH`.  
- **Slug non valido** → richiesto reinserimento.  

---

## 7) Policy operative (estratto)

- **Orchestratori** → UX/CLI, prompt e mapping deterministico errori.  
- **Moduli** → azioni tecniche, no prompt.  
- **Sicurezza I/O** → `is_safe_subpath`, scritture atomiche, no segreti nei log.  
- **Coerenza doc/codice** → ogni modifica richiede aggiornamento documentazione.  

---

## 8) FAQ

**Posso usare la preview se Docker non c’è?**  
No. In batch viene saltata; in interattivo puoi proseguire senza.  

**La preview blocca la pipeline?**  
No. È *detached* e si ferma automaticamente.  

**Cosa viene pubblicato su GitHub?**  
Solo i `.md` in `book/` (esclusi i `.bak`).  

**Posso cambiare la porta della preview?**  
Sì: `--port 4000`.  

---

## 9) Log & Redazione

La pipeline usa redazione log centralizzata:

- Modalità (`LOG_REDACTION`):  
  - `auto` (default) → attiva se `ENV` ∈ {prod, production, ci} o `CI=true`, o se presenti credenziali sensibili.  
  - `on` → sempre attiva.  
  - `off` → disattiva.  
- In debug (`log_level=DEBUG`), redazione sempre disattiva.  
- Dati sensibili (token, path credenziali) mascherati.  

Il flag `redact_logs` è calcolato in `ClientContext` e riflesso nei log strutturati.
