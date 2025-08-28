# Roadmap operativa – Pre‑Onboarding (Timmy‑KB)

## Obiettivo

Consegnare una **UI di pre‑onboarding** che:

1. carichi un **YAML di base** con cartelle obbligatorie e metadati; 2) lo **arricchisca** a partire dal **Vision Statement** tramite LLM; 3) permetta **editing/validazione**; 4) all’esito, invochi la **creazione cartelle su Drive** (già esistente).

---

## Scope

- **In**: UI (Streamlit), parsing/merge YAML, AI‑enrichment, validazione, salvataggio versione finale, hand‑off al modulo “creator” già in uso.
- **Out**: implementazione del creator Drive (esiste), tag‑onboarding/semantic‑onboarding, GitHub deploy.

---

## Architettura (alto livello)

- **UI layer**: Streamlit (scelta rapida).
- **Core**: modulo `yaml_manager` (schema, I/O, validazioni), `enricher` (LLM), `validator`, `preset_templates`.
- **Integration**: `drive_client` (wrapper già esistente, qui solo “handoff”).
- **Config/Secrets**: `.env` (API keys, org, default locale).
- **Logging**: `logging` Python con file unico `onboarding.log` (livello INFO, handler console+file).

Directory suggerita:

```
src/
  ui/
    pre_onboarding_app.py
  core/
    yaml_manager.py
    schema.py
    validator.py
    enricher.py
    presets.py
  integrations/
    drive_handoff.py
  tests/
    test_yaml_manager.py
    test_validator.py
    test_enricher.py
.env
```

---

## YAML di base (cartelle obbligatorie + metadati)

**Principi**

- Le cartelle “non negoziabili” danno senso e guidano il cliente.
- Ogni nodo ha **ruolo semantico** e **tipo\_dato** (text|numeric|mixed) per i trattamenti successivi.
- Versionare con `schema_version`.

**Schema minimo**

```yaml
schema_version: 1.0
cliente:
  slug: "<slug>"
  ragione_sociale: "<rs>"
  lingua: it-IT
layout:
  - name: artefatti_base
    descrizione: "Vision Statement, Framework Etico, Aree del Dataset, Modello ER, policy."
    obbligatoria: true
    tipo_dato: text
  - name: dati_numerici
    descrizione: "Bilanci, KPI, tabelle, CSV/Excel."
    obbligatoria: true
    tipo_dato: numeric
  - name: organizzazione
    descrizione: "Org chart, ruoli, processi, procedure."
    obbligatoria: true
    tipo_dato: text
  - name: scenario
    descrizione: "Analisi di mercato, trend, serie storiche (testo e numeri)."
    obbligatoria: false
    tipo_dato: mixed
regole:
  naming: kebab-case
  allowed_types: [text, numeric, mixed]
  max_depth: 3
```

**Note**

- `layout` è una **lista ordinata** (UI conserva l’ordine).
- Campi aggiuntivi consentiti: `tags_preferite: [..]`, `pattern_file: "*.pdf;*.csv"`, `owner_team: "Finance"`.

---

## Flusso utente (E2E)

1. Inserimento **slug**, **ragione\_sociale**, upload **Vision Statement** (PDF/MD/TXT) o incolla testo.
2. Caricamento template YAML di base (da `presets.py`).
3. **AI‑Enrichment**: LLM elabora Vision Statement → propone **nuove cartelle/sottocartelle** + descrizioni + tipo\_dato.
4. UI mostra **tabella editabile** (nome, descrizione, tipo\_dato, obbligatoria, parent). Aggiungi/Rinomina/Elimina.
5. **Validazione** (schema, duplicati, nomi illegali, profondità, allowed\_types).
6. **Versioning**: salva `config/clienti/<slug>/config/config.yaml` (timestamped + `latest`).
7. **Conferma** → chiama `drive_handoff.create_from_yaml(config_path)` ed esce.

---

## LLM & Prompting (Enrichment)

**Obiettivo**: partire dal Vision Statement per suggerire cartelle pertinenti senza toccare le obbligatorie.

**Modello**: usare un LLM general‑purpose con costo basso/latency bassa. Parametri consigliati: temperatura bassa (0.2‑0.4), max\_tokens adeguati (2‑4k), **JSON‑mode** per risposta strutturata.

**Prompt (schema)**

- System: “Sei un information architect. Aggiungi cartelle semantiche a un layout esistente, mantenendo vincoli e tipi\_dato. Rispondi SOLO in JSON valido conforme allo schema.”
- User: include **YAML base**, **Vision Statement** (testo plain), **vincoli**: naming, max\_depth, allowed\_types, elenco cartelle obbligatorie.
- Output atteso (JSON):

```json
{
  "proposte": [
    {"name": "vendite", "descrizione": "Lead, pipeline, contratti", "tipo_dato": "text", "parent": null},
    {"name": "kpi_operativi", "descrizione": "Metriche operative ricorrenti", "tipo_dato": "numeric", "parent": "dati_numerici"}
  ],
  "note": "..."
}
```

**Guardrail**

