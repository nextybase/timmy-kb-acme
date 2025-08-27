# User Guide — Timmy‑KB (v1.5.0)

Guida aggiornata per l’uso della pipeline di **onboarding clienti** in Timmy‑KB. Converte PDF in Markdown AI‑ready, arricchisce i frontmatter, lancia l’anteprima HonKit (Docker) e, se richiesto, pubblica su GitHub.

---

## 1) Prerequisiti

- **Python ≥ 3.10**
- **Docker** (per l’anteprima)
- **Credenziali Google Drive** (Service Account JSON) — *necessarie se usi Drive*
- (Opz.) **GitHub Token** per il push finale

### Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE` → path JSON Service Account (Drive)
- `DRIVE_ID` → ID cartella root dello Shared Drive
- `GITHUB_TOKEN` → richiesto per il push su GitHub
- `YAML_STRUCTURE_FILE` → override opzionale dello YAML cartelle (default: `config/cartelle_raw.yaml`)
- `LOG_REDACTION` → `auto` (default), `on`, `off`
- `ENV`, `CI` → per modalità operative

> Se non hai credenziali Drive ma vuoi procedere comunque, usa le modalità **solo locale** nei comandi che lo supportano.

---

## 2) Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF di origine (fonte unica locale)
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
- **CLI/Batch**: nessun prompt, tutto via opzioni (`--slug`, `--non-interactive`, …).

---

### A) Pre‑Onboarding (setup)

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome>] [--non-interactive] [--dry-run]
```

1. Richiede *slug* cliente.
2. Crea struttura locale (`raw`, `book`, `config`, `logs`).
3. Copia i template semantici in `semantic/` e arricchisce `semantic_mapping.yaml` con blocco di contesto.
4. Se configurato, crea la struttura su Drive e carica `config.yaml` nella root cliente.

---

### B) Tag Onboarding (HiTL)

```bash
py src/tag_onboarding.py --slug <id> [--source local|drive] [--proceed] [--non-interactive]
```

1. **Sorgente PDF → raw/**
   - **Default: `drive`** → scarica i PDF su `raw/` usando gli ID dal `config.yaml` creato in pre‑onboarding.
   - **Solo locale**: `--source local` (opz. `--local-path <dir>` per copiare PDF in `raw/`, altrimenti usa quelli già presenti).
2. Genera `semantic/tags_raw.csv` (scrittura streaming, POSIX path `raw/...`).
3. Checkpoint umano (HiTL): conferma prima di proseguire (o passa `--proceed`).
4. Se confermato, crea `README_TAGGING.md` e lo stub `tags_reviewed.yaml`.

**Esempi rapidi**
```bash
# Default (Drive → RAW)
py src/tag_onboarding.py --slug acme --non-interactive --proceed

# Solo locale (senza Drive)
py src/tag_onboarding.py --slug acme --source local --non-interactive --proceed
# Copia da una cartella esterna in RAW prima del CSV
py src/tag_onboarding.py --slug acme --source local --local-path ./some-pdfs --non-interactive --proceed
```

---

### C) Semantic Onboarding (conversione + preview)

```bash
py src/semantic_onboarding.py --slug <id> [--no-preview] [--preview-port 4000] [--non-interactive]
```

1. Converte PDF → Markdown in `book/`.
2. Arricchisce frontmatter usando `semantic/tags_reviewed.yaml`.
3. Genera `README.md` e `SUMMARY.md` (fallback idempotente se le utilità non sono disponibili).
4. Avvia preview Docker HonKit (se presente). In interattivo chiede se avviare/fermare; in CLI puoi passare `--no-preview`.

---

### D) Onboarding Full (Push)

```bash
py src/onboarding_full.py --slug <id> [--non-interactive]
```

1. Preflight su `book/`: ammessi solo file **`.md`** (i placeholder **`.md.fp`** sono **ignorati**). Qualsiasi artefatto di build (es. `_book/`, `package.json`, `book.json`) va rimosso/spostato.
2. Garantisce `README.md` e `SUMMARY.md` (fallback se mancanti).
3. Esegue push su GitHub (richiede `GITHUB_TOKEN`). In interattivo chiede conferma.

> La preview Docker non richiede file extra dentro `book/`. Non committare `_book/` o asset non‑md: verranno bloccati dal preflight.

---

## 4) Comandi rapidi

### Interattivo
```bash
py src/pre_onboarding.py            # setup locale (+ Drive se configurato)
py src/tag_onboarding.py            # default: Drive → raw/
py src/semantic_onboarding.py       # conversione + preview
py src/onboarding_full.py           # push GitHub
```

### CLI/Batch
```bash
# Setup minimale solo locale
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive --dry-run

