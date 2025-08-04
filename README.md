# Timmy-KB – Onboarding Pipeline v1.0

---

# Timmy-KB: Knowledge Base Onboarding Pipeline (v1.0)

Pipeline modulare, automatizzata e AI-ready per l’onboarding strutturato di PMI nella piattaforma NeXT (Nested eXtreme Timeline), con generazione semantica di knowledge base in Markdown e pubblicazione continua su GitHub/GitBook.

## 🧠 Filosofia e Obiettivi dell’Onboarding

La fase di **onboarding** della pipeline Timmy-KB è *propedeutica* alla successiva creazione della knowledge base semantica tramite AI. Questa fase NON prevede inferenze se non strettamente controllate e limita al minimo le deduzioni euristiche o le automazioni intelligenti:  
**la semantica deve essere dichiarata, non dedotta**.

**Obiettivo principale:**  
> Costruire una base dati solida, tracciabile e completamente esplicita, in cui ogni informazione, tag, relazione e categoria sia definita tramite regole, configurazioni e mapping YAML forniti a monte.

- Il parsing e la strutturazione sono lineari, sostanzialmente deterministici e auditabili: ogni dato trasformato o marcato semanticamente segue policy e mapping ufficiali. 
- Nessuna inferenza automatica viene applicata senza specifico controllo HiTL: la pipeline non “indovina” e raggruppa o classifica in modo euristico soltanto con palese approvazione umana.
- Tutta la semantica e le relazioni sono **forti**, *dichiarate*, e mai deboli o “implicite”.

**Solo con questa base rigorosa sarà possibile, nella fase di creazione AI del prototipo Timmy,  
sviluppare un database relazionale semantico e un knowledge graph realmente affidabili e flessibili.**

---


> Questa versione implementa la **separazione netta tra pipeline di produzione, orchestrazione e logica semantica**, secondo i principi del modello NeXT.

---

## 🎯 Scopo

- Automatizzare onboarding documentale e operativo per PMI/organizzazioni in ecosistemi NeXT
- Generare una **Knowledge Base** semantica, normalizzata e compatibile con la fase uccessiva (CreateTimmy)
- Garantire **separazione tra orchestrazione e semantica**: la pipeline opera come layer tecnico, la semantica come layer autonomo
- Centralizzare configurazione e logging per massimo controllo e auditabilità
- Consentire test end-to-end, preview locale (Docker/Honkit), e deploy automatico su GitHub

### Documentazione chiave della pipeline Timmy-KB

| **[onboarding_readme.md](onboarding_readme.md)**   | **README operativo**: guida step-by-step a pipeline, onboarding, deploy e strumenti. Usare per ogni primo setup o revisione processo.                    |
| **[coding_rules.md](coding_rules.md)**             | **Regole di coding**: naming convention, policy di logging, test, organizzazione repo e naming file/folder. Fonte di verità obbligatoria per sviluppo.      |
| **[manifesto_tecnico.md](manifesto_tecnico.md)**   | **Manifesto tecnico**: principi architetturali e semantici NeXT, separation of concerns, scelte di design, envelope epistemico, roadmap e visione futura.  |

> **Consulta sempre questi file prima di modificare la pipeline o aprire nuove PR.**  
> Per bug/anomalie, apri issue su GitHub allegando log e dettagli.


---

## 🧩 Architettura (overview)

- **Pipeline modulare**: separazione chiara tra moduli di pipeline (`src/pipeline/`), semantica (`src/semantic/`) e strumenti (`src/tools/`)
- **Orchestratori**: file root (`src/pre_onboarding.py`, `src/onboarding_full.py`) gestiscono tutto il flusso e coordinano pipeline + semantica
- **Configurazione centralizzata**: tutte le variabili sono gestite via `.env` e moduli `config_utils.py`
- **Onboarding idempotente, a step**:
    - Pre-onboarding (setup ambiente, Drive, config)
    - Onboarding completo (download, conversione, enrichment semantico, preview, deploy)
