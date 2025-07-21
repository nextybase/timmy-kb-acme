# 📚 Documentazione Pipeline Onboarding – Timmy KB (v1.2.2)

## 🧭 Obiettivo

Automatizzare la generazione, l’arricchimento semantico, l’anteprima e la pubblicazione di una Knowledge Base partendo da PDF contenuti in una cartella Drive condivisa, per ogni nuovo cliente.\
Pipeline e arricchimento semantico sono ora **modulari e completamente separati**: la pipeline si occupa di ingest, conversione, preview e push, mentre tutti gli enrichment (tagging, AI, NLP, embedding) sono delegati ai moduli in `/semantic/`.

---

## ✅ Novità v1.2.2

- 🧠 **Separazione pipeline/enrichment:** tutti gli arricchimenti semantici ora sono gestiti solo dai moduli in `/semantic/`.
- 🔁 **Batch conversion PDF→Markdown arricchito:** i markdown ora hanno frontmatter semantico direttamente in fase di conversione.
- 🧹 **Cancellazione selettiva e rigenerazione automatica:** in modalità standalone è possibile pulire la cartella principale e rigenerare tutti i markdown.
- 🛡️ **Pipeline robusta e idempotente:** ogni step lavora in modo sicuro senza rischio di duplicati o perdita dati.
- 🔎 **Preview e publish:** anteprima locale con Honkit (Docker), push interattivo su GitHub (ramo main).

---

## 🗂️ Struttura base del progetto

project-root/

├── config/

│   ├── cartelle\_semantica.yaml           # Mapping semantico delle cartelle principali

│   └── clienti/\<slug>/config.yaml        # Configurazione specifica per ogni cliente (slug = identificativo cliente)

├── output/

│   └── timmy-kb-\<slug>/                  # Output: markdown arricchiti, README, SUMMARY ecc.

├── src/

│   ├── ingest/                           # Moduli di ingestione e conversione

│   │   ├── config\_loader.py              # Caricamento delle config centralizzate

│   │   ├── pdf\_to\_md.py                  # Conversione batch PDF → Markdown

│   │   ├── build\_summary.py              # Generazione e aggiornamento SUMMARY.md

│   │   ├── gitbook\_preview\.py            # Lancio anteprima Honkit/GitBook in Docker

│   │   ├── github\_push.py                # Push su GitHub repo cliente

│   │   └── cleanup.py                    # Cancellazione selettiva / pulizia cartelle

│   ├── semantic/                         # Moduli di enrichment semantico e tagging

│   │   ├── semantic\_extractor.py         # Conversione + arricchimento PDF→MD + frontmatter semantico

│   │   └── semantic\_mapping.py           # Mappatura semantica (AI, NLP, tag, embedding)

│   └── onboarding\_full.py                # Orchestratore principale della pipeline onboarding

├── .env                                  # Variabili d’ambiente e credenziali (mai in repo!)

## ⚙️ Flusso della pipeline (Onboarding)

### 1. ▶️ Avvio pipeline

```bash
py src/onboarding_full.py
2. 🔍 Check repo GitHub esistente
Prompt se la repo esiste già; prosegui solo su conferma

3. 📥 Download PDF da Google Drive
Scarica ricorsivamente tutti i PDF da <slug>/raw

Mantiene la struttura delle sottocartelle

4. 🧩 Caricamento configurazione
Carica config.yaml del cliente e parametri da .env

5. 🧠 Conversione e arricchimento PDF→Markdown
Batch conversion di tutti i PDF in markdown con frontmatter semantico (tramite /semantic/semantic_extractor.py)

6. 📑 Generazione README & SUMMARY
Rigenera README.md e SUMMARY.md in modo idempotente

7. 🧪 Anteprima locale via Docker
Preview con container Honkit su localhost:4000

L’utente può verificare i contenuti prima del deploy

8. 🚀 Deploy GitHub
Push su repo GitHub (ramo main); prompt interattivo se già esistente

9. 🧹 Cleanup finale (opzionale)
Pulizia su richiesta; mai in automatico se la cartella contiene solo config

✅ Risultati Finali
Markdown semantic-ready, frontmatter coerente per AI/knowledge graph

README e SUMMARY sempre rigenerati e consistenti

Repo GitHub aggiornata e navigabile

Logging dettagliato, path e config centralizzati

🛠️ Requisiti tecnici
Componente	Requisito
Python	>= 3.10
Librerie	PyMuPDF, spacy, pydantic, pyyaml, slugify, google-api-python-client, docker, requests
Docker	Per preview Honkit/GitBook
GitHub CLI	gh autenticato
Google Drive	Service Account configurato (.env)

⚡ Sicurezza & portabilità
Tutti i path e parametri sono centralizzati in .env

Funziona su Windows / Linux / Mac

Logging strutturato

Nessuna credenziale sensibile in repo

🧭 Estensioni previste
Parsing PDF→MD con estrazione contenuto reale

Validazione naming e refactoring massivo

Logging configurabile e interfaccia CLI per debug

Plug-in AI e vettorializzazione

```
