# Timmy-KB - User Guide (v1.0 Beta)

Executive summary

Questo spazio ti accompagna nel comprendere e usare strumenti che mettono a disposizione conoscenze strutturate: l'intento è sostenere la tua lettura e costruzione dei contenuti mantenendo chiara la separazione tra ciò che ti viene proposto e le decisioni che restano tue.

Il sistema non decide per te né nasconde l'incertezza, e non si sostituisce all'esperienza umana; ogni scelta, dubbio o aggiustamento rimane sotto la tua responsabilità, mentre la sua funzione è rendere esplicite le ambiguità e offrirti contesto e chiarezza.

Per la cornice filosofica del progetto vedi [MANIFEST.md](../../MANIFEST.md).

Guida rapida all'onboarding e alla produzione della **KB Markdown AIready**.

## Normative context

Questo progetto adotta una separazione intenzionale tra:
- documentazione tecnica operativa (cartella `docs/`)
- documentazione normativa e di governance ([MANIFEST.md](../../MANIFEST.md), [instructions/](../../instructions/))

Le guide in `docs/` descrivono *come* utilizzare ed estendere il sistema.
I vincoli su *cosa è consentito o vietato*, i ruoli, i gate decisionali e le
macchine a stati sono definiti esclusivamente nelle fonti normative.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py` (la UI risolve il repo root via SSoT e non si affida a `REPO_ROOT_DIR`).

Nota: la UI e gli orchestratori CLI delegano alle funzioni modulari
`semantic.convert_service`, `semantic.frontmatter_service`,
`semantic.embedding_service` e `semantic.mapping_loader`.

---

## Prerequisiti
- **Python >= 3.11**
- (Opz.) **Docker** per preview HonKit
- (Default Drive) **Service Account JSON** e `DRIVE_ID`

Variabili utili: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `LOG_REDACTION`.

---

## Quick start    Interfaccia (consigliato per onboarding)
1. Lancia:
   ```bash
   streamlit run onboarding_ui.py
   ```
2. Inserisci **Slug cliente** e **Nome cliente** (UI si sblocca).
3. Tab **Drive**: crea struttura, genera README, poi **Scarica PDF** su `raw/`.
4. Tab **Semantica**: **Converti**  **Arricchisci**  **README & SUMMARY**.
5. Tab **Gestisci cliente**  sezione *Knowledge Graph dei tag (Tag KG Builder)*: costruisce `semantic/kg.tags.json` + `semantic/kg.tags.md` a partire da `semantic/tags_raw.json` e ti mostra valori di tag/relazioni e i path generati.
5. (Opz.) Avvia **Preview Docker**.

Note Drive nella UI:
- La generazione dei README usa la variante che assicura la struttura delle cartelle.
- E' presente il pulsante "Rileva PDF in raw/" per aggiornare lo stato senza rifare il download (scansione locale di PDF/CSV).
- Dopo l'upload di `config/VisionStatement.pdf`, il tool `tools/gen_vision_yaml.py` genera `semantic/semantic_mapping.yaml` via OpenAI usando il modello risolto da `ai.vision_config.resolve_vision_config`.

Guida completa: [guida_ui.md](guida_ui.md).

---

## From Foundation to Agency
- La fase iniziale coinvolge ProtoTimmy che governa la pipeline di foundation: l'obiettivo è produrre markdown semanticamente arricchiti e validare il knowledge graph.
- Completare questa pipeline foundation abilita il passaggio a Timmy, che assume agency dialogica e coordina Domain Gatekeepers e micro-agent nella Prompt Chain documentata in `instructions/`.
- La pipeline non orchestra né decide: fornisce gli artifact affidabili richiesti dallo SSoT, mentre Timmy è responsabile della governance e del dialogo con i gatekeeper dopo la validazione.

---

## Quick start    Terminale (orchestratori)
Esegui gli step in sequenza.

```bash
# 1) Setup locale (+ Drive opzionale)
python -m timmy_kb.cli.pre_onboarding --slug acme --name "Cliente ACME"

# 2) Tagging semantico (default: Drive)
python -m timmy_kb.cli.tag_onboarding --slug acme --proceed

# 3) Costruzione Knowledge Graph dei tag
py src/kg_build.py --slug acme

> Nota: `timmy_kb.cli.semantic_onboarding` invoca internamente `build_kg_for_workspace`,
> quindi l'intero flusso semantic costruisce automaticamente il Tag KG prima di
> generare README/SUMMARY. La CLI `kg_build.py` serve per ricostruire o isolare
> questo step quando necessario.

# 4) Conversione + arricchimento + README/SUMMARY (+ preview opz.)
Esegui la pipeline semantica con gli helper modulari; ricava i path dal `WorkspaceLayout` (SSoT).

```bash
python - <<'PY'
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from semantic.vocab_loader import load_reviewed_vocab

slug = "acme"
ctx = ClientContext.load(slug=slug, require_env=True, bootstrap_config=False)
layout = WorkspaceLayout.from_context(ctx)
base_dir = layout.base_dir
log = get_structured_logger("docs.semantic", context={"slug": slug})

convert_markdown(ctx, log, slug=slug)
vocab = load_reviewed_vocab(base_dir, log)
enrich_frontmatter(ctx, log, vocab, slug=slug, allow_empty_vocab=True)
write_summary_and_readme(ctx, log, slug=slug)
PY
```

