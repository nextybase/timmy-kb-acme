# 📚 Documentazione Pipeline Onboarding – Timmy KB (2025, v1.2)

## 🧭 Obiettivo

Automatizzare la generazione, strutturazione semantica, anteprima e pubblicazione di una Knowledge Base partendo da PDF contenuti in una cartella Drive condivisa, per ogni nuovo cliente.  
Tutti i path e i parametri di sistema sono caricati dinamicamente da file `.env` e dalla configurazione del cliente su Drive.

---

## 🆕 Novità v1.2

- ✅ Check anticipato: se la repo GitHub esiste già, chiede all'utente se proseguire o annullare
- 🔁 Fallback sicuro: push solo su repo esistente, evitando errori da duplicazione
- 🔍 Controllo `gh` installata e autenticata prima di procedere
- 🧪 Logging migliorato e pulizia più sicura al termine della pipeline

---

## 🗂️ Struttura base del progetto

```
project-root/
├── config/
│   ├── raw_structure.yaml        # (opz.) Mappa semantica delle tipologie documentali
│   └── cartelle_raw.yaml         # Template struttura cartelle cliente su Drive
├── output/
│   └── timmy_kb_<slug>/          # Output Markdown, JSON, README generati
├── clienti/
│   └── timmy-kb-<slug>/          # (opz.) Config locale cliente (copia)
├── src/
│   ├── ingest/
│   │   ├── config_loader.py
│   │   ├── pdf_to_md.py
│   │   ├── semantic_extractor.py
│   │   ├── build_summary.py
│   │   ├── gitbook_preview.py
│   │   ├── github_push.py
│   │   └── cleanup.py
│   ├── utils/
│   │   └── github_utils.py       # ✅ nuovo modulo helper GitHub
│   └── onboarding_full.py
├── .env
```

---

## ⚙️ Flusso della pipeline (Onboarding)

### 1. ▶️ Avvio pipeline
```bash
py src/onboarding_full.py
```

### 2. 🔍 Check GitHub repo esistente
Subito dopo l'inserimento dello slug, la pipeline verifica se la repo esiste:
- Se esiste → prompt per confermare o annullare
- Se non esiste → prosegue con lo step successivo

### 3. 📥 Download PDF da Google Drive
- Scarica ricorsivamente tutti i PDF da `<slug>/raw`
- Mantiene la struttura delle sottocartelle

### 4. 🧩 Caricamento configurazione
- Carica `config.yaml` dal Drive del cliente
- Integra parametri da `.env`
- Valida consistenza, fallisce se mancano dati essenziali

### 5. 📄 Conversione PDF → Markdown
- Tutti i PDF diventano `.md` salvati in `output/timmy_kb_<slug>/`

### 6. 🧠 Estrazione Semantica
- Genera JSON placeholder (`README.json`, `SUMMARY.json`) per ogni documento

### 7. 📑 Generazione README & SUMMARY
- Crea `README.md` e `SUMMARY.md` compatibili con GitBook/Honkit

### 8. 🧪 Anteprima locale via Docker
- Avvia container Honkit su `localhost:4000`
- L’utente può ispezionare i contenuti prima di procedere

### 9. 🚀 Deploy GitHub
- Prompt interattivo
- Se repo esiste → push solo se confermato
- Altrimenti → crea repo con `gh repo create`

### 10. 🧹 Cleanup finale
- Chiede conferma prima della rimozione
- Cancella solo se directory è quella attesa

---

## ✅ Risultati Finali

- File Markdown e JSON strutturati
- README e SUMMARY pronti per GitBook
- Repo GitHub aggiornata
- Preview Docker verificata
- Logging trasparente

---

## 🛠️ Requisiti tecnici

| Componente     | Requisito                                               |
|----------------|----------------------------------------------------------|
| Python         | >= 3.10                                                  |
| Librerie       | PyMuPDF, spacy, pydantic, pyyaml, slugify, google-api-python-client, docker, requests |
| Docker         | Per preview Honkit/GitBook                               |
| GitHub CLI     | `gh` autenticato                                         |
| Google Drive   | Service Account configurato (.env)                       |

---

## ⚡ Sicurezza & portabilità

- Tutti i path e parametri sono centralizzati in `.env`
- Compatibile con sistemi Windows / Linux
- Logging strutturato
- Nessuna credenziale sensibile è committata

---

## 🧭 Estensioni previste

- Attivazione GitHub Pages automatica post-push
- Modalità `--yes` per CI/CD
- Logging avanzato su file
- Supporto altri formati oltre PDF
