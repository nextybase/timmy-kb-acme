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

### A) Pre‑onboarding (setup) — **flusso interattivo di base**

Esegui semplicemente:

```bash
py src/pre_onboarding.py
```

**Sequenza di interazioni tipica**

1. **Slug cliente** → ti viene chiesto lo *slug* (es. `acme`). Se non valido, il sistema spiega il motivo e richiede un nuovo valore.
2. **Creazione struttura locale** → conferma della creazione cartelle `raw/`, `book/`, `config/`, `logs/` e del file `config.yaml` (con backup `.bak` in caso di aggiornamento).
3. **Google Drive (opzionale)**
   - Se le variabili sono presenti, ti viene mostrato l’ID rilevato e chiesto se vuoi **creare/aggiornare** la struttura su Drive.
   - Se mancano credenziali, ti viene chiesto se **procedere senza Drive**.
4. **Riepilogo** → stampa un breve riepilogo delle azioni eseguite e dove trovare i file.

> Nota: in questa fase non c’è nessuna anteprima né push. Serve solo a preparare l’ambiente del cliente.

---

### B) Onboarding completo — **flusso interattivo di base**

Esegui semplicemente:

```bash
py src/onboarding_full.py
```

**Sequenza di interazioni tipica**

1. **Slug cliente** → viene richiesto lo *slug*; se non valido, il sistema spiega il motivo e richiede un nuovo valore.
2. **Conversione PDF → Markdown** → parte senza prompt, con log di avanzamento; al termine vengono generati `SUMMARY.md` e `README.md` sotto `book/`.
3. **Anteprima HonKit (Docker)**
   - Se Docker è **presente**: *«Avviare l’anteprima ora?»* (default **Sì**). Se confermi, la preview parte in modalità **detached**; non blocca la pipeline e al termine viene **fermata automaticamente**.
   - Se Docker è **assente**: *«Proseguire senza anteprima?»* (default **No**). Se scegli **Sì**, la pipeline continua senza preview.
4. **Pubblicazione su GitHub (opzionale)**
   - *«Eseguire il push su GitHub?»* (default **No**). Se **Sì**, verifica `GITHUB_TOKEN` e propone il branch di default (da `GIT_DEFAULT_BRANCH`, fallback `main`), consentendo di confermarlo o cambiarlo.
5. **Pulizia finale**
   - *«Eseguire il cleanup?»* (default **Sì**): rimozione di file temporanei/backup non necessari e verifica che la preview non sia più attiva. Se per qualche motivo la preview risultasse ancora in esecuzione, viene proposta la chiusura.

**Dettagli tecnici anteprima**

- Porta: `4000` (puoi cambiarla quando richiesto o passando `--port 4000`).
- Nome container: `honkit_preview_<slug>`.

---

## 4) Comandi rapidi

### Flusso consigliato (interattivo)

```bash
# 1) Setup cliente
py src/pre_onboarding.py

# 2) Onboarding completo (conversione, anteprima, push opzionale, cleanup)
py src/onboarding_full.py
```

### Varianti batch/CI (senza prompt)

```bash
# Setup minimale, nessun accesso a servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# Generazione Markdown + (auto-skip preview se Docker non c'è), niente push
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# Con push esplicito
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push
```

> Su Linux/Mac puoi usare `python` invece di `py` se preferisci.

---

## 5) Log ed Exit Codes

- Tutti i log vanno in `output/timmy-kb-<slug>/logs/onboarding.log`.
- Nessun `print()` nei moduli; prompt solo dove previsto negli orchestratori.

**Exit codes (estratto)**

- `0`  → ok
- `2`  → `ConfigError` (es. variabili mancanti, slug invalido in batch)
- `30` → `PreviewError`
- `40` → `PushError`

---

## 6) Troubleshooting

- **Docker non installato**  → interattivo: domanda se proseguire senza anteprima.
- **Anteprima non raggiungibile**  → verifica che la porta `4000` sia libera, puoi forzare stop con `docker rm -f honkit_preview_<slug>`.
- **Push fallito** → controlla `GITHUB_TOKEN` e `GIT_DEFAULT_BRANCH`.
- **Slug non valido** → viene chiesto di reinserirlo.

---

## 7) Policy operative (estratto)

- **Orchestratori** → UX/CLI, prompt e mapping deterministico degli errori.
- **Moduli** → azioni tecniche, **niente **``**/**``.
- **Sicurezza I/O** → `is_safe_subpath`, scritture atomiche, nessun segreto nei log.
- **Coerenza doc/codice** → ogni modifica di comportamento comporta aggiornamento della documentazione.

---

## 8) FAQ

**Posso usare la preview se Docker non c’è?**\
No. In batch verrà saltata; in interattivo puoi scegliere se proseguire senza anteprima.

**La preview blocca la pipeline?**\
No. Viene avviata *detached* e l’orchestratore la **ferma automaticamente** alla fine.

**Cosa viene pubblicato su GitHub?**\
Solo i `.md` sotto `book/` (i `.bak` sono esclusi).

**Posso cambiare la porta della preview?**\
Sì: `--port 4000`.

---

## 9) Log & Redazione

La pipeline adotta una policy centralizzata di **redazione log**:

- Modalità (`LOG_REDACTION`):
  - `auto` (default) → redazione attiva se `ENV` ∈ {prod, production, ci} o `CI=true`, oppure se presenti credenziali sensibili.
  - `on` → sempre attiva.
  - `off` → sempre disattiva.
- In modalità debug (`log_level=DEBUG`), la redazione è **sempre disattiva**.
- Dati potenzialmente sensibili (es. token, path credenziali) vengono mascherati.

Il flag `redact_logs` è calcolato automaticamente in `ClientContext` e riflesso nei log strutturati.