> **Nota**: `python -m timmy_kb.cli.semantic_onboarding` e `python -m timmy_kb.cli.semantic_headless` falliscono con `ConfigError` quando `semantic/tags.db` e mancante o vuoto; rigenera il vocabolario eseguendo `python -m timmy_kb.cli.tag_onboarding --slug <slug> --proceed`.

(Puoi continuare a usare `python -m timmy_kb.cli.semantic_onboarding` come orchestratore
della sequenza se preferisci una CLI dedicata.)

Per l'indicizzazione nel DB semantico puoi delegare a
`semantic.embedding_service.index_markdown_to_db`, passando il client embeddings
adottato nel tuo ambiente (es. quello configurato nella UI retriever).

# 4) Preview finale (HonKit locale)
La preview Docker/HonKit è gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

Modalita` **batch** (senza prompt): aggiungi `--non-interactive` ai comandi sopra per la parte CLI di onboarding.

---

## Vision Statement (CLI)
1. Copia `VisionStatement.pdf` in `output/timmy-kb-<slug>/config/` oppure in `raw/`.
2. Assicurati che `.env` contenga `OPENAI_API_KEY` (token valido per il modello Vision).
3. Esegui `py tools/gen_vision_yaml.py --slug <slug>`: il tool carica l'ambiente, risolve i path e genera
   `semantic/semantic_mapping.yaml`.
4. Errori (PDF mancante, risposta vuota, rifiuto modello) sono riportati come `ConfigError` senza stack trace.

### Entita fondamentali e codici documentali
- **Operativi:** Progetto, Obiettivo, Milestone, Epic, Task, Processo, Deliverable
- **Attori:** Organizzazione, Cliente, Stakeholder, Team, Operatore, Decisore, Management, Fornitore
- **Azioni:** Decisione, Analisi, Modifica, Intervento, Upgrade, Downgrade, Validazione
- **Oggetti:** Bene, Servizio, Skill, Risorsa, Outsourcing, Documento, Contratto, Dataset

| Categoria   | Entita        | Codice suggerito | Esempio nome file                     |
|-------------|---------------|------------------|---------------------------------------|
| Operativo   | Progetto      | PRJ-             | PRJ-Progetto_neXT_roadmap.pdf         |
| Attore      | Organizzazione| ORG-             | ORG-Statuto_NeXT_srl.pdf              |
| Oggetto     | Contratto     | CTR-             | CTR-Contratto_servizi_AI_2025.pdf     |
| Azione      | Decisione     | DEC-             | DEC-Verbale_CDA_2025-01-15.pdf        |

I prefissi non sono decorativi: servono a collegare i file alle entita, alimentare il modello ER e migliorare ricerca/tagging ed embedding. Se cambi entita o strutture, aggiorna il Vision Statement e riesegui la funzione Vision per rigenerare mapping/ER.


## Struttura output
```
output/timmy-kb-<slug>/
   raw/        # PDF
   book/       # Markdown + SUMMARY.md + README.md
   semantic/   # semantic_mapping.yaml, tags_raw.csv, tags.db
   config/     # config.yaml (con eventuali ID Drive)
   logs/
```

Template seed (repo): nessun template semantico copiato nel workspace durante `pre_onboarding`.

---

## Note operative
- **RAW locale e` la sorgente** per conversione/enrichment; Drive e` usato per provisioning/ingest.
- Solo file **.md** in `book/` vengono pubblicati; i `.md.fp` sono ignorati.
- Log con redazione automatica se `LOG_REDACTION` e` attivo.
- I pulsanti **Avvia arricchimento semantico**/**Abilita** nella UI rispettano il servizio `ui.services.tags_adapter`: se non e` disponibile vengono disabilitati (salvo `TAGS_MODE=stub`). In modalita` stub lo YAML viene rigenerato con `DEFAULT_TAGS_YAML` e lo stato cliente torna a **pronto** se il DB resta vuoto.
- La preview finale usa HonKit via Docker ed è gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

## Impostazioni retriever (UI)
La sidebar della UI consente di configurare il retriever, salvando i parametri in `config/config.yaml`:

```yaml
retriever:
  auto_by_budget: false
  throttle:
    candidate_limit: 4000
    latency_budget_ms: 300
    parallelism: 1
    sleep_ms_between_calls: 0
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
python tools/forbid_control_chars.py --fix <path>
```

## Troubleshooting essenziale
- `DRIVE_ID` mancante  lo richiede `pre_onboarding`/`tag_onboarding` (default Drive).
- PDF non scaricati in UI  assicurati di aver prima **generato i README** in `raw/` e di avere permessi Drive corretti.
- Preview non parte  verifica Docker e porta libera.
- Conversione fallisce con "solo PDF non sicuri/fuori perimetro"  in `raw/` ci sono solo symlink o percorsi fuori dal perimetro sicuro. Rimuovi i symlink o sposta i PDF reali dentro `raw/`, quindi riprova la conversione.
