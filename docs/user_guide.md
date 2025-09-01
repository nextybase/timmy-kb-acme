# Timmy‑KB — User Guide (v1.6.1)

Guida rapida all’onboarding e alla produzione della **KB Markdown AI‑ready**.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

Nota: la UI usa la façade pubblica `semantic.api` per invocare la logica semantica senza dipendere dagli helper interni di `semantic_onboarding`.

---

## Prerequisiti
- **Python ≥ 3.10**  
- (Opz.) **Docker** per preview HonKit  
- (Default Drive) **Service Account JSON** e `DRIVE_ID`

Variabili utili: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`, `LOG_REDACTION`, `YAML_STRUCTURE_FILE`.

---

## Quick start — Interfaccia (consigliato per onboarding)
1. Lancia:
   ```bash
   streamlit run onboarding_ui.py
   ```
2. Inserisci **Slug cliente** e **Nome cliente** (UI si sblocca).  
3. Tab **Drive**: crea struttura, genera README, poi **Scarica PDF** su `raw/`.  
4. Tab **Semantica**: **Converti** → **Arricchisci** → **README & SUMMARY**.  
5. (Opz.) Avvia **Preview Docker**.

Guida completa: [guida_ui.md](guida_ui.md).

---

## Quick start — Terminale (orchestratori)
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

Modalità **batch** (senza prompt): aggiungi `--non-interactive` ai comandi sopra.

---

## Struttura output
```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ semantic/   # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml
  ├─ config/     # config.yaml (con eventuali ID Drive)
  └─ logs/
```

---

## Note operative
- **RAW locale è la sorgente** per conversione/enrichment; Drive è usato per provisioning/ingest.  
- Solo file **.md** in `book/` vengono pubblicati; i `.md.fp` sono ignorati.  
- Log con redazione automatica se `LOG_REDACTION` è attivo.

---

## Troubleshooting essenziale
- `DRIVE_ID` mancante → lo richiede `pre_onboarding`/`tag_onboarding` (default Drive).  
- PDF non scaricati in UI → assicurati di aver prima **generato i README** in `raw/` e di avere permessi Drive corretti.  
- Preview non parte → verifica Docker e porta libera.
