# 🟦 Pre-Onboarding NeXT – Pipeline v1.3.1

Questa fase serve a **creare la struttura Drive cliente**, pronta per la raccolta documentale e la successiva pipeline di onboarding NeXT/Timmy.

---

## 📍 Scopo e overview

- **Automazione completa** della creazione struttura cartelle su Google Drive per il cliente.
- **Generazione automatica del file `config.yaml`**, usato come base di configurazione per tutta la pipeline.
- **Logging strutturato e centralizzato** (sia su console che su file, con emoji e policy uniforme).
- **Gestione errori explainable & exception-first**: ogni errore bloccante solleva una eccezione custom, con messaggi CLI chiari.
- Input guidato e validazione naming (slug + nome cliente).
- Rollback sicuro: nessuna cartella viene sovrascritta se già esistente.
- Tutta la logica di naming e logging segue [coding_rule.md](./coding_rule.md).

---

## ⚙️ Come si usa

### 1. Esegui il pre-onboarding

py src/pre_onboarding.py
Ti verrà chiesto:

Lo slug cliente (solo minuscole, trattino, no spazi)

Il nome completo del cliente

2. Cosa fa lo script
Connette l’account Google Drive tramite service account.

Cerca la cartella cliente (usando lo slug come nome).

Se esiste già, blocca la procedura con warning.

Crea la cartella root cliente e tutte le sottocartelle tematiche (da YAML di struttura in config/).

Genera e salva localmente il file config.yaml (in output/timmy-kb-<slug>/config/config.yaml).

Carica config.yaml su Google Drive, dentro la cartella root appena creata.

Logga ogni step (successo, warning, errori) su console e su file (logs/pre_onboarding.log), secondo le policy emoji e livelli v1.3.1.

3. Struttura output generata
lua
Copia
Modifica
output/
└── timmy-kb-<slug>/
    ├── config/
    │   └── config.yaml
    └── (cartelle tematiche da YAML)
4. Variabili e dipendenze
Il file .env deve contenere:

DRIVE_ID (ID della root Google Drive da usare)

CARTELLE_RAW_YAML (path YAML con struttura cartelle, default: config/cartelle_raw.yaml)

GOOGLE_SERVICE_ACCOUNT_JSON (default: service_account.json)

Il file config.yaml generato conterrà tutte le informazioni necessarie per le pipeline successive.

🪵 Logging, naming & policy
Ogni operazione viene loggata via logger strutturato (logging_utils.py), policy uniforme su tutta la pipeline.

Logging sia su console che su file (logs/pre_onboarding.log), emoji e livelli standardizzati (INFO, WARNING, ERROR).

Funzioni, file, variabili sempre in snake_case e con nomi descrittivi (no abbreviazioni).

Messaggi CLI chiari ed empatici, distinti dal logging strutturato.

Tutte le policy di coding, logging e testing sono ora formalizzate in coding_rule.md (non più in NAMING_LOGGING_RULES.md).

❗ Novità rispetto alle versioni precedenti
Exception-first: ogni errore critico solleva una eccezione custom, con catch centralizzato e log user-friendly.

Logging centralizzato: ogni step tracciato e facilmente auditabile, emoji e livelli uniformi.

Pipeline più robusta: roll-back, path sicuri, nessuna sovrascrittura accidentale.

Refactor tool CLI incluso (per find & replace e manutenzione batch).

Tutte le regole di test, naming, logging sono centralizzate in coding_rule.md.

📎 Note operative
La procedura va lanciata una sola volta per ogni nuovo cliente.
In caso di errore o rollback, basta rilanciare lo script con lo stesso slug.
Per aggiornamenti e policy consulta sempre il README principale, il CHANGELOG e coding_rule.md.