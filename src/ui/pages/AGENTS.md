# AGENTS.md — Linee guida vincolanti per `src/ui/pages/`

> Questo documento istruisce l’agente che sviluppa/rivede le **pagine Streamlit** sotto `src/ui/pages/`.
> È **vincolante**: ogni PR che tocca l’interfaccia deve rispettarlo.

---

## 0) Scopo e perimetro

- Target: **Streamlit ≥ 1.50** con **router nativo**.
- Ambito: file in `src/ui/pages/` e ogni modulo UI invocato dalle pagine.
- Obiettivo: UI **import-safe**, **coerente**, **strumentata** (logging/observability), senza accoppiamenti inutili con pipeline e storage.

---

## 1) Architettura di pagina (contratto minimo)

Ogni pagina deve:

1. **Essere import-safe**
   - Nessun side-effect a import (niente I/O, process spawn o scritture).
   - Log/variabili create solo in funzioni o sotto `if __name__ == "__main__":` (se presente).

2. **Usare il chrome condiviso**
   - In testa: `from ui.chrome import header, sidebar` e invocare `header(slug_or_none)` e `sidebar(slug_or_none)`.
   - Non richiamare `st.set_page_config` nelle pagine: viene gestito dal chrome.

3. **Seguire il ciclo standard**
   - Recuperare il **contesto** (slug, stato) esclusivamente tramite gli **helper** di UI già forniti.
   - Rispettare la **gating policy** (vedi §3) prima di esporre azioni.
   - Effettuare chiamate ai servizi solo tramite **façade** (es. `semantic.api`), mai con import ciclici o accesso diretto a livello storage.

---

## 2) Navigazione & routing

- **Obbligatorio** usare il router nativo: `st.Page` / `st.navigation`.
  - Vietato introdurre router custom o logica di dispatch duplicata.
- **Link interni**: usare `st.page_link(PagePaths.XYZ, ...)` e non URL manuali.
- **Query/state**: leggere/scrivere lo stato di navigazione tramite **helper dedicati** (slug, tab, query); evitare accesso diretto a `st.session_state` se esiste l’helper.
- **Reindirizzamenti**: preferire i link di navigazione ad hard-redirects; usare `st.rerun()` solo se strettamente necessario e mai in loop.

**Deprecated (vietato)**:
- Router legacy o hack con `st.experimental_set_query_params`/`get_query_params` se esiste un helper equivalente.
- Hard-coded path delle pagine o import incrociati tra pagine per “saltare” il router.

---

## 3) Gating & stati (UI contratto)

- **Distinzione netta**:
  - `SEMANTIC_ENTRY_STATES`: stati che **abilitano la pagina** (es. include `"pronto"`).
  - `SEMANTIC_READY_STATES`: stati che abilitano **preview/finitura**.
- Prima di renderizzare pulsanti **mutanti** (es. Converti/Arricchisci/Summary):
  - Verificare gate **di pagina** (ENTRY).
  - Verificare precondizioni **runtime** (es. `has_raw_pdfs`).
- Testo utente: messaggi **chiari** e **coerenti** con i contratti sopra; evitare termini ambigui.

**Deprecated (vietato)**:
- Usare una sola costante per gating di pagina e di preview.
- Bloccare la pagina dopo “Converti” impedendo il flusso **convert→enrich→summary**.

---

## 4) I/O & sicurezza dei path

- **Path-safety obbligatoria**: qualunque accesso a file/dir deve usare gli **helper** (`ensure_within_and_resolve`, scanner sicuri, scritture atomiche).
- **Divieti**:
- funzioni built-in come `open` o `os.path.join` usate su path utente senza wrapper sicuro.
  - Traversal (es. `../`) o symlink non gestiti.
  - Scritture non atomiche o fuori dal workspace cliente.
- **Cache raw**: rispettare TTL/limiti da config; non re-implementare scanning o ordinamenti.

---

## 5) Logging & observability

- Logger: ottenere sempre via **`get_structured_logger`** (no `print`).
- Ogni azione rilevante deve loggare **evento** e **contesto** (`slug`, `run_id`, `phase`, …).
- **Formato**: message breve (chiave evento), dettagli in `extra`; niente f-string nel message.
- **Redazione**: nessun segreto in log/UI; mascherare token/ID sensibili.
- Non introdurre handler duplicati o livelli incoerenti; rispettare la policy di livello da configurazione.

