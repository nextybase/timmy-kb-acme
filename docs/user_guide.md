# Timmy-KB - User Guide (v1.7.0)

Guida rapida all'onboarding e alla produzione della **KB Markdown AIâ€‘ready**.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py`  â€”  vedi [Guida UI (Streamlit)](guida_ui.md).

Nota: la UI usa la faÃ§ade pubblica `semantic.api` per invocare la logica semantica senza dipendere dagli helper interni di `semantic_onboarding`.

---

## Prerequisiti
- **Python â‰¥ 3.10**  
- (Opz.) **Docker** per preview HonKit  
- (Default Drive) **Service Account JSON** e `DRIVE_ID`

Variabili utili: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`, `LOG_REDACTION`, `YAML_STRUCTURE_FILE`.

---

## Quick start  â€”  Interfaccia (consigliato per onboarding)
1. Lancia:
   ```bash
   streamlit run onboarding_ui.py
   ```
2. Inserisci **Slug cliente** e **Nome cliente** (UI si sblocca).  
3. Tab **Drive**: crea struttura, genera README, poi **Scarica PDF** su `raw/`.  
4. Tab **Semantica**: **Converti** â†’ **Arricchisci** â†’ **README & SUMMARY**.  
5. (Opz.) Avvia **Preview Docker**.

Guida completa: [guida_ui.md](guida_ui.md).

---

## Quick start  â€”  Terminale (orchestratori)
Esegui gli step in sequenza.

```bash
# 1) Setup locale (+ Drive opzionale)
py src/pre_onboarding.py --slug acme --name "Cliente ACME"

# 2) Tagging semantico (default: Drive)
py src/tag_onboarding.py --slug acme --proceed

# 3) Conversione + arricchimento + README/SUMMARY (+ preview opz.)
py src/semantic_onboarding.py --slug acme --no-preview

# 4) Push finale (se richiesto)
py src/onboarding_full.py --slug acme
```

ModalitÃ  **batch** (senza prompt): aggiungi `--non-interactive` ai comandi sopra.

---

## Struttura output
```
output/timmy-kb-<slug>/
  â”œâ”€ raw/        # PDF
  â”œâ”€ book/       # Markdown + SUMMARY.md + README.md
  â”œâ”€ semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml, tags.db
  â”œâ”€ config/     # config.yaml (con eventuali ID Drive)
  â””â”€ logs/
```

---

## Note operative
- **RAW locale Ã¨ la sorgente** per conversione/enrichment; Drive Ã¨ usato per provisioning/ingest.  
- Solo file **.md** in `book/` vengono pubblicati; i `.md.fp` sono ignorati.  
- Log con redazione automatica se `LOG_REDACTION` Ã¨ attivo.

---

## Troubleshooting essenziale
- `DRIVE_ID` mancante â†’ lo richiede `pre_onboarding`/`tag_onboarding` (default Drive).  
- PDF non scaricati in UI â†’ assicurati di aver prima **generato i README** in `raw/` e di avere permessi Drive corretti.  
- Preview non parte â†’ verifica Docker e porta libera.

