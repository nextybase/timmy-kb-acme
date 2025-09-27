# Onboarding UI — Guida aggiornata (v1.9.6)

Questa guida descrive come usare e come funziona l'interfaccia `onboarding_ui.py`, il suo inserimento nella pipeline, le dipendenze e i casi d'errore più comuni.

> In sintesi: la UI è una app Streamlit con tre step operativi: Configurazione, Drive, Semantica, e un opzionale Preview Docker (HonKit). Tutte le funzioni delegano a utility stabili della pipeline; i fallback interni sono stati rimossi, salvo messaggi di avviso idempotenti quando un modulo non è disponibile.

---

## 1) Prerequisiti
- Python >= 3.11 e Streamlit installato
- Repository clonato e avviato dalla root
- Per la tab "Drive": credenziali Google Drive (`SERVICE_ACCOUNT_FILE`) e ID dell'unità (`DRIVE_ID`)
- Per la Preview: Docker installato e in esecuzione, porta TCP libera (configurabile in UI)
- Logging/Redazione (opzionale ma consigliato): variabili `LOG_REDACTION` / `LOG_REDACTED` o `ENV=prod`

---

## 2) Avvio
```bash
# macOS/Linux
streamlit run onboarding_ui.py

# Windows
py -m streamlit run onboarding_ui.py
```
Alla prima apertura, la landing chiede `slug` e `nome cliente`. Quando entrambi sono valorizzati, la UI si sblocca e salva lo stato in sessione. Il pulsante "Chiudi UI" termina il processo Streamlit in modo pulito.

---

## 3) Struttura logica e stato
- Lock cliente: blocca `slug`/`nome` dopo l'inserimento
- Stato Drive: avanza provisioning e download
- Gate Semantica: la tab Semantica appare solo dopo il download dei PDF in `raw/`
- Preview: nome container, porta e stato (running/stopped)

La redazione log preferisce la logica di pipeline (`compute_redact_flag`); in assenza, abilita la redazione se `ENV=prod` o variabili esplicite.

---

## 3bis) Landing Vision onboarding
- **Step 1 - upload**: con slug nuovo la landing mostra l'uploader dedicato a `VisionStatement.pdf`; il file viene salvato in `config/` con guardie `ensure_within_and_resolve`.
- **Step 2 - Genera da Vision (AI)**: il pulsante esplicito avvia la pipeline (`semantic.vision_provision.provision_from_vision`) e visualizza gli step di avanzamento `[PDF ricevuto] -> [Snapshot] -> [YAML vision] -> [YAML cartelle]`.
- **Step 3 - Anteprima**: al termine vengono mostrati in expander gli YAML `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml` per revisione rapida.
- **Step 4 - Approva**: il bottone **"Approva e crea cartelle"** crea la gerarchia `docs/` leggendo `semantic/cartelle_raw.yaml`; nessuna cartella viene generata prima di questa approvazione.
- **Idempotenza**: se l'hash del PDF non cambia, la UI avvisa che gli artefatti sono già presenti e propone un toggle per rigenerare forzatamente (utile anche per cambiare modello).
> Screenshot (TODO): acquisire la landing Vision aggiornata e salvarla come `docs/assets/vision_onboarding.png` per documentazione e training.

**Pulsanti e stati rapidi**
- `Genera da Vision (AI)`: si abilita dopo l'upload del PDF e resta in stato di avanzamento finche' la generazione non termina.
- `Approva e crea cartelle`: compare dopo la generazione e rimane disabilitato finche' gli YAML non passano la validazione di schema.
- Toggle `Rigenera Vision`: appare quando esiste `semantic/.vision_hash`; abilita la rigenerazione forzata (utile anche per cambiare modello).

> Nota: mantieni il flusso idempotente; se cambi modello attiva il toggle di rigenerazione, attendi il completamento degli step di avanzamento e poi ripeti l'approvazione.

## 4) Tab "Configurazione"
- Definisce/raffina il mapping semantico del cliente (categorie, descrizioni, alias/tag)
- Carica mapping rivisto se esiste, altrimenti un default
- Editor per una categoria alla volta (supporto HiTL)
- Validazione (duplicati, campi obbligatori, coerenza)
- Opzione di normalizzazione chiavi (kebab‑case)

Percorsi: mapping rivisto in `semantic/tags_reviewed.yaml` (workspace cliente). È mantenuto come input storico, ma il SSoT attuale è il DB SQLite. Lo YAML è solo un locator retro‑compatibile e sarà deprecato in 1.0.

---

## 5) Tab "Drive"
- Provisioning: genera struttura cartelle su Drive, incluse `raw/`
- Genera README per raw/: PDF (o TXT) di istruzioni upload
- Download contenuti: scarica file da Drive in `raw/`; aggiorna stato `raw_downloaded=True`
- Pulsante extra: "Rileva PDF in raw/" aggiorna lo stato senza download
- Vision: upload di `VisionStatement.pdf` → generazione automatica di `semantic_mapping.yaml` (schema stabile)

