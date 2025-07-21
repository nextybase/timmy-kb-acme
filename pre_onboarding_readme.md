# 🟦 Pre-Onboarding NeXT – Pipeline v1.2.3

Questa fase serve a **creare la struttura Drive cliente**, pronta per la raccolta documentale e la successiva pipeline di onboarding NeXT.

---

## 📍 Scopo e overview

- **Automazione completa** della creazione struttura cartelle su Google Drive per il cliente.
- **Generazione automatica del file `config.yaml`**, usato come base di configurazione per tutta la pipeline.
- **Logging strutturato** e validazione a ogni step.
- Input guidato e validazione naming (slug + nome cliente).
- Rollback sicuro: nessuna cartella viene sovrascritta se già esistente.

---

## ⚙️ Come si usa

### 1. Esegui il pre-onboarding

```bash
py src/pre_onboarding.py
```
Ti verrà chiesto:

- Lo slug cliente (solo minuscole, trattino, no spazi)
- Il nome completo del cliente

---

### 2. Cosa fa lo script

- Connette l’account Google Drive tramite service account.
- Cerca la cartella cliente (usando lo slug come nome).
- Se esiste già, blocca la procedura con warning.
- Crea la cartella root cliente e tutte le sottocartelle tematiche (da YAML di struttura in config/).
- Genera e salva localmente il file config.yaml (in output/timmy-kb-<slug>/config/config.yaml).
- Carica config.yaml su Google Drive, dentro la cartella root appena creata.
- Logga ogni step (successo, warning, errori) su console e su file (logs/pre_onboarding.log).

---

### 3. Struttura output generata

```
output/
└── timmy-kb-<slug>/
    ├── config/
    │   └── config.yaml
    └── (cartelle tematiche da YAML)
```

---

### 4. Variabili e dipendenze

Il file `.env` deve contenere:

- DRIVE_ID (ID della root Google Drive da usare)
- CARTELLE_RAW_YAML (path YAML con struttura cartelle, default: config/cartelle_raw.yaml)
- GOOGLE_SERVICE_ACCOUNT_JSON (default: service_account.json)

Il file config.yaml generato conterrà tutte le informazioni necessarie per le pipeline successive.

---

## 🪵 Logging e naming

Ogni operazione viene loggata via funzione `get_structured_logger` dal modulo logging_utils.py.  
Logging su console e su file.  
Funzioni, file, variabili sempre in snake_case e con nomi descrittivi (no abbreviazioni).  
Messaggi CLI chiari e “empathic”, differenziati da logging strutturato.

---

## ❗ Novità rispetto alle versioni precedenti

- Refactor naming: tutte le funzioni e i file seguono la nuova naming rule (vedi NAMING_LOGGING_RULES.md).
- Logging centralizzato: ogni step tracciato e facilmente auditabile.
- Pipeline più robusta: roll-back, path sicuri, nessuna sovrascrittura accidentale.

---

## 📎 Note operative

La procedura va lanciata una sola volta per ogni nuovo cliente.  
In caso di errore o rollback, basta rilanciare lo script con lo stesso slug.  
Per aggiornamenti, consulta anche il README principale e il CHANGELOG.
