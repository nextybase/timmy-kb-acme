# User Guide — Timmy‑KB (v1.0.3 Stable)

Questa guida spiega come usare la pipeline per generare una **KB Markdown AI‑ready** a partire da PDF del cliente, con anteprima HonKit (Docker) e, se vuoi, push su GitHub.

> Nota: i micro‑fix introdotti (preview *detached* con **stop automatico** in uscita, logging centralizzato, cache regex slug) sono già riflessi qui. Il bump versione verrà finalizzato nel `CHANGELOG.md` quando chiudiamo il giro.

---

## 1) Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima; se assente la preview viene *auto‑skip* in batch)
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

### A) Pre‑onboarding (setup)
Crea la struttura locale per il cliente e, se vuoi, prepara/aggiorna la struttura su Drive.

**Esempi**
```bash
# Setup minimale, nessun accesso a servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# Setup con Drive (richiede variabili d'ambiente corrette)
py src/pre_onboarding.py --slug acme
```

**Cosa fa**
1. Inizializza cartelle `raw/`, `book/`, `config/`, `logs/`.
2. Crea o aggiorna `config.yaml` (con backup `.bak`).
3. (Opz.) Su Drive: crea cartelle e allinea struttura secondo configurazione.

---

### B) Onboarding completo
Converte i PDF in Markdown, genera `SUMMARY.md`/`README.md`, avvia l’anteprima (se Docker presente) e può pubblicare su GitHub.

**Esempi**
```bash
# Batch/CI: nessun prompt, preview saltata se Docker non c'è, push disabilitato
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# Interattivo: se Docker assente ti chiede se proseguire; chiede conferma push
py src/onboarding_full.py --slug acme --no-drive
```

**Comportamento anteprima**
- Se **Docker presente** → build + serve **in modalità _detached_** (non blocca).  
  L’orchestratore ferma **automaticamente** il container al termine dell’esecuzione.
- Se **Docker assente** →
  - in `--non-interactive`: **auto‑skip**;
  - in interattivo: domanda “proseguire senza anteprima?” (default **NO**).

**Porta e container**
- Porta: `4000` (override: `--port 4000`)
- Container: `honkit_preview_<slug>`

**Comportamento push**
- Richiede `GITHUB_TOKEN`.
- Branch letto da `GIT_DEFAULT_BRANCH` (fallback `main`).
- In `--non-interactive` il push **non avviene** salvo `--push` esplicito.
- In interattivo viene chiesto se eseguire il push (default **NO**).

---

## 4) Comandi rapidi (che coprono il 90% dei casi)

```bash
# 1) Setup locale senza toccare servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# 2) Generazione Markdown + anteprima (se Docker c'è), niente push
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# 3) Come sopra ma con push esplicito (batch)
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

La mappatura completa è nella documentazione tecnica.

---

## 6) Troubleshooting

- **Docker non installato**  
  - Batch: la preview viene saltata automaticamente.  
  - Interattivo: ti verrà chiesto se proseguire senza anteprima.

- **Anteprima non raggiungibile**  
  - Verifica che la porta `4000` sia libera.  
  - Il container ha nome `honkit_preview_<slug>`: puoi fermarlo con `docker rm -f honkit_preview_<slug>`.

- **Push fallito**  
  - Controlla `GITHUB_TOKEN`.  
  - Verifica il branch in `GIT_DEFAULT_BRANCH` (altrimenti usa `main`).

- **Slug non valido**  
  - In batch: errore.  
  - In interattivo: ti verrà chiesto di reinserirlo.

---

## 7) Policy operative (estratto)

- **Orchestratori** → UX/CLI, prompt e mapping deterministico degli errori.
- **Moduli** → azioni tecniche, **niente `input()`/`sys.exit()`**.
- **Sicurezza I/O** → `is_safe_subpath`, scritture atomiche, nessun segreto nei log.
- **Coerenza doc/codice** → ogni modifica di comportamento comporta aggiornamento della documentazione.

---

## 8) FAQ

**Posso usare la preview se Docker non c’è?**  
No. In batch verrà saltata; in interattivo puoi scegliere se proseguire senza anteprima.

**La preview blocca la pipeline?**  
No. Viene avviata *detached* e l’orchestratore la **ferma automaticamente** alla fine.

**Cosa viene pubblicato su GitHub?**  
Solo i `.md` sotto `book/` (i `.bak` sono esclusi).

**Posso cambiare la porta della preview?**  
Sì: `--port 4000`.
