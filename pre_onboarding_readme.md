
# 🚀 Pre-onboarding Pipeline Timmy-KB (2025+)

## 🎯 Obiettivo

Automatizzare la creazione della struttura base su Google Drive per ogni nuovo cliente, compresa la generazione e validazione della configurazione (`config.yaml`), e l'upload di tutti i file necessari tramite API.

---

## 🗂️ Struttura e moduli coinvolti

```
project-root/
├── config/
│   └── cartelle_raw.yaml       # Struttura cartelle cliente (template)
├── temp_config/
│   └── config.yaml             # Config locale cliente (temporaneo)
├── src/
│   ├── pre_onboarding.py       # Entry-point procedura pre-onboarding
│   └── ingest/
│       ├── config_writer.py
│       ├── drive_utils.py
│       └── validate_structure.py
├── .env                        # Configurazione variabili ambiente
```

---

## ⚙️ Flusso della procedura

1. **Avvio script**
   - Da CLI: `py src/pre_onboarding.py`
   - Richiede solo input interattivo: **slug** e **nome cliente**

2. **Generazione e validazione `config.yaml`**
   - Genera il file di configurazione locale per il cliente.
   - Mostra all’utente il preview, chiede conferma prima dell’upload.

3. **Validazione struttura cartelle**
   - Carica `cartelle_raw.yaml`, verifica che sia una lista di dict con chiave `name`.

4. **Upload su Google Drive**
   - Crea la cartella cliente (`<slug>`) su Drive condiviso.
   - Carica `config.yaml` nella root della cartella cliente.
   - Crea tutte le sottocartelle definite nella struttura.

5. **Rollback e pulizia**
   - Se l’utente annulla o se c’è errore grave, vengono rimossi i file temporanei.

6. **Logging**
   - Tutti i messaggi sono gestiti tramite logging centralizzato (no print).

---

## 🧩 Variabili richieste in `.env`

Prima di eseguire la procedura, assicurati che queste variabili siano valorizzate:

| Variabile                 | Descrizione                                                    |
|---------------------------|----------------------------------------------------------------|
| DRIVE_ID                  | ID del Drive condiviso clienti                                 |
| SERVICE_ACCOUNT_FILE      | Path file credenziali Google API                               |
| CARTELLE_RAW_YAML         | Path file struttura cartelle (`config/cartelle_raw.yaml`)      |
| LOCAL_TEMP_CONFIG_PATH    | Path temporaneo per config locale (`temp_config/config.yaml`)  |
| ...                       | (Altre variabili per portabilità/estensioni)                   |

> **NB:** Consulta il template ufficiale `.env` fornito nel progetto.

---

## 🌐 Note di portabilità

- Tutti i path e gli ID sono parametrizzati tramite variabili `.env`
- La pipeline funziona su Windows, Mac, Linux senza modifiche
- Il logging centralizzato facilita debugging e audit trail

---

## ✅ Output atteso

- Struttura cliente creata su Google Drive, pronta per la fase di onboarding
- File `config.yaml` caricato nella root della cartella cliente

---

## 🛠️ Dipendenze principali

- Python >= 3.10
- `google-api-python-client`, `pyyaml`, `python-dotenv`

---

## 🗒️ Estensioni future

- Template multipli per diverse strutture clienti
- Generazione automatica slug da nome cliente
- Logging avanzato su file rotanti
