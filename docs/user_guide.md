# User Guide — Timmy‑KB (v1.2.2)

Questa guida spiega come usare la pipeline per generare una **KB Markdown AI‑ready** a partire da PDF del cliente, con arricchimento semantico, anteprima HonKit (Docker) e, se desiderato, push su GitHub.

---

## 1) Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima)
- (Solo per pre‑onboarding con Drive) **Credenziali Google** (Service Account JSON)
- (Opz.) **GitHub Token** (`GITHUB_TOKEN`) per il push

### Variabili d’ambiente

Imposta le variabili (via `.env` o ambiente di sistema):

- `SERVICE_ACCOUNT_FILE` → path al JSON del Service Account (solo per Drive)
- `DRIVE_ID` → radice/parent dello spazio Drive (solo per Drive)
- `GITHUB_TOKEN` → necessario solo se vuoi pubblicare su GitHub
- `GIT_DEFAULT_BRANCH` → branch di default per il push (fallback `main`)
- `YAML_STRUCTURE_FILE` → **override opzionale** del file YAML di struttura cartelle usato dal *pre_onboarding* (default `config/cartelle_raw.yaml`)
- `LOG_REDACTION` → `auto` (default), `on`, `off`
- `ENV` → `dev`, `prod`, `ci`, ...
- `CI` → `true`/`false`

---

## 2) Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF locali (fonte unica)
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml
  ├─ config/     # config.yaml (aggiornato con eventuali ID Drive e blocco semantic_tagger)
  └─ logs/       # log centralizzati (pre_onboarding, tag_onboarding, semantic_onboarding, onboarding_full)
```

> Lo **slug** deve rispettare la regex definita in `config/config.yaml`. In interattivo, se non valido ti verrà chiesto di correggerlo.

---

## 3) Flussi operativi

### Modalità interattiva vs CLI

- **Interattiva**: l’utente viene guidato passo passo. Nel pre‑onboarding deve inserire *slug* e nome cliente; in onboarding può confermare/negare l’avvio della preview Docker e del push GitHub. In questa modalità i comandi si lanciano "secchi" (senza parametri), e lo script chiede via prompt i dati mancanti.  
  - Esempi: `py src/pre_onboarding.py` oppure `py src/semantic_onboarding.py`.

- **CLI (batch)**: tutti i parametri vanno passati via opzioni (`--slug`, `--name`, `--no-preview`, `--no-push`, ecc.). Non ci sono prompt ed è pensata per CI/CD o automazioni.  
  - Esempi: `py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive` oppure `py src/semantic_onboarding.py --slug acme --no-preview --non-interactive`.

---

### A) Pre‑onboarding (setup)

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome descrittivo>] [--non-interactive] [--dry-run]
```

**Sequenza tipica**

1. **Slug cliente** → richiesto lo *slug* (es. `acme`). In interattivo, se non valido il sistema chiede un nuovo valore. In CLI puoi fornirlo con `--slug acme` e, opzionalmente, `--name "Cliente ACME"`.
2. **Creazione struttura locale** → genera cartelle `raw/`, `book/`, `config/`, `logs/` e `config.yaml`.
3. **Configurazioni semantiche** → copia `cartelle_raw.yaml` e `default_semantic_mapping.yaml` in `semantic/`, generando `semantic_mapping.yaml` con blocco `semantic_tagger` (valori di default modificabili).
4. **Google Drive (opzionale)**
   - Se configurato: crea/aggiorna la struttura remota e carica `config.yaml`.
   - Se mancano credenziali: in interattivo puoi usare `--dry-run` per restare in locale; in batch l’esecuzione fallisce senza il flag.

> In questa fase non ci sono anteprima né push: serve solo a predisporre l’ambiente.

---

### B) Tagging semantico (HiTL)

```bash
py src/tag_onboarding.py --slug <id>
```

**Sequenza tipica**

1. Copia i PDF da Drive o locale in `raw/`.
2. Genera `semantic/tags_raw.csv` con i candidati tag derivati dai path e dai nomi file.
3. Checkpoint HiTL: in interattivo chiede se proseguire con l’arricchimento semantico; in CLI puoi usare `--proceed`.
4. Se confermato, genera `README_TAGGING.md` e stub `tags_reviewed.yaml`.

