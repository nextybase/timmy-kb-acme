# User Guide — Timmy‑KB (v1.5.0)

Guida aggiornata per l’uso della pipeline di **onboarding clienti** in Timmy‑KB. Converte PDF in Markdown AI‑ready, arricchisce i frontmatter, avvia anteprima HonKit (Docker) e, se richiesto, pubblica su GitHub.

---

## 1) Prerequisiti

- **Python ≥ 3.10**
- **Docker** (per l’anteprima)
- (Opz.) **Credenziali Google Drive** (Service Account JSON)
- (Opz.) **GitHub Token** per il push finale

### Variabili d’ambiente principali

- `SERVICE_ACCOUNT_FILE` → path JSON Service Account (Drive)
- `DRIVE_ID` → ID cartella root dello spazio Drive
- `GITHUB_TOKEN` → per il push su GitHub
- `YAML_STRUCTURE_FILE` → override opzionale dello YAML cartelle (default: `config/cartelle_raw.yaml`)
- `LOG_REDACTION` → `auto` (default), `on`, `off`
- `ENV`, `CI` → per modalità operative

---

## 2) Struttura output

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF
  ├─ book/       # Markdown + README.md + SUMMARY.md
  ├─ semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml
  ├─ config/     # config.yaml
  └─ logs/       # log centralizzati
```

> **SSoT semantico**: `tags_reviewed.yaml` è la fonte unica dei tag canonici.

---

## 3) Flussi operativi

### Modalità interattiva vs CLI
- **Interattiva**: prompt a video, scelte passo‑passo.
- **CLI/Batch**: nessun prompt, tutto via opzioni (`--slug`, `--non-interactive`, ...).

---

### A) Pre‑Onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome>] [--non-interactive] [--dry-run]
```

1. Richiede *slug* cliente.
2. Crea struttura locale (raw, book, config, logs).
3. Copia i template semantici in `semantic/` e arricchisce `semantic_mapping.yaml`.
4. Se configurato, crea struttura su Drive e carica `config.yaml`.

---

### B) Tag Onboarding (HiTL)

```bash
py src/tag_onboarding.py --slug <id> [--source local|drive] [--proceed]
```

1. Copia/scarica PDF in `raw/`.
2. Genera `semantic/tags_raw.csv`.
3. Checkpoint umano: confermare prima di proseguire.
4. Se confermato (o `--proceed`), crea `README_TAGGING.md` e `tags_reviewed.yaml`.

---

### C) Semantic Onboarding

```bash
py src/semantic_onboarding.py --slug <id> [--no-preview] [--preview-port 4000]
```

1. Converte PDF → Markdown in `book/`.
2. Arricchisce frontmatter con `tags_reviewed.yaml`.
3. Genera `README.md` e `SUMMARY.md` (fallback idempotente).
4. Avvia preview Docker (se presente). In interattivo chiede se avviare/fermare.

---

### D) Onboarding Full (Push)

```bash
py src/onboarding_full.py --slug <id>
```

1. Preflight su `book/`: ammessi solo `.md`, i `.md.fp` sono ignorati.
2. Garantisce `README.md` e `SUMMARY.md`.
3. Esegue push GitHub (richiede `GITHUB_TOKEN`). In interattivo chiede conferma.

---

## 4) Comandi rapidi

### Interattivo
```bash
py src/pre_onboarding.py
py src/tag_onboarding.py
py src/semantic_onboarding.py
py src/onboarding_full.py
```

### CLI/Batch
```bash
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive --dry-run
py src/tag_onboarding.py --slug acme --source local --non-interactive --proceed
py src/semantic_onboarding.py --slug acme --no-preview --non-interactive
py src/onboarding_full.py --slug acme --non-interactive
```

---

## 5) Log & Exit Codes

- Log in `logs/` per ogni fase.
- Mascheramento automatico di credenziali (se `LOG_REDACTION=on/auto`).
- Exit codes standardizzati: `0=OK`, `2=ConfigError`, `40=PushError`, ecc.

---

## 6) Troubleshooting

- **Docker mancante** → interattivo: chiede se saltare, CLI: skip automatico.
- **Book con file non‑md** → errore. Sposta in `assets/` o converti. `.md.fp` sono ignorati.
- **Push fallito** → controlla `GITHUB_TOKEN` e branch.
- **Tags incoerenti** → riallinea `tags_raw.csv` e `tags_reviewed.yaml`.

---

## 7) Test e Policy operative

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

- **Policy doc↔codice**  
  - Ogni modifica agli orchestratori o alle API interne richiede **aggiornamento contestuale** di documentazione e test.  
  - Le PR devono mantenere **tutti i test verdi**; aggiungere test per regressioni e nuovi percorsi critici.


---

## 8) FAQ

**Posso usare la preview senza Docker?**  No. Se Docker manca, viene saltata.

**Cosa viene pushato su GitHub?**  Solo i `.md` in `book/`.

**Come gestire force push?**  Con `--force-push` + `--force-ack` (se implementato).

**Slug non valido?**  In interattivo chiede correzione, in batch fallisce.

**Devo modificare a mano semantic_mapping?**  Non obbligatorio. Puoi personalizzare `semantic_mapping.yaml` cliente.

---

## 9) Log & Redazione

- Modalità `LOG_REDACTION`:
  - `auto` (default) → attiva in prod/ci o se presenti credenziali.
  - `on` → sempre attiva.
  - `off` → disattiva.
- In debug, redazione disattiva.
- Dati sensibili (token, path credenziali) mascherati automaticamente.