# Tagging (default: Drive)
py src/tag_onboarding.py --slug acme --non-interactive --proceed

# Variante solo locale
py src/tag_onboarding.py --slug acme --source local --local-path ./fixtures/pdfs --non-interactive --proceed

# Generazione book + enrichment, senza preview
py src/semantic_onboarding.py --slug acme --no-preview --non-interactive

# Push GitHub
set GITHUB_TOKEN=...
py src/onboarding_full.py --slug acme --non-interactive
```

---

## 5) Log & Exit Codes

- Log per fase in `output/timmy-kb-<slug>/logs/`.
- Mascheramento automatico credenziali se `LOG_REDACTION=on/auto`.
- Exit codes principali: `0=OK`, `2=ConfigError`, `30=PreviewError`, `40=PushError`.

---

## 6) Troubleshooting

- **Docker mancante** → interattivo: chiede se saltare; CLI: `--no-preview`.
- **Book contiene file non‑md** → errore di preflight. Sposta in `assets/` o rimuovi artefatti di build (`_book/`, `package.json`, `book.json`). I `.md.fp` sono ignorati.
- **Push fallito** → verifica `GITHUB_TOKEN` e branch.
- **Tags incoerenti** → riallinea `semantic/tags_raw.csv` e `semantic/tags_reviewed.yaml`.
- **Drive non disponibile** → usa `--source local` in `tag_onboarding`.

---

## 7) Test e Policy operative

- **Orchestratori**: gestiscono prompt, UX, checkpoint HiTL, codici di uscita.  
  **Moduli tecnici**: nessun I/O utente, nessun `sys.exit()`.
- **Sicurezza I/O**: path validati con `ensure_within`; scritture atomiche via `safe_write_text`/`safe_write_bytes`.
- **Test**
  - Suite deterministica, senza rete, con dataset **dummy**.
  - Livelli: **unit**, **contract/CLI**, **smoke/E2E**.  
  - Guida completa e comandi: vedi **[docs/test_suite.md](test_suite.md)**.
- **Doc↔codice**: ogni modifica a orchestratori/API richiede aggiornamento contestuale di documentazione e test; le PR devono mantenere tutti i test verdi.

---

## 8) FAQ

**Posso usare la preview senza Docker?**  No: viene saltata.

**Cosa viene pushato su GitHub?**  Solo i `.md` in `book/`.

**Qual è la sorgente PDF di default?**  `tag_onboarding` usa **Drive** di default; per lavorare offline usa `--source local`.

**Come forzo un push?**  Se previsto, `--force-push` + `--force-ack`.

**Slug non valido?**  In interattivo chiede correzione; in batch fallisce.

**Devo toccare a mano `semantic_mapping.yaml`?**  Non obbligatorio: è generato con default sensati; puoi personalizzarlo per cliente.

---

## 9) Log & Redazione

- `LOG_REDACTION=auto` (default) → attiva in `prod/ci` o se rileva credenziali.
- `on` → sempre attiva; `off` → disattiva.
- In debug la redazione è disattivata. Dati sensibili vengono mascherati nel logging strutturato.

