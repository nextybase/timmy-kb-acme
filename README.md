# Timmy-KB – Knowledge Base Onboarding Pipeline (v1.0)

---

Pipeline modulare e automatizzata per l’onboarding strutturato di PMI nella piattaforma NeXT, con generazione di knowledge base in Markdown semantico e pubblicazione continua su GitHub/GitBook.

## 📜 Filosofia e Obiettivi

Timmy-KB fornisce un flusso completo, dal recupero dei materiali grezzi (PDF) fino alla generazione, revisione e distribuzione della knowledge base. Il progetto integra le best practice del **modello NeXT** e supporta sia esecuzioni automatiche che modalità interattive, garantendo:

- **Riproducibilità**: flussi chiari, parametrizzabili e documentati.
- **Automazione end-to-end**: gestione cartelle Drive, conversione, generazione, preview e push.
- **Flessibilità**: CLI parametrica e modalità interattiva.
- **Output standardizzato**: struttura coerente e semantica.
- **Compatibilità multi-target**: GitHub per versionamento, GitBook per fruizione web.

## 🎯 Funzionalità chiave

- Gestione sicura di cartelle e file su Google Drive (controlli path). 
- Conversione PDF → Markdown strutturato.
- Generazione automatica di **SUMMARY.md** e **README.md**.
- Anteprima locale con **Honkit/Docker** con stop controllato.
- Push automatico su GitHub (solo file `.md` della cartella `book`).
- Modalità **interattiva** e **batch**.
- Gestione configurazioni cliente tramite YAML.

## 🛠 Architettura

### Orchestratori

- `` – Prepara configurazioni cliente, crea struttura cartelle di output, valida requisiti minimi, verifica dipendenze. Supporta modalità interattiva e CLI.
- `` – Esegue onboarding completo: caricamento configurazioni, gestione cartelle Drive, conversione in Markdown, generazione documenti, anteprima GitBook in interattivo, push GitHub. Implementa controlli di sicurezza e gestione eccezioni.

### Moduli `src/pipeline/`

- `cleanup_utils.py` – Pulizia e riorganizzazione file/cartelle di output.
- `config_utils.py` – Gestione configurazioni YAML, backup e update.
- `constants.py` – Costanti globali.
- `content_utils.py` – Conversione PDF → MD, generazione SUMMARY e README.
- `context.py` – Contesto cliente (path, settings, variabili).
- `drive_utils.py` – Gestione cartelle su Google Drive e download sicuro.
- `env_utils.py` – Caricamento e validazione variabili `.env`.
- `exceptions.py` – Eccezioni specifiche pipeline.
- `gitbook_preview.py` – Gestione anteprima GitBook in Docker con stop controllato.
- `github_utils.py` – Push `.md` su GitHub con creazione repo.
- `logging_utils.py` – Logging strutturato.
- `path_utils.py` – Verifica path sicuri e gestione sottocartelle.

### Altri moduli

- `` – (in costruzione) Logica semantica per categorizzazione contenuti.
- `` – Script ausiliari (`gen_dummy_kb.py` per generazione dati fittizi).

## ⚙️ Configurazione

Variabili gestite tramite `.env` e `env_utils.py`:

```env
DRIVE_ID=...
SERVICE_ACCOUNT_FILE=...
BASE_DRIVE=...
GITHUB_TOKEN=...
GITBOOK_TOKEN=...
```

> **Nota:** `GITHUB_ORG` non richiesto; gestione interna.

## 🚀 Esecuzione

```bash
python src/onboarding_full.py               # Interattivo
python src/onboarding_full.py --slug acme-srl --no-drive   # Batch
```

## 🧪 Testing

- Test unitari in `tests/`
- Modalità batch per test senza input
- Generazione dati dummy con `gen_dummy_kb.py`

## 📦 Output

Output in `output/timmy-kb-<slug>/book/` conforme alla struttura YAML.

## 📐 Regole di sviluppo

Definite in `coding_rules.md`: naming, struttura moduli, formattazione e linee guida di coerenza.

