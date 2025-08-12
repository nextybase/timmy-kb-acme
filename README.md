# Timmy-KB – Knowledge Base Pipeline per Onboarding NeXT

## 📌 Descrizione
Timmy-KB è una **pipeline modulare** progettata per l’onboarding strutturato di PMI nella piattaforma **NeXT**.
Genera **Markdown semantico** e YAML a partire da fonti eterogenee, con validazione umana (HiTL) e pubblicazione automatica su GitHub/Book.

Il progetto segue le regole aziendali NeXT e le **best practice open-source**, con focus su:
- Automazione end-to-end
- Struttura e naming coerenti
- Compatibilità multi-target
- Logging strutturato
- Configurazione esterna (YAML + `.env`)

---

## 🚀 Funzionalità principali
- **Parsing semantico** da PDF, testi e altre fonti
- **Mapping e validazione** automatica + supervisione umana
- **Generazione output** in Markdown/YAML standardizzato
- **Pipeline CLI** modulare e componibile
- **Compatibilità DB vettoriali** e strumenti di ricerca semantica
- **Pubblicazione GitHub/Book** automatica

---

## 📂 Struttura del repository
```
root/
 ├── src/
 │    ├── pipeline/     # Orchestrazione e logica esecuzione
 │    ├── semantic/     # Parsing, tagging, validazione
 │    └── tools/        # Utility, validatori, refactoring
 ├── config/            # Configurazioni YAML
 ├── output/            # Output Markdown/YAML
 ├── tests/             # Test end-to-end e unitari
 ├── docs/              # Documentazione utente e sviluppatore
```

---

## 🛠 Requisiti
- **Python** 3.9+
- **Poetry** o **pip** per la gestione pacchetti
- Moduli indicati in `pyproject.toml` o `requirements.txt`

---

## ⚡ Installazione rapida
```bash
# Clona il repository
git clone https://github.com/nextybase/timmy-kb-acme.git
cd timmy-kb-acme

# Crea ambiente virtuale e installa dipendenze
poetry install
# oppure
pip install -r requirements.txt
```

---

## ▶️ Esecuzione
Esegui la pipeline completa:
```bash
python -m src.pipeline.onboarding_full --config config/config.yaml
```
Esegui un modulo specifico (es. estrazione keyword):
```bash
python -m src.semantic.keyword_generator --input data/pdf_folder
```

---

## 🧪 Testing
```bash
pytest tests/ --maxfail=1 --disable-warnings -q
```

---

## 📚 Documentazione
- [Guida utente](docs/user_guide.md)
- [Guida sviluppatore](docs/developer_guide.md)
- [Regole di codifica](docs/coding_rules.md)
- [Architettura tecnica](docs/architecture.md)

---

## 📜 Licenza
Distribuito sotto licenza [MIT](LICENSE).

---

**Autori**: NeXT Dev Team

