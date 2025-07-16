
# 🧪 Documentazione Pre-Onboarding – Timmy KB

## 🎯 Obiettivo

Automatizzare la **creazione delle strutture base** per un nuovo cliente, compresa:
- 📁 Cartella in `clienti/` per la configurazione
- 📁 Cartella su Drive condiviso con struttura predefinita
- 📝 Generazione di un file `config.yaml` temporaneo
- 🔍 **Punto di validazione manuale** per verificare il file di configurazione
- ↩️ **Rollback automatico** in caso di annullamento

---

## 🧱 Struttura dei percorsi coinvolti

```
project-root/
├── config/
│   └── cartelle_raw.yaml ← Struttura delle sottocartelle da creare
├── clienti/
│   └── timmy-kb-<slug>/ ← Configurazione cliente
│       └── config.yaml ← File finale copiato da temporaneo
├── G:/Drive condivisi/Nexty Docs/
│   └── <slug>/ ← Cartella cliente su Google Drive
│       └── raw/ ← Cartella principale per PDF
│           ├── identity/
│           ├── organizzazione/
│           ├── ...
│       └── contrattualistica/
```

---

## ⚙️ Script principale: `src/pre_onboarding.py`

### ✅ Funzioni principali:

1. **Richiesta slug cliente**
   - Input utente: `slug` identificativo (es: `prova`)
   - Input nome cliente (per leggibilità)

2. **Creazione file `config.yaml` temporaneo**
   - Salvato in `temp_config/config.yaml`
   - Contiene solo ID e nome cliente
   - Mostrato a video per revisione

3. **Validazione manuale**
   - Prompt: `✅ Confermi il caricamento su Drive? [y/n]`
   - Se `n`: viene attivato il rollback → eliminazione file

4. **Upload su Google Drive**
   - Autenticazione con `service_account.json`
   - Crea cartella principale con nome `slug`
   - Legge `config/cartelle_raw.yaml` per creare la struttura sottocartelle
   - Carica `config.yaml` nella root della cartella cliente su Drive

---

## 📄 Moduli coinvolti

### `src/pre_onboarding.py`
Controlla il flusso generale, input, validazione e trigger delle funzioni secondarie.

### `utils/config_writer.py`
Contiene:
- `generate_config_yaml()` → genera il dizionario di config
- `write_config()` → scrive su file temporaneo
- `upload_config_to_drive()` → carica `config.yaml` nella cartella Drive

### `utils/drive_utils.py`
Contiene:
- `create_folder()` → crea una singola cartella
- `create_drive_folder_structure()` → legge da `cartelle_raw.yaml` e crea la struttura
- `init_drive_service()` → autenticazione Google Drive API

---

## 🗂️ Struttura da `cartelle_raw.yaml`

Esempio:

```yaml
# config/cartelle_raw.yaml
root_folders:
  - name: raw
    subfolders:
      - identity
      - organizzazione
      - artefatti-operativi
      - glossario
      - best-practices
      - normativa
      - scenario
      - economy
      - template-documenti
  - name: contrattualistica
```

---

## 🧪 Esecuzione

```bash
py src/pre_onboarding.py
```

Prompt:

```
👤 Pre-onboarding Timmy-KB

🔤 Slug cliente (es. prova):
📝 Nome cliente:
✅ Confermi il caricamento su Drive? [y/n]
```

---

## 🛑 Possibili errori gestiti

- Slug vuoto o duplicato
- Permessi insufficienti su Drive
- Errore di autenticazione service_account.json
- Config non confermato → rollback file temporaneo

---

## ✅ Output finale atteso

- 📁 Cartella `G:/Drive condivisi/Nexty Docs/<slug>/` creata con sottostruttura
- 📄 `config.yaml` caricato in Drive
- 💾 Eventuale copia del file finale in `clienti/timmy-kb-<slug>/`

---

## 👥 Destinatari

- Team tecnico o PM per creazione cliente
- Utenti con accesso Drive condiviso Nexty Docs
- Operatori che preparano i documenti per l’onboarding

---

## 🧩 Estensioni previste

- Aggiunta dei campi GitHub/GitBook nella config
- Validazione automatica file .yaml
- Integrazione con procedura onboarding successiva
