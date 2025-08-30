# Guida all’interfaccia (Streamlit) — v1.6.1

Questa pagina spiega come usare l’interfaccia grafica di **Timmy‑KB** costruita con **Streamlit**. È l’alternativa ai run da terminale: stessi step, più guidati e con feedback immediati.

> Avvio rapido: `streamlit run onboarding_ui.py`  
> Requisiti minimi: Python ≥ 3.10. Per la preview serve Docker. Per le funzioni su Drive servono credenziali e `DRIVE_ID`.

---

## 1) Primo avvio e “gating” iniziale
All’apertura vedi solo **due campi centrali** a schermo intero:
- **Slug cliente** (es. `acme`)
- **Nome cliente** (es. `ACME S.p.A.`)

Appena li compili entrambi, la UI si **sblocca** e i valori vengono **bloccati** (non modificabili). In alto appare un header con **Cliente** e **Slug**, più il pulsante **Chiudi UI** per terminare l’app.

> Per cambiare slug/nome dopo lo sblocco, riavvia l’app.

---

## 2) Struttura delle tab
Dopo lo sblocco compaiono due tab:
- **Configurazione**
- **Drive**

La terza tab **Semantica** compare **solo dopo** che avrai scaricato i PDF su `raw/` dalla tab *Drive* (vedi §3.3).

---

## 3) Tab “Configurazione”
Questa sezione gestisce il **mapping semantico** (le categorie e i loro metadati) che guida i passi successivi.

- **Panoramica categorie (solo lettura)**: preview JSON delle categorie correnti.
- **Editor per‑categoria**: ogni categoria ha un *accordion* con tre campi:
  - **Ambito** (titolo/area)
  - **Descrizione** (testo libero)
  - **Esempi** (uno per riga)
  Premi **Salva** dentro la singola voce per aggiornare solo quella categoria.
- **Normalizzazione chiavi**: toggle per forzare la **kebab‑case** (SSoT).
- **Azioni globali**:
  - **Valida mapping**: controlli di coerenza rapidi.
  - **Salva mapping rivisto**: scrive `semantic/tags_reviewed.yaml` nello spazio del cliente.

> Nota: la funzione usa gli helper del repo (nessuna duplicazione). Eventuali errori sono mostrati a schermo e loggati con dettagli tecnici.

---

## 4) Tab “Drive”
Questa sezione prepara e popola la struttura su **Google Drive**.

### 4.1 Crea/aggiorna struttura
Pulsante **“Crea/aggiorna struttura Drive”**:
- Crea (sotto `DRIVE_ID`) la cartella del cliente (nome = slug)
- Carica `config.yaml` nella cartella cliente
- Crea la gerarchia **`raw/`** (e **`contrattualistica/`** se prevista) partendo dal mapping rivisto

> Requisiti: `SERVICE_ACCOUNT_FILE` e `DRIVE_ID` nel tuo ambiente.

### 4.2 Genera README in raw/
Pulsante **“Genera README in raw/”**:
- Per ogni sotto‑cartella di `raw/`, genera un **README.pdf** (o `.txt` fallback) con ambito/descrizione/esempi
- Carica i README nelle rispettive directory su Drive

Al termine compare un messaggio di promemoria:
> “La struttura delle cartelle è stata creata su Drive; popolarne il contenuto seguendo le indicazioni del file README presente in ogni cartella per proseguire con la procedura”.

### 4.3 Scarica PDF su `raw/` locale
Dopo la generazione dei README appare una nuova sezione **“Download contenuti su raw/”** con il pulsante **“Scarica PDF da Drive in raw/”**.
- Scarica i PDF dalla struttura Drive appena creata **nella sandbox locale** del cliente (`output/timmy-kb-<slug>/raw/`).
- A download completato, la UI **sblocca** la tab **Semantica**.

> Se vedi l’errore “Funzione di download non disponibile”, aggiorna il modulo `config_ui/drive_runner.py` (serve `download_raw_from_drive`).

---

## 5) Tab “Semantica”
Questa tab appare solo dopo il download dei PDF in `raw/`. Raccoglie le funzioni per la trasformazione e l’arricchimento.

### 5.1 Converti PDF → Markdown (RAW → BOOK)
Pulsante **“Converti PDF in Markdown”**:
- Converte i PDF in file `.md` sotto `book/` usando la pipeline `semantic_onboarding`.

### 5.2 Arricchisci frontmatter
Pulsante **“Arricchisci con tag canonici (tags_reviewed.yaml)”**:
- Carica il **vocabolario rivisto** e aggiorna i frontmatter dei Markdown con tag/aree coerenti.

### 5.3 Genera/valida README & SUMMARY
Pulsante **“Genera/valida README & SUMMARY”**:
- Garantisce la presenza/validità di `SUMMARY.md` e `README.md` in `book/` (contenuti fallback idempotenti).

### 5.4 Preview Docker (HonKit)
Sezione con stato e due pulsanti:
- **Avvia preview**: lancia un container HonKit. Porta configurabile (default **4000**). Messaggio di esito e link locale.
- **Ferma preview**: arresta il container in esecuzione.

> Se Docker non è presente o la porta è occupata, viene mostrato un errore; nessun dato del cliente viene modificato.

---

## 6) Messaggi, log e resilienza
- Gli esiti positivi sono mostrati con **success banner**; errori/imprevisti con **stacktrace** sintetico.
- I log sono **strutturati**; dove configurato è attiva la **redazione** (mascheramento ID/segreti).
- Le scritture su disco usano **path‑safety** e **scritture atomiche** per evitare corruzioni.

---

## 7) Domande frequenti
**La tab Semantica non compare.**  
Assicurati di aver eseguito **“Genera README in raw/”** e poi **“Scarica PDF da Drive in raw/”** nella tab *Drive*.

**Non riesco a creare la struttura su Drive.**  
Verifica `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`. Controlla i permessi del Service Account sulla root indicata.

**La preview non parte.**  
Controlla che Docker sia avviato e che la porta scelta non sia usata da altri processi.

**Ho bisogno di cambiare slug/nome cliente.**  
Riavvia l’app e reinserisci i due valori nella schermata iniziale.

---

## 8) Suggerimenti d’uso
- Completa sempre gli step della tab **Drive** prima di passare alla **Semantica**.
- Tieni aperta accanto la cartella `output/timmy-kb-<slug>/` per verificare cosa viene generato.
- Se lavori spesso con gli stessi clienti, considera una naming convention per gli *slug* (breve, significativo, kebab‑case).

---

## 9) Esecuzione da terminale (alternativa)
Se preferisci la CLI, gli step equivalenti sono disponibili negli **orchestratori**:
```bash
py src/pre_onboarding.py
py src/tag_onboarding.py
py src/semantic_onboarding.py
py src/onboarding_full.py
```
Dettagli nelle rispettive guide.