- Rifiutare output non‑JSON o che rompe `allowed_types`/`max_depth`.
- Merge **idempotente**: non duplicare nomi; mappare conflitti con suffisso o suggerire rename in UI.
- **Offline‑safe**: se LLM fallisce, procedere solo con YAML base.

---

## UI/UX (Streamlit – suggerimenti pratici)

- **Sezioni**: (1) Dati cliente; (2) Upload Vision Statement; (3) Template YAML; (4) Suggerimenti AI; (5) Editor tabellare; (6) Validazione; (7) Review & Conferma.
- **Editor tabellare**: `st.data_editor` con colonne: name, descrizione, tipo\_dato (select), obbligatoria (checkbox), parent (select gerarchico). Blocca editing su righe obbligatorie per i campi critici.
- **Anteprima YAML** a destra (read‑only) che si aggiorna live.
- **Validazioni live** con badge ✅/❌ e messaggi sintetici.
- **CTA finale**: “Conferma e crea struttura su Drive”.

---

## Validazioni (hard rules)

- `name`: kebab‑case, no spazi, no caratteri speciali non ammessi da Drive, lunghezza ≤ 100.
- Unicità dei nomi allo **stesso livello**; supporto parent opzionale.
- `tipo_dato` ∈ `allowed_types`.
- `max_depth` rispettato.
- Obbligatorie **sempre presenti** e non eliminabili; consentito solo rinominare descrizione.
- **Dry‑run**: generare elenco cartelle che verranno create, con path completo.

---

## Logging & Telemetria

- Log file `onboarding.log` con **context**: slug, utente, step, esito, durata.
- Correlazione: `request_id` per chiamate LLM.
- Eventi chiave: upload, enrich start/end, validation pass/fail, save config, handoff.

---

## Sicurezza & Compliance

- Vision Statement processato **in RAM**; se salvato, cifrare a riposo (es. `Fernet`/KMS).
- Redigere **consenso** uso LLM; opzione “no‑AI” che salta l’arricchimento.
- Sanitizzazione input; limite dimensione file; antivirus opzionale per upload.

---

## Testing (DoD)

- **Unit**: parser YAML, merge, validator, normalizer naming, fallback senza AI.
- **Contract**: validare schema JSON dell’LLM (pydantic/dataclasses) + casi limite (tipi\_dato invalidi, depth overflow).
- **E2E**: scenario con Vision Statement reale → verifica che l’output rispetti obbligatorie e regole.
- **Snapshot**: confronto YAML generati per regressioni.

**Definition of Done**

- UI funzionale con editor tabellare e validazioni live.
- Enrichment AI opzionale con fallback.
- Salvataggio `config.yaml` in `config/clienti/<slug>/config/` + copia `latest`.
- Dry‑run cartelle e handoff verso modulo Drive.
- Log completo.

---

## Punti di attenzione (senior tips)

- **Idempotenza**: il merge non deve generare duplicati; normalizza i nomi prima del confronto.
- **Internazionalizzazione**: campi UI in IT/EN; ma `name` sempre kebab‑case.
- **Prestazioni**: non rigenerare l’LLM a ogni keypress; bottone “Genera suggerimenti”.
- **Explainability**: mostra perché una proposta è stata generata (estratti dal Vision Statement).
- **Usabilità**: scorciatoie “Aggiungi cartella sorella/figlia”, duplicazione record.
- **Rollback**: pulsante “Ripristina template base”.

---

## Integrazione con il modulo Drive (handoff)

- Output finale: path file YAML.
- API interna: `drive_handoff.create_from_yaml(yaml_path, dry_run=False)`; mostra anteprima struttura prima dell’esecuzione reale.
- Gestione errori di Drive: rete, permessi, rate‑limit → retry con backoff e messaggio UI chiaro.

---

## Roadmap di sviluppo (sprint suggeriti)

**Sprint 1 (UI base + YAML):** layout Streamlit, upload Vision Statement, caricamento template, editor tabellare, preview YAML.

**Sprint 2 (Validator & Merge):** regole dure, normalizzazione nomi, dry‑run, versioning file.

**Sprint 3 (LLM Enrichment):** prompt JSON‑only, guardrail, fallback, explainability.

**Sprint 4 (Handoff Drive & Hardening):** integrazione, logging unificato, gestione errori, test E2E, documentazione.

---

## Deliverable per il Junior IT

- Repo con struttura indicata e istruzioni `README.md`.
- File `presets.py` con 1–2 template base (PMI, scuola) e relativi test.
- `schema.py` con pydantic per convalida `layout`.
- `enricher.py` con funzione `suggest_layout(base_yaml, vision_text, constraints) -> Proposte`.
- `pre_onboarding_app.py` pronto all’uso (Streamlit) con salvataggio in `config/clienti/<slug>/config/config.yaml`.
- Suite di test + pipeline semplice (pytest) e report.

---

## Estensioni future (nice‑to‑have)

- Editor YAML avanzato con diff visuale.
- Ruoli/permessi (cliente vs consulente).
- Libreria di “pattern” per settori (manifattura, servizi, PA) come knowledge pack.
- Telemetria anonima per migliorare i preset.

