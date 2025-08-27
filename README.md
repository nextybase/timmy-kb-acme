# Timmy-KB — README (v1.4.0)

Pipeline per la generazione di una **Knowledge Base Markdown AI-ready** a partire da PDF cliente, con arricchimento semantico, anteprima HonKit (Docker) e push opzionale su GitHub.

---

# Timmy-KB Onboarding

Pipeline di onboarding dei clienti per Timmy-KB.

## Flusso principale
1. **Pre-Onboarding**  
   Crea la struttura locale e remota (Drive), copia i template semantici e genera il `config.yaml`.

2. **Tag Onboarding (HiTL)**  
   Estrae i PDF (da Drive o locale) → genera `semantic/tags_raw.csv`.  
   Dopo il checkpoint umano, produce `README_TAGGING.md` e `tags_reviewed.yaml`.

3. **Semantic Onboarding**  
   Converte i PDF in `book/*.md`, arricchisce i frontmatter con i dati di `semantic/tags_reviewed.yaml`, genera `README.md` e `SUMMARY.md`.  
   Avvia la preview Docker (HonKit).

4. **Onboarding Full (Push)**  
   Verifica che in `book/` ci siano solo `.md` (i `.md.fp` vengono ignorati di default), garantisce i fallback README/SUMMARY e pubblica su GitHub.

## Note
- **SSoT dei tag**: il file di riferimento è `semantic/tags_reviewed.yaml`.  
- **Drive**: usato solo in `pre_onboarding` e opzionale in `tag_onboarding` (`--source=drive`).  
- **Logging**: centralizzato, con mascheramento degli ID sensibili.  

---

## Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima)
- (Solo per pre-onboarding con Drive) **Credenziali Google** (Service Account JSON)
- (Opz.) **GitHub Token** (`GITHUB_TOKEN`) per il push

### Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE` → path al JSON del Service Account (solo per Drive)  
- `DRIVE_ID` → radice/parent dello spazio Drive (solo per Drive)  
- `GITHUB_TOKEN` → richiesto per il push GitHub  
- `GIT_DEFAULT_BRANCH` → branch di default (fallback `main`)  
- `YAML_STRUCTURE_FILE` → override opzionale del file YAML per il pre-onboarding (default `config/cartelle_raw.yaml`)  
- `LOG_REDACTION` → `auto` (default), `on`, `off`  
- `ENV` → `dev`, `prod`, `ci`, ...  
- `CI` → `true`/`false`  

---

## Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF caricati/scaricati
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml
  ├─ config/     # config.yaml aggiornato con ID Drive e blocchi client-specific
  └─ logs/       # log centralizzati (pre_onboarding, tag_onboarding, semantic_onboarding, onboarding_full)
```

> Lo **slug** deve rispettare la regex in `config/config.yaml`. In interattivo, se non valido, viene richiesto di correggerlo.

---

## Flussi operativi

### Modalità interattiva vs CLI

- **Interattiva** → guidata via prompt (slug, nome cliente, conferme preview/push).  
  Esempi:
  ```bash
  py src/pre_onboarding.py
  py src/tag_onboarding.py
  py src/semantic_onboarding.py
  py src/onboarding_full.py
  ```

- **CLI (batch)** → parametri espliciti (`--slug`, `--name`, `--no-preview`, `--no-push`, ecc.), nessun prompt.  
  Esempi:
  ```bash
  py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive
  py src/tag_onboarding.py --slug acme --non-interactive
  py src/semantic_onboarding.py --slug acme --no-preview --non-interactive
  py src/onboarding_full.py --slug acme --non-interactive
  ```

---

### 1) Pre-onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome descrittivo>] [--non-interactive] [--dry-run]
```

1. Richiede *slug* (e, se interattivo, nome cliente).  
2. Crea struttura locale (`raw/`, `book/`, `config/`, `logs/`, `semantic/`).  
3. Copia i template in `semantic/` (`cartelle_raw.yaml`, `semantic_mapping.yaml`) con valori di default `semantic_tagger`.  
4. Drive opzionale: se configurato crea/aggiorna la struttura remota e carica `config.yaml`.  
5. Aggiorna `config.yaml` locale con gli ID Drive.  

