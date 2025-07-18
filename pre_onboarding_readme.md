# 🚀 Pre-onboarding Pipeline Timmy-KB (v1.3)

## 🎯 Obiettivo

Automatizzare la creazione della struttura base su Google Drive per ogni nuovo cliente, compresa la generazione e validazione della configurazione (`config.yaml`), con supporto a rollback e idempotenza.

---

## ✅ Novità v1.3

- 🔁 Check se la cartella `<slug>` esiste già su Drive
- ⚠️ Prompt interattivo per confermare o annullare
- 🧹 Rollback completo su Drive in caso di errore a metà
- 🧪 Validazione semantica `cartelle_raw.yaml`
- 📦 Logging robusto, fail-fast, portabilità .env

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
   - `config.yaml` generato localmente
   - Preview e conferma prima dell’upload

3. **Validazione YAML struttura cartelle**
   - Verifica che `cartelle_raw.yaml` contenga lista valida

4. **Upload Drive**
   - Crea cartella cliente solo se non già esistente (o su conferma)
   - Carica `config.yaml`
   - Crea sottocartelle annidate

5. **Rollback**
   - In caso di errore, elimina la cartella root su Drive

6. **Logging**
   - Loggato con `logging` Python, livelli INFO/WARNING/ERROR

---

## 📄 Variabili richieste in `.env`

| Variabile              | Descrizione                                       |
|------------------------|---------------------------------------------------|
| DRIVE_ID               | ID Drive condiviso clienti                        |
| SERVICE_ACCOUNT_FILE   | Path al file JSON con credenziali Google API     |
| LOCAL_TEMP_CONFIG_PATH | Path locale config temporanea                    |
| CARTELLE_RAW_YAML      | Path al template struttura cartelle cliente      |

---

## ✅ Output atteso

- Struttura cliente pronta su Google Drive
- `config.yaml` caricato correttamente

---

## 🌐 Portabilità

- Funziona su Windows / Mac / Linux
- Tutti i path sono parametrizzati
- Logging strutturato, auditabile

---

## 🛠️ Dipendenze

- Python >= 3.10
- `google-api-python-client`, `pyyaml`, `python-dotenv`

---

## 🧭 Estensioni future

- Autogenerazione slug cliente
- Profilazione multipla cartelle
- Supporto a batch onboarding
