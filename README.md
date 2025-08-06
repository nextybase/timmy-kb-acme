# Timmy-KB – Knowledge Base Onboarding Pipeline (v1.0)

---

Pipeline modulare e automatizzata per l’onboarding strutturato di PMI nella piattaforma NeXT, con generazione di knowledge base in Markdown semantico e pubblicazione continua su GitHub/GitBook.

## 🧠 Filosofia e Obiettivi

La pipeline Timmy-KB garantisce che ogni informazione, tag, relazione e categoria sia esplicitamente dichiarata e tracciabile, secondo policy e mapping YAML forniti a monte. Nessuna inferenza automatica viene applicata senza controllo: la semantica è sempre dichiarata, non dedotta.

- Parsing e strutturazione deterministici e auditabili
- Semantica e relazioni forti, sempre definite da configurazione
- Ideale per generare database relazionali e knowledge graph affidabili

## 🎯 Scopo

- Automatizzare onboarding documentale e operativo per organizzazioni in ecosistemi NeXT
- Generare una Knowledge Base semantica e normalizzata, pronta per le successive fasi AI
- Separare orchestrazione e semantica, mantenendo la pipeline come layer tecnico
- Centralizzare configurazione e logging per massimo controllo
- Supportare preview locale (Docker/Honkit), test end-to-end e deploy automatico

## 🧩 Architettura (overview)

- **Pipeline modulare**: separazione tra moduli tecnici (`src/pipeline/`), semantici (`src/semantic/`), e strumenti (`src/tools/`)
- **Orchestratori CLI-ready**: orchestratori root (`src/pre_onboarding.py`, `src/onboarding_full.py`) gestiscono tutto il flusso e sono utilizzabili sia in modalità manuale (con input guidato) che automatica (parametri CLI)
- **Configurazione centralizzata**: variabili d’ambiente e YAML gestiti da moduli dedicati
- **Output knowledge base**: Markdown generati raccolti in `output/book/`, pronti per deploy
- **Logging strutturato**: ogni step loggato su file/console tramite logger dedicato

## 🏗️ Struttura cartelle principale

```
project-root/
├── output/
│   └── timmy-kb-<slug>/
│       ├── raw/           # PDF originali da Drive
│       ├── book/          # Markdown generati
│       └── config/        # File di configurazione cliente
├── src/
│   ├── pipeline/          # Moduli tecnici
│   ├── semantic/          # Funzioni semantiche
│   └── tools/             # Strumenti di supporto e dummy KB
├── tests/                 # Test unitari ed E2E
├── logs/                  # Log strutturati
└── .env                   # Configurazione centralizzata
```

## ⚙️ Prerequisiti

- Python 3.10+
- Docker
- Account Google Drive + service account JSON
- Token GitHub con permessi repo
- Variabili configurate in `.env`

## 🚦 Quickstart

1. **Clona il repository e installa le dipendenze**
2. \*\*Configura \*\*\`\` (vedi esempio nel repo)
3. **Esegui il pre-onboarding:**
   ```bash
   python src/pre_onboarding.py
   ```
   Segui i prompt per slug/nome cliente oppure usa i parametri CLI (`--slug`, `--client-name`, `--no-interactive`)
4. **Popola la cartella Drive** con i PDF richiesti
5. **Esegui onboarding completo:**
   ```bash
   python src/onboarding_full.py
   ```
   Usa i flag CLI per modalità automatica (`--slug`, `--auto-push`, `--skip-preview`, `--no-interactive`), oppure interagisci guidato

## 🧪 Testing e Dummy Data

Tutti i dati di test sono generati tramite:

```bash
python src/tools/gen_dummy_kb.py
```

- Slug di test: sempre `dummy`
- Output test separato da dati reali (`output/timmy-kb-dummy/`)
- Tutti i test (`tests/`) sono idempotenti, batch/manuale friendly e automatizzati
- In modalità batch (`BATCH_TEST=1 pytest tests/`): nessun input richiesto, cleanup automatico

## 📦 Funzioni principali e CLI orchestratori

Gli orchestratori supportano:

- `--slug`: slug del cliente
- `--client-name`: nome cliente (pre-onboarding)
- `--no-interactive`: disabilita input (solo batch/CI)
- `--auto-push`: push GitHub automatico senza conferma
- `--skip-preview`: salta preview Honkit/Docker

Tutti i parametri possono essere combinati per workflow automatici. In assenza, il tool guida l’utente passo-passo.

## 🪵 Logging e Debug

- Log sempre su file in `logs/` e in console
- Debug e errori tracciati da logger strutturato, mai via print
- Ogni funzione tecnica/semantica deve loggare input/output/errore

## 📝 Policy, regole e documentazione

- **Regole di coding**: [coding\_rule.md](coding_rule.md)
- **Manifesto tecnico**: [manifesto\_tecnico.md](manifesto_tecnico.md)
- **Best practice pipeline**: PDF “Best practices per pipeline Python” (Kedro, Airflow, Luigi)
- **Modello NeXT**: Paper NeXT allegato

Consulta sempre questi file PRIMA di modificare la pipeline o aprire PR.

---

**Per bug/anomalie, apri issue su GitHub allegando log e dettagli.**