> In `--dry-run` lavora solo in locale, senza Drive.

---

### 2) Tagging semantico

```bash
py src/tag_onboarding.py --slug <id>
```

1. Legge i PDF in `raw/`.  
2. Genera `semantic/tags_raw.csv` con path base-relative (`raw/...`) e colonne standard (relative_path, suggested_tags, entities, keyphrases, score, sources).  
3. Checkpoint HiTL: l’utente può fermarsi dopo il CSV o proseguire con lo stub.  
4. Se confermato (o `--proceed`), crea `README_TAGGING.md` e `tags_reviewed.yaml` (stub) in `semantic/`.  

---

### 3) Semantic onboarding

```bash
py src/semantic_onboarding.py [--slug <id>] [opzioni]
```

1. Conversione PDF → Markdown in `book/`.  
2. Arricchimento frontmatter dei `.md` usando `semantic/tags_reviewed.yaml`.  
3. Generazione `README.md` e `SUMMARY.md`.  
4. Avvio preview HonKit (Docker) opzionale, con chiusura esplicita richiesta.  

**Opzioni CLI aggiuntive:**
- `--no-preview` → salta la preview Docker.  
- `--preview-port <N>` → porta per la preview (default 4000).  

---

### 4) Onboarding full (solo push)

```bash
py src/onboarding_full.py --slug <id>
```

1. Esegue esclusivamente il push GitHub del contenuto di `book/`.  
2. Richiede `GITHUB_TOKEN` valido.  
3. In roadmap: integrazione diretta GitBook.  

---

## 7) Test 

- **Orchestratori**: gestiscono prompt, UX, checkpoint HiTL e codici di uscita.  
  **Moduli tecnici**: nessun I/O utente, nessun `sys.exit()`.

- **Sicurezza I/O**: tutti i path sono validati con `ensure_within`; scritture atomiche via `safe_write_text`/`safe_write_bytes`.

- **Test: principi**  
  - I test sono **deterministici**, indipendenti dalla rete e riproducibili su Windows/Linux/Mac.  
  - Le integrazioni esterne (Google Drive, GitHub) sono **mockate/stub** nella suite; l’uso reale è limitato allo **E2E manuale**.  
  - Prima di eseguire i test, genera l’ambiente di prova con l’**utente/dataset dummy**.

- **Livelli di test (vedi `docs/test_suite.md`)**  
  - **Unit**: funzioni pure e utility (es. validatore YAML, emissione CSV, guard frontmatter/book).  
  - **Contract/CLI**: firme, default e exit code degli orchestratori.  
  - **Smoke/E2E**: percorso minimo su dataset dummy (senza servizi esterni), più varianti manuali opzionali.

- **Come lanciare**  
  - Globale: `pytest -ra` (dopo `py src/tools/gen_dummy_kb.py --slug dummy`).  
  - Per file/funzione/marker e scenari manuali: rimando completo in [Test suite](test_suite.md).

---

## Log e sicurezza

- Log centralizzati in `output/timmy-kb-<slug>/logs/`.  
- Mascheramento segreti automatico (`LOG_REDACTION`).  
- Scritture atomiche e path-safety enforced (`ensure_within` come SSoT).  

---

## Exit codes principali

- `0` → OK  
- `2` → ConfigError (slug invalido, variabili mancanti)  
- `30` → PreviewError  
- `40` → PushError  

---

## Note operative

- La **RAW è sempre locale** (`output/timmy-kb-<slug>/raw`); Drive è usato solo per la sincronizzazione iniziale.  
- La preview funziona solo se Docker è disponibile; in batch viene saltata.  
- In interattivo puoi decidere se avviare/fermare preview e push.  
- Pubblicazione su GitHub: vengono inclusi solo i `.md` in `book/`.  
- La sandbox dummy (`timmy-kb-dummy`) è usata nei test automatici per validare coerenza e idempotenza della pipeline.  

---

