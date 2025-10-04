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

streamlit run onboarding_ui.py

```

---

## Landing: due pulsanti centrali
All'apertura vengono mostrati solo due pulsanti centrali:
- **Nuovo Cliente**
- **Gestisci cliente**

La pagina non cambia URL: i blocchi sottostanti si attivano aggiornando `st.session_state`.

---

## Sidebar: azioni rapide
La colonna sinistra mostra sempre una sezione fissa con:
- **Home**: azzera lo stato e riporta alla schermata iniziale (equivalente a `_back_to_landing`).
- **Genera dummy**: esegue il tool CLI `tools.gen_dummy_kb` per creare un workspace di esempio; mostra spinner e toast con l'esito.
- **Esci**: invia il segnale di shutdown all'app Streamlit.

La stessa colonna ospita logo, stato del cliente e scorciatoie contestuali (per esempio il link rapido ad 'Apri workspace').

## Diagnostica & log ZIP
L'expander **Diagnostica** nel corpo principale (sotto l'intestazione cliente) offre un check rapido senza toccare la business logic.
- Mostra il `base_dir` ricostruito best-effort dal contesto ed evidenzia lo slug corrente (raggiungibile anche tramite lo skip-link di accessibilita).
- Conta i file presenti nelle cartelle `raw/`, `book/` e `semantic/` per uno snapshot immediato del workspace.
- Se `logs/` esiste, mostra le ultime ~4 KB dell'ultimo log disponibile (decodifica safe) e fornisce un pulsante **Scarica logs** che genera al volo un archivio ZIP con tutti i file della cartella.
- I contenuti restano in sola lettura: nessun runner viene invocato e nessun side-effect viene applicato allo stato Streamlit.
- I log rispettano le regole di redazione segreti del progetto; l'expander non introduce nuove scritture.

## Tabs & stati cliente
- Se lo stato non e' disponibile (es. nessuno slug attivo) tutti i pulsanti della barra laterale restano disattivati.
- Da `inizializzato` in avanti diventano cliccabili sia **Home** sia **Gestisci cliente**.
- La tab **Semantica** resta riservata agli stati `pronto`, `arricchito` o `finito`.

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

## Riprendere dopo un'interruzione (gate Vision)

Se interrompi il flusso prima di **Inizializza workspace** e poi riparti con uno **slug** che ha gia' generato gli YAML (stesso `VisionStatement.pdf` e stesso modello), l'app non si blocca: compare un **dialog** che ti chiede come procedere. Questo accade quando il controllo su `vision_hash` rileva che il PDF e' stato gia' elaborato con la stessa configurazione.

### Scelte disponibili
- **Rigenera usando lo stesso PDF**
  Ricrea gli YAML forzando l'operazione (`force=True`), senza richiedere un nuovo upload. Idempotente.
- **Carica un nuovo PDF e rigenera**
  Sostituisci il PDF e rigenera gli YAML. Utile se il documento e' stato aggiornato.
- **Annulla e apri gli YAML**
  Nessuna rigenerazione: apri direttamente gli editor per verificare o modificare gli artefatti.

### Cosa aspettarti da l'interfaccia
- Il dialog mostra il motivo del gate (es. *Gia' elaborato con lo stesso modello...*).
- Stato e avanzamento sono visibili con `st.status`/progress; alla fine compare una notifica di esito (**toast con fallback a success**).
- Nessun side-effect a import-time, nessuna modifica alla business logic: e' un adapter **UI-only**.

### Linee guida operative
- Se vuoi ripetere esattamente l'ultimo passaggio, scegli **Rigenera usando lo stesso PDF**.
- Se il VisionStatement e' cambiato, scegli **Carica un nuovo PDF e rigenera**.
- Se devi solo consultare/modificare, scegli **Annulla e apri gli YAML**.

> Nota: la rigenerazione con lo stesso PDF usa `force=True` per bypassare il gate; le altre operazioni restano invariate. Le notifiche di completamento seguono lo standard repo: `st.toast(...)` con fallback automatico a `st.success(...)`.

### Tab "Semantica"
La tab appare solo quando lo stato del cliente e' in `{"pronto", "arricchito", "finito"}`. Per stati piu bassi la UI mostra l'avviso:
> "La semantica sara' disponibile quando lo stato raggiunge 'pronto' (dopo il download dei PDF in raw/)."

All'interno della tab sono disponibili gli editor `semantic_mapping.yaml`, `cartelle_raw.yaml` e `tags_reviewed.yaml` forniti da `ui.components.yaml_editors`.

---

## Note operative
- Tutti i salvataggi YAML utilizzano `safe_write_text` con path-safety `ensure_within_and_resolve`.
- `cartelle_raw.yaml` viene normalizzato automaticamente in formato `{raw: {...}}` quando la Vision restituisce la struttura legacy.
- Lo stato del cliente viene aggiornato tramite `clients_store.set_state` (ad esempio `inizializzato` dopo la creazione, `pronto` dopo avere popolato `raw/`).
- L'albero Drive e il diff usano frammenti Streamlit con cache di 90 secondi; il pulsante "Aggiorna elenco Drive" invalida la cache.
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