**Deprecated (vietato)**:
- `print()`, logging “a caso”, messaggi con valori sensibili, stacktrace esposti in UI.

---

## 6) Errori, UX e performance

- **Fail-fast e chiaro**: su precondizioni mancanti, mostrare `st.info/warning/error` sintetico; dettagli → log.
- **Idempotenza**: pulsanti di fase non devono restare “bloccati” su errori; ripristinare gating/stato in `finally` degli orchestratori.
- **Reattività**: evitare operazioni sincrone lunghe nel render; usare spinner e delegare a servizi.
- **Accessibilità**: titoli (`st.subheader`), `st.divider`, pulsanti con etichette esplicite; nessun testo ambiguo.

---

## 7) Admin & azioni privilegiate

- Controlli **amministrativi** (es. stack osservabilità, link Grafana) **solo** nella pagina **Admin**.
  - Devono restare disabilitati se i prerequisiti non sono soddisfatti (es. Docker down, porta 3000 chiusa).
- La pagina Admin **non redirige** automaticamente alla Home dopo login: mostra il pannello di controllo.

**Deprecated (vietato)**:
- Azioni admin in sidebar o in pagine utente.
- Shell-out non mediati/diagnostica rumorosa in pagine non-admin.

---

## 8) Configurazione: YAML come SSoT per non-segreti

- Le pagine leggono **config non-segrete** da **Settings/YAML** (es. `ui.allow_local_only`, knob del retriever), **mai** da ENV se esiste il campo in YAML.
- I **segreti** restano in `.env` e non compaiono in UI/log.
- Non replicare logiche di parsing/validazione nelle pagine: delegare al modello Settings/Store.

---

## 9) Best practice di implementazione

- **Struttura pagina**: intestazione, gating, azioni, esito; evitare 'spaghetti Streamlit'.
- **Helper unici**: usare solo gli helper/UI già presenti (router, query, stato cliente, path-safety). Se manca un helper, crearne **uno** condiviso (no duplicati locali).
- **Testabilità**: fattorizzare la logica in funzioni pure o servizi richiamabili dai test; evitare di 'seppellire' la logica nel render.
- **Internationalization**: testo utente pronto per sostituzione; non hard-codare copy in più punti se è condiviso.

---

## 10) Deprecated / Divieti (checklist rigida)

- ❌ Router custom / legacy; ❌ uso di una sola costante per tutti i gate; ❌ stampa su console;
- ❌ I/O diretto senza helper; ❌ side-effect a import; ❌ esposizione segreti in UI/log;
- ❌ Admin actions fuori da Admin; ❌ duplicazione di contratto (UI vs servizi) su stati/policy.

---

## 11) Cosa deve fare l’agente PRIMA di aprire PR

1. Lint e type-check (ruff/mypy) senza nuove soppressioni.
2. Test UI/semantica: flusso **convert→enrich→summary** non bloccato.
3. Verifica logging: eventi presenti, niente valori sensibili, nessun handler duplicato.
4. Gating: messaggi coerenti con ENTRY vs READY; azioni disabilitate correttamente.
5. Admin: controlli osservabilità visibili solo dove previsto e con prerequisiti rispettati.
6. Documentare nella descrizione PR **cosa è stato toccato** (routing/gating/logging/I-O) e **perché**.

---

## 12) Cosa deve rifiutare l’agente (o chiedere correzione)

- Introduzione di nuove ENV lette direttamente dalla UI per parametri **non-segreti**.
- Modifiche che accoppiano UI con storage o paths senza helper.
- Regressioni su import-safety, gating o navigazione nativa.

---

## 13) Glossario rapido

- **ENTRY vs READY**: ENTRY abilita la **pagina**, READY abilita **preview/finitura**.
- **Import-safe**: importare la pagina non cambia stato, non legge/scrive risorse.
- **Helper**: funzioni condivise per stato/slug/path/router/log.

---

> Se una regola non è applicabile in un caso concreto, l’agente **deve** aprire un 'design note' nel PR spiegando l’eccezione e proponendo un helper/astrazione per evitarla in futuro.
