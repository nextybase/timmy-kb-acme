# 🚀 Pre-onboarding Pipeline Timmy-KB (v1.2.2)

## 🎯 Obiettivo

Automatizzare la creazione della struttura base su Google Drive per ogni nuovo cliente, compresa la generazione e validazione della configurazione (`config.yaml`), con supporto a rollback, logging strutturato e idempotenza.\
Questa fase fornisce la base solida per tutte le successive procedure di ingest e arricchimento semantico.

---

## ✅ Novità v1.2.2

- 🔁 Check preventivo su esistenza cartella `<slug>` su Drive (idempotente)
- ⚠️ Prompt interattivo per confermare o annullare
- 🧹 Rollback sicuro su errore (eliminazione cartella root su Drive)
- 🧪 Validazione semantica del template `cartelle_raw.yaml`
- 📦 Logging robusto, audit completo e portabilità .env
- ➕ Generazione e upload di `config.yaml` nella cartella `config` del cliente (pronta per la fase di onboarding)

---

## 🗂️ Struttura e moduli coinvolti

```
project-root/
├── config/
│   └── cartelle_raw.yaml
├── temp_config/
│   └── config.yaml
├── src/
│   ├── pre_onboarding.py
│   └── ingest/
│       ├── config_writer.py
│       ├── drive_utils.py
│       └── validate_structure.py
├── .env
```



---

## ⚙️ Flusso della procedura

1. **Avvio**

   - Da CLI: `py src/pre_onboarding.py`
   - Richiede: **slug** e **nome cliente**

2. **Generazione e validazione config**

   - Crea e salva localmente `config.yaml` nella struttura del cliente
   - Preview e conferma manuale prima dell’upload

3. **Validazione YAML struttura cartelle**

   - Controlla la validità di `cartelle_raw.yaml` (deve rappresentare una struttura coerente)

4. **Upload e creazione struttura su Drive**

   - Crea cartella root cliente e sottocartelle secondo YAML
   - Carica `config.yaml` nella sottocartella `config/`

5. **Rollback**

   - In caso di errore, elimina tutta la cartella cliente su Drive

6. **Logging**

   - Logging strutturato su file e console, con livelli INFO/WARNING/ERROR

---

## 📄 Variabili richieste in `.env`

| Variabile                 | Descrizione                                 |
| ------------------------- | ------------------------------------------- |
| DRIVE\_ID                 | ID Drive condiviso clienti                  |
| SERVICE\_ACCOUNT\_FILE    | Path file JSON credenziali Google API       |
| LOCAL\_TEMP\_CONFIG\_PATH | Path locale config temporanea               |
| CARTELLE\_RAW\_YAML       | Path al template struttura cartelle cliente |

---

## ✅ Output atteso

- Struttura cliente completa su Google Drive (`<slug>/raw`, sottocartelle tematiche, ecc.)
- `config.yaml` caricato e validato, pronto per la fase di onboarding

---

## 🌐 Portabilità

- Funziona su Windows/Mac/Linux
- Path e credenziali totalmente parametrizzati
- Logging strutturato e auditabile

---

## 🛠️ Dipendenze

- Python >= 3.10
- `google-api-python-client`, `pyyaml`, `python-dotenv`

---

## 🧭 Estensioni future

- Autogenerazione intelligente slug cliente
- Supporto a batch pre-onboarding
- Profili multipli di struttura cartelle

