
# Onboarding UI - Guida a blocchi (v2)

Questa guida descrive l'interfaccia Streamlit utilizzata per l'onboarding dei clienti Timmy-KB. Il layout attuale si basa su blocchi dinamici invece delle vecchie tab statiche.

---

## Prerequisiti
- Python 3.11 (o superiore) con Streamlit installato
- Repository clonato e comando eseguito dalla root del progetto
- Credenziali Drive (variabili `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`) per le operazioni remote
- Opzionale: Docker attivo se si utilizzano componenti aggiuntivi al di fuori del flusso documentato qui

Avvio rapido:
```bash
# macOS / Linux
streamlit run src/ui/app.py

# Windows
py -m streamlit run src/ui/app.py
```

---

## Landing: due pulsanti centrali
All'apertura vengono mostrati solo due pulsanti centrali:
- **Nuovo Cliente**
- **Gestisci cliente**

La pagina non cambia URL: i blocchi sottostanti si attivano aggiornando `st.session_state`.

---

## Flusso "Nuovo Cliente"
1. **Form anagrafica**: campi `Slug (kebab-case)` e `Nome cliente`.
2. **Upload VisionStatement.pdf**: l'uploader accetta un singolo PDF e lo salva in `config/VisionStatement.pdf`.
3. **Inizializza workspace**: il pulsante resta cliccabile, ma al click verifica slug, nome e PDF. Se manca qualcosa mostra errori espliciti. In caso positivo:
   - Copia la configurazione base.
   - Avvia `provision_from_vision` per generare `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml`.
   - Mostra gli YAML in due editor a larghezza fissa.
4. **Crea Workspace**: esegue i runner esistenti (`_run_create_local_structure`, `_run_drive_structure`, `_run_generate_readmes`) per creare le cartelle in locale e su Drive. Durante la procedura viene mostrato uno spinner; al termine lo stato del cliente passa a `inizializzato`.

Gli editor YAML restano disponibili dopo la creazione per eventuali ritocchi manuali.

---

## Flusso "Gestisci cliente"
Dopo avere scelto lo slug, la pagina mostra tre blocchi principali affiancati:

1. **Albero Drive**
   - Mostra la gerarchia a partire da `DRIVE_ID/<slug>/` con focus su `raw/` e relative sottocartelle.
   - Usa `render_drive_tree(slug)` e restituisce un indice dei metadati (tipo, size, mtime).

2. **Diff Drive vs locale**
   - Confronta `raw/` remoto con `output/timmy-kb-<slug>/raw/` locale.
   - Espone i conteggi di elementi presenti solo su Drive, solo in locale e le differenze (size/mtime).

3. **Editor tags_reviewed + Estrai Tags**
   - Editor YAML per `semantic/tags_reviewed.yaml` con validazione minima.
   - Pulsante **Estrai Tags** che esegue `run_tags_update(slug)`:
     - Genera `tags_raw.csv`.
     - Aggiorna lo stub tramite `write_tags_review_stub_from_csv`.
     - Sincronizza `tags_reviewed.yaml` e ricarica il testo nell'editor.
     - In caso di errore mostra un messaggio e scrive il motivo nei log.

### Tab "Semantica"
La tab appare solo quando lo stato del cliente e' in `{"pronto", "arricchito", "finito"}`. Per stati piu bassi la UI mostra l'avviso:
> "La semantica sara' disponibile quando lo stato raggiunge 'pronto' (dopo il download dei PDF in raw/)."

All'interno della tab sono disponibili gli editor `semantic_mapping.yaml`, `cartelle_raw.yaml` e `tags_reviewed.yaml` forniti da `ui.components.yaml_editors`.

---

## Note operative
- Tutti i salvataggi YAML utilizzano `safe_write_text` con path-safety `ensure_within_and_resolve`.
- `cartelle_raw.yaml` viene normalizzato automaticamente in formato `{raw: {...}}` quando la Vision restituisce la struttura legacy.
- Lo stato del cliente viene aggiornato tramite `clients_store.set_state` (ad esempio `inizializzato` dopo la creazione, `pronto` dopo avere popolato `raw/`).
- Gli spinner e i messaggi di esito sono visibili nella pagina corrente: non vengono aperte modali o tab secondarie.

---

## Struttura del workspace
```
output/
  timmy-kb-<slug>/
    raw/
    book/
    semantic/
      semantic_mapping.yaml
      cartelle_raw.yaml
      tags_reviewed.yaml
      tags.db
    config/
      config.yaml
      VisionStatement.pdf
```
`tags.db` resta la fonte dati di runtime; lo YAML serve per authoring e controlli rapidi.

---

## Suggerimenti
- Usa slug in kebab-case (minuscole, numeri e trattini).
- Rigenera gli artefatti Vision solo quando cambia il PDF.
- Dopo avere caricato i PDF in Drive, esegui il diff per verificare la sincronizzazione.
- Mantieni gli YAML coerenti: l'editor valida lo schema prima di salvare.

---

## FAQ
- **Come avvio l'interfaccia?** `streamlit run src/ui/app.py`.
- **Dove viene salvato il Vision Statement?** In `config/VisionStatement.pdf`.
- **Perche' non vedo la tab Semantica?** Lo stato del cliente deve essere almeno `pronto`.
- **Posso usare Estrai Tags senza Drive?** Si, se `raw/` contiene gia' i PDF necessari.

---

Documento mantenuto in ASCII per evitare problemi di encoding e compatibile con cSpell.