- **Output knowledge base**: tutti i Markdown generati sono raccolti in `output/book/`, pronti per la pubblicazione (“flat output”)
- **Preview locale e deploy continuo**: preview via Docker/Honkit, push GitHub solo della KB definitiva

## 🏗️ Struttura delle cartelle

project-root/
├── output/
│ └── timmy-kb-<slug>/
│ ├── raw/ # PDF originali da Drive
│ ├── book/ # Markdown generati (KB pulita)
│ └── config/ # File di configurazione cliente
├── src/
│ ├── pipeline/ # Moduli tecnici della pipeline
│ ├── semantic/ # Funzioni di arricchimento e mappatura semantica
│ └── tools/ # Strumenti di supporto, refactor, validazione repo, dummy KB
├── tests/
│ └── ... # Test unitari, E2E, test semantici
├── logs/
│ └── ... # Log strutturati e di processo
└── .env # Configurazione centralizzata


## ⚙️ Prerequisiti

- Python 3.10+
- Docker (per preview locale, Honkit)
- Account Google Drive + service account JSON
- Token GitHub con permessi repo
- Variabili configurate in `.env` (vedi sotto)

## ⚡ Setup rapido

1. **Clona il repository e installa le dipendenze**
2. **Configura `.env`** (esempio):

    DRIVE_ID=...
    GOOGLE_SERVICE_ACCOUNT_JSON=...
    GITHUB_ORG=nextybase
    GITHUB_TOKEN=...
    ```
3. **Esegui il pre-onboarding:**

    python src/pre_onboarding.py
    ```
   Segui i prompt CLI per slug/nome cliente. Verrà creata la struttura di partenza e il file `config.yaml` cliente.
4. **Popola la cartella Drive** con i PDF richiesti.
5. **Esegui l’onboarding completo:**

    python src/onboarding_full.py
    ```
   La pipeline effettuerà download, conversione, enrichment semantico, preview, e deploy GitHub della KB.

## 🧪 Test e strumenti di sviluppo

- **Test end-to-end**: `tests/test_end2end.py` copre l’intero flusso di onboarding e deploy.
- **Generazione dummy KB**: `src/tools/gen_dummy_kb.py` crea dataset/test dummy per sviluppo e validazione.
- **Cleanup completo**: `src/tools/cleanup_repo.py` elimina tutte le risorse/test di un cliente o ambiente.
- **Refactor & validazione**: `src/tools/refactor_tool.py` e `src/tools/validate_structure.py` mantengono la codebase conforme a regole aziendali e modularità.

## 🪵 Logging e debug

- Logging centralizzato in tutti i moduli (`logs/`)
- Ogni funzione semantica/tecnica deve loggare input/output ed errori, mai scrivere output direttamente fuori dai layer orchestrati
- In caso di errori bloccanti/config errata, la pipeline si interrompe e avvisa l’utente

## 📝 Changelog sintetico

- **v1.0** (2025-08): Pubblicazione applicativo base, solo pipeline, semantica da strutturare.


## 📚 Documentazione e principi

- **Regole di coding**: [coding_rule.md](coding_rule.md) — naming, logging, modularità, test (obbligatorio seguirlo!)
- **Manifesto tecnico**: [manifesto_tecnico.md](manifesto_tecnico.md) — principi semantici, architetturali, NeXT, separation of concerns
- **Best practice pipeline**: vedere PDF “Best practices per pipeline Python” (lezioni da Kedro, Airflow, Luigi)
- **Modello di orchestrazione**: Paper NeXT, focus su modularità, explainability, envelope epistemico
- **Roadmap**: milestones e step in ProgettoRoadmap1_3.pdf (se disponibile)

---

### 🟢 Segui sempre la documentazione e le regole di coding aziendali.  
**Per bug o anomalie**, apri issue su GitHub allegando log e dettagli.

