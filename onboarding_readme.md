
# 📚 Documentazione Pipeline Onboarding – Timmy KB

## 🧭 Obiettivo

Automatizzare la generazione, strutturazione semantica, anteprima e pubblicazione di una Knowledge Base partendo da PDF contenuti in una cartella Drive condivisa.

---

## 🗂️ Struttura base del progetto

```
project-root/
├── config/
│   └── raw_structure.yaml # Mappa semantica delle cartelle in Drive
├── output/
│   └── timmy_kb_<slug>/ # Output Markdown + JSON generati
├── clienti/
│   └── timmy-kb-<slug>/ # Config locale cliente (copia)
├── src/
│   ├── ingest/
│   │   ├── config_loader.py # Carica e valida config.yaml
│   │   ├── pdf_to_md.py # Estrae testo + semantica da PDF
│   │   ├── semantic_extractor.py # Estrai entità e relazioni semantiche
│   │   ├── build_summary.py # Genera README.md e SUMMARY.md
│   │   ├── gitbook_preview.py # Preview locale GitBook con Docker
│   │   ├── github_push.py # Push su GitHub (da template)
│   ├── utils/
│   │   ├── cleanup.py # Pulizia temporanea in caso di annullamento
│   │   └── cleanup_repo.py # Pulizia completa repo e cliente
│   └── onboarding_full.py # Entry-point principale
```

---

## ⚙️ Flusso completo della pipeline

### 1. ▶️ Avvio

```bash
py src/onboarding_full.py <slug_cliente>
# Esempio:
py src/onboarding_full.py prova
```

Il parametro `<slug_cliente>` punta a:

```
G:/Drive condivisi/Nexty Docs/<slug>/config.yaml
```

---

### 2. 🧩 Caricamento Configurazione
📄 Modulo: `config_loader.py`

✔ Azioni:
- Carica `config.yaml` da Drive
- Valida i campi con `pydantic`
- Espande i path `drive_input_path` e `md_output_path`

---

### 3. 🧠 Lettura struttura semantica
📄 File: `config/raw_structure.yaml`

✔ Azioni:
- Mappa semantica delle cartelle Drive
- Utilizzata per etichettare i documenti

📌 Esempio:

```yaml
normativa:
  descrizione: "Norme e requisiti"
  tipo_contenuto: ["legge", "regolamento"]
  entita_rilevanti: ["ente", "requisito"]
```

---

### 4. 📄 Conversione PDF → Markdown semantico
📄 Modulo: `pdf_to_md.py`

✔ Azioni per ogni PDF:
- Estrazione testo (con `PyMuPDF`)
- Riconoscimento immagini
- Titoli tramite NLP (`spacy`)
- Estrazione semantica con:
  - `estrai_entita()`
  - `estrai_relazioni()`
  - `arricchisci_entita_con_contesto()`

📂 Output esempio:

```
output/timmy_kb_<slug>/
├── Documento.md
└── Documento.json
```

---

### 5. 🧱 Generazione Sommario GitBook
📄 Modulo: `build_summary.py`

✔ Azioni:
- Genera `README.md` e `SUMMARY.md`
- Organizza la navigazione GitBook

---

### 6. 🧪 Anteprima GitBook via Docker
📄 Modulo: `gitbook_preview.py`

✔ Azioni:
- Avvia container Docker su `output/timmy_kb_<slug>`
- Anteprima disponibile su `localhost:4000`
- Prompt: "Procedere con deploy?"

---

### 7. 🚀 Deploy GitHub
📄 Modulo: `github_push.py`

✔ Azioni:
- Verifica repo con GitHub CLI
- Crea repo se non esiste (da template)
- Clona e copia contenuti
- `git add`, `commit` e `push`

---

### 8. 🧹 Pulizia temporanea (opzionale)
📄 Modulo: `cleanup.py`

✔ Azioni:
- Se l’utente annulla il deploy, svuota `output/`

---

### 9. 🔥 Pulizia completa cliente (manuale)
📄 Modulo: `cleanup_repo.py`

✔ Azioni:
- Elimina:
  - `clienti/timmy-kb-<slug>`
  - `output/timmy_kb_<slug>`
  - Repo GitHub (`gh repo delete`)
  - `book.json` se presente

---

## ✅ Risultati Finali

- `.md` con semantica, immagini e struttura
- `.json` strutturati per analisi entità/relazioni
- GitBook locale per revisione
- Repo GitHub generata e aggiornata
- Logging dettagliato automatico

---

## 🛠️ Requisiti tecnici

| Componente      | Requisito                               |
|----------------|------------------------------------------|
| Python          | >= 3.10                                  |
| Librerie Python | fitz, spacy, pydantic, pyyaml, slugify  |
| Docker          | Per preview GitBook                     |
| GitHub CLI      | `gh` per creare/push repo               |
| Google Drive    | Sincronizzato in `G:/Drive condivisi/...` |

---

## 🧑‍💻 Note di sviluppo

- I moduli `semantic_extractor.py` e `raw_structure.yaml` permettono evoluzione semantica
- Tutti i moduli sono documentati con docstring
- Il sistema è progettato per essere riusabile per più clienti