---

### C) Semantic Onboarding (conversione + preview)

```bash
py src/semantic_onboarding.py [--slug <id>] [opzioni]
```

**Sequenza tipica**

1. **Conversione PDF → Markdown** → genera `.md` in `book/`.
2. **Arricchimento frontmatter** → integra tags/areas da `tags_reviewed.yaml` e mapping semantico.
3. **README e SUMMARY** → generati in `book/`.
4. **Anteprima HonKit (Docker)**
   - Se Docker disponibile: chiede *«Avviare l’anteprima ora?»*. Lancia la preview e poi chiede *«Chiudere ORA la preview e terminare?»*.
   - Se Docker assente: chiede *«Proseguire senza anteprima?»*.

**Opzioni CLI aggiuntive:**
- `--no-preview` → salta la preview Docker.
- `--preview-port <N>` → porta per la preview (default 4000).

---

### D) Onboarding Full (push)

```bash
py src/onboarding_full.py --slug <id> [opzioni]
```

**Sequenza tipica**

1. **Push GitHub** → pubblica i contenuti della cartella `book/` (commit + push).
2. Richiede `GITHUB_TOKEN` valido.
3. Integrazioni future: collegamento automatico con GitBook.

**Opzioni CLI principali**

- `--no-push` → salta il push GitHub.
- `--force-push` + `--force-ack` → forza il push anche in caso di conflitto.

---

## 4) Comandi rapidi

### Interattivo (consigliato)

```bash
# Setup cliente
py src/pre_onboarding.py

# Tagging semantico
py src/tag_onboarding.py

# Conversione + preview
py src/semantic_onboarding.py

# Push finale
py src/onboarding_full.py
```

### CLI / Batch / CI

```bash
# Setup minimale, solo locale
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive --dry-run

# Tagging
py src/tag_onboarding.py --slug acme --non-interactive

# Generazione book + enrichment, skip preview
py src/semantic_onboarding.py --slug acme --no-preview --non-interactive

# Push GitHub
py src/onboarding_full.py --slug acme --no-push --non-interactive
```

---

## 5) Log ed Exit Codes

- Log centralizzati in `output/timmy-kb-<slug>/logs/`.
- Mascheramento segreti automatico (`LOG_REDACTION`).
- Scritture atomiche e path-safety enforced (`ensure_within`).

**Exit codes (estratto)**

- `0`  → ok
- `2`  → `ConfigError` (slug invalido, variabili mancanti)
- `30` → `PreviewError`
- `40` → `PushError`

---

## 6) Troubleshooting

- **Docker non installato** → interattivo: domanda se proseguire senza anteprima.
- **Anteprima non raggiungibile** → verifica porta `4000`, stop con `docker rm -f gitbook-<slug>`.
- **Push fallito** → controlla `GITHUB_TOKEN` e branch.
- **Slug non valido** → richiesto reinserimento.
- **Tags incoerenti** → assicurati che `tags_raw.csv` e `tags_reviewed.yaml` siano allineati.

---

## 7) Policy operative (estratto)

- **Orchestratori** → UX/CLI, prompt e checkpoint HiTL.
- **Moduli** → azioni tecniche, no prompt.
- **Sicurezza I/O** → `ensure_within`, scritture atomiche via `safe_write_text`/`safe_write_bytes`.
- **Coerenza doc/codice** → ogni modifica richiede aggiornamento documentazione.

---

## 8) FAQ

**Posso usare la preview se Docker non c’è?**  
No. In batch viene saltata; in interattivo puoi proseguire senza.

**La preview blocca la pipeline?**  
No. È *detached* e si può fermare a fine pipeline.

**Cosa viene pubblicato su GitHub?**  
Solo i `.md` in `book/` (esclusi i `.bak`).

**Posso cambiare la porta della preview?**  
Sì: `--preview-port 4000`.

**Come gestire un push con force?**  
Passa `--force-push` e, se richiesto, `--force-ack`.

**Posso lanciare senza variabili di ambiente?**  
Sì, se usi `--non-interactive` e resti in locale (`--dry-run`).

**Devo modificare a mano il mapping semantico?**  
No: in `pre_onboarding` viene già generato con valori di default. Puoi però personalizzare `semantic_mapping.yaml` per cliente.

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

