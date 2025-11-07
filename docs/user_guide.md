# Timmy-KB - User Guide (v1.0 Beta)

Guida rapida all'onboarding e alla produzione della **KB Markdown AIready**.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py`    vedi [Guida UI (Streamlit)](guida_ui.md).

Nota: la UI e gli orchestratori CLI delegano alle funzioni modulari
`semantic.convert_service`, `semantic.frontmatter_service`,
`semantic.embedding_service` e `semantic.mapping_loader` (riesportate da
`semantic.api` per compatibilita`).

---

## Prerequisiti
- **Python >= 3.11**
- (Opz.) **Docker** per preview HonKit
- (Default Drive) **Service Account JSON** e `DRIVE_ID`

Variabili utili: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`, `LOG_REDACTION`, `YAML_STRUCTURE_FILE`.

---

## Quick start    Interfaccia (consigliato per onboarding)
1. Lancia:
   ```bash
   streamlit run onboarding_ui.py
   ```
2. Inserisci **Slug cliente** e **Nome cliente** (UI si sblocca).
3. Tab **Drive**: crea struttura, genera README, poi **Scarica PDF** su `raw/`.
4. Tab **Semantica**: **Converti**  **Arricchisci**  **README & SUMMARY**.
5. (Opz.) Avvia **Preview Docker**.

Note Drive nella UI:
- La generazione dei README usa la variante che assicura la struttura delle cartelle.
- E' presente il pulsante "Rileva PDF in raw/" per aggiornare lo stato senza rifare il download (scansione locale di PDF/CSV).
 - Dopo l'upload di `config/VisionStatement.pdf`, il tool `gen_vision_yaml.py` genera `semantic/semantic_mapping.yaml` via OpenAI usando il modello definito in `config/config.yaml` (recuperato tramite `get_vision_model()`).

Guida completa: [guida_ui.md](guida_ui.md).

---

## Quick start    Terminale (orchestratori)
Esegui gli step in sequenza.

```bash
# 1) Setup locale (+ Drive opzionale)
py src/pre_onboarding.py --slug acme --name "Cliente ACME"

# 2) Tagging semantico (default: Drive)
py src/tag_onboarding.py --slug acme --proceed

# 3) Conversione + arricchimento + README/SUMMARY (+ preview opz.)
Esegui la pipeline semantica con gli helper modulari:

```bash
python - <<'PY'
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from semantic.vocab_loader import load_reviewed_vocab

slug = "acme"
ctx = ClientContext.load(Path.cwd(), slug=slug)
log = get_structured_logger("docs.semantic", context={"slug": slug})

convert_markdown(ctx, log, slug=slug)
vocab = load_reviewed_vocab(ctx.base_dir, log)
enrich_frontmatter(ctx, log, vocab, slug=slug, allow_empty_vocab=True)
write_summary_and_readme(ctx, log, slug=slug)
PY
```

(Puoi continuare a usare `py src/semantic_onboarding.py` come orchestratore
della sequenza se preferisci una CLI dedicata.)

Per l'indicizzazione nel DB semantico puoi delegare a
`semantic.embedding_service.index_markdown_to_db`, passando il client embeddings
adottato nel tuo ambiente (es. quello configurato nella UI retriever).

Per l'indicizzazione nel DB semantico puoi delegare a
`semantic.embedding_service.index_markdown_to_db`, passando il client embeddings
adottato nel tuo ambiente (es. quello configurato nella UI retriever).

# 4) Push finale (se richiesto)
py src/onboarding_full.py --slug acme
```

Modalita` **batch** (senza prompt): aggiungi `--non-interactive` ai comandi sopra.

---

## Vision Statement (CLI)
1. Copia `VisionStatement.pdf` in `output/timmy-kb-<slug>/config/` oppure in `raw/`.
2. Assicurati che `.env` contenga `OPENAI_API_KEY_FOLDER` (o `OPENAI_API_KEY`).
3. Esegui `py src/tools/gen_vision_yaml.py --slug <slug>`: il tool carica l'ambiente, risolve i path e genera
   `semantic/semantic_mapping.yaml`.
4. Errori (PDF mancante, risposta vuota, rifiuto modello) sono riportati come `ConfigError` senza stack trace.


## Struttura output
```
output/timmy-kb-<slug>/
   raw/        # PDF
   book/       # Markdown + SUMMARY.md + README.md
   semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv,  tags.db
   config/     # config.yaml (con eventuali ID Drive)
   logs/
```

---

## Note operative
- **RAW locale e` la sorgente** per conversione/enrichment; Drive e` usato per provisioning/ingest.
- Solo file **.md** in `book/` vengono pubblicati; i `.md.fp` sono ignorati.
- Log con redazione automatica se `LOG_REDACTION` e` attivo.

## Impostazioni retriever (UI)
La sidebar della UI consente di configurare il retriever, salvando i parametri in `config/config.yaml`:

```yaml
retriever:
  candidate_limit: 4000
  latency_budget_ms: 300
  auto_by_budget: false
```

La UI applica immediatamente le modifiche e i test di regressione coprono il pass-through verso gli helper di `semantic.embedding_service`.

---
## Controllo caratteri & encoding (UTF-8)

- `fix-control-chars`: hook pre-commit che normalizza i file (rimozione controlli C0/C1 + NFC).
- `forbid-control-chars`: hook pre-commit di guardia; blocca il commit se restano caratteri proibiti o file non UTF-8.

Esecuzione manuale:

```bash
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
python scripts/forbid_control_chars.py --fix <path>
```

## Troubleshooting essenziale
- `DRIVE_ID` mancante  lo richiede `pre_onboarding`/`tag_onboarding` (default Drive).
- PDF non scaricati in UI  assicurati di aver prima **generato i README** in `raw/` e di avere permessi Drive corretti.
- Preview non parte  verifica Docker e porta libera.
- Conversione fallisce con "solo PDF non sicuri/fuori perimetro"  in `raw/` ci sono solo symlink o percorsi fuori dal perimetro sicuro. Rimuovi i symlink o sposta i PDF reali dentro `raw/`, quindi riprova la conversione.