Funzioni (`ui.services.drive_runner`):
- `build_drive_from_mapping(slug, client_name, progress_cb)`
- `emit_readmes_for_raw(slug, ensure_structure=True)`
- `download_raw_from_drive_with_progress(slug)` o `download_raw_from_drive(slug)`

Requisiti ENV: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`

---

## 6) Tab "Semantica"
> Nota: `semantic/cartelle_raw.yaml` viene generato insieme a `semantic/semantic_mapping.yaml`; la creazione delle cartelle `docs/` rimane esplicita via pulsante nella landing.
- Conversione RAW → BOOK (PDF → Markdown)
- Arricchimento frontmatter: aggiunge tag canonici dal DB SQLite (`storage/tags_store`)
- Generazione e validazione di `README.md` e `SUMMARY.md`
- Preview Docker (opzionale): container `gitbook-<slug>`, porta configurabile, start/stop dalla UI

Funzioni (`semantic.api`):
- `convert_markdown(context, logger, *, slug)`
- `enrich_frontmatter(context, logger, vocab, *, slug)`
- `write_summary_and_readme(context, logger, *, slug)`
- `get_paths(slug)` / `load_reviewed_vocab(base_dir, logger)` (usa DB SQLite come SSoT)

Funzioni (`adapters.preview`):
- `start_preview(context, logger, *, port, container_name)`
- `stop_preview(logger, *, container_name)`

Output locale: `output/timmy-kb-<slug>/raw/`, `book/`, `README.md`, `SUMMARY.md`

---

## 7) Workspace cliente
```
output/
  timmy-kb-<slug>/
    raw/        # PDF scaricati
    book/       # Markdown generati
    semantic/
      tags_reviewed.yaml   # mapping storico (non SSoT)
      tags.db              # SSoT attuale (SQLite)
    README.md
    SUMMARY.md
```
SSoT dei tag reviewed = DB SQLite. Lo YAML resta come input per migrazione e retro‑compatibilità, ma sarà deprecato.

---

## 8) Logging & redazione
- Usa logger strutturato pipeline; fallback a `logging.basicConfig`
- Redazione calcolata da pipeline o, in assenza, da ENV/variabili

---

## 9) Errori comuni & soluzioni
- Docker non attivo/porta occupata: avvia Docker Desktop, scegli porta libera
- Credenziali Drive mancanti: verifica variabili e riesegui tab Drive
- RAW vuota o conversione fallita: controlla PDF e log
- Validazione mapping: correggi duplicati o normalizza chiavi
- Container bloccato: usa "Stop Preview" o elimina manualmente

---

## 10) Best practice
- Vision onboarding: sfrutta il toggle di rigenerazione solo quando devi aggiornare il modello o hai cambiato il PDF; in caso contrario l'hash evita compute inutile.
- Procedere in ordine: Configurazione → Drive → Semantica → Preview
- Mantieni mapping coerente con i materiali effettivi
- Usa normalizzazione chiavi per consistenza
- Evita spazi/caratteri speciali nei file sorgenti
- Avvia Docker solo quando serve la preview

---

## 11) API surface
- ui.components.mapping_editor: `load_default_mapping`, `load_tags_reviewed`, `split_mapping`, `validate_categories`, `build_mapping`, `save_tags_reviewed`
- ui.services.drive_runner: `build_drive_from_mapping`, `emit_readmes_for_raw`, `download_raw_from_drive_with_progress`, `download_raw_from_drive`
- semantic.api: `get_paths`, `load_reviewed_vocab`, `convert_markdown`, `enrich_frontmatter`, `write_summary_and_readme`
- adapters.preview: `start_preview`, `stop_preview`

---

## 12) FAQ
- Posso usare Semantica senza Drive? Sì, se i PDF sono già in `raw/`
- Come fermo la UI? Pulsante "Chiudi UI" o interrompendo Streamlit
- Dove trovo i file generati? In `output/timmy-kb-<slug>/book/` + radice workspace

---

## 13) Novità e Deprecazioni
- API semantica pubblica: la UI importa solo da `semantic.api`. È disponibile anche un wrapper CLI (`src/semantic_onboarding.py`) che orchestri `convert_markdown` → `enrich_frontmatter` → `write_summary_and_readme` per simmetria con gli altri orchestratori.
- Migrazione tag: `tags_reviewed.yaml` resta input storico; SSoT attuale = `tags.db` (SQLite). Sarà deprecato in 1.0.

---

## 14) CLI vs UI (in breve)
- Entry point: `pre_onboarding.py`, `tag_onboarding.py`, `onboarding_full.py` vs `onboarding_ui.py`
- Destinatari: DevOps/CI/power user vs utenti operativi/facilitatori
- Config: YAML + ENV vs editor interattivo mapping + Drive provisioning
- Preview: script adapters vs bottoni UI
- Requisiti extra: Token GitHub (push) vs Docker attivo e credenziali Drive
