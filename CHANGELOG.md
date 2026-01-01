# Changelog

All notable changes to this project are documented in this file.
The format follows *Keep a Changelog* and *Semantic Versioning*.

---

## [Unreleased] — Stabilizzazione architetturale pre-1.0 Beta

Questa sezione rappresenta **l’unico piano di lavoro residuo** prima della Beta 1.0.
I punti sono ordinati **per priorità architetturale e riduzione del rischio sistemico**.

---

### Phase 1 — Rimozione ambiguità operative (fondamenta)

**Obiettivo:** ridurre entropia concettuale e tecnica prima di qualsiasi raffinamento.

**TODO-A — Cleanup definitivo flussi GitHub / Push**
- Rimuovere ogni residuo funzionale e documentale relativo a:
  - push verso GitHub,
  - branch di deploy,
  - test e script associati al push.
- Mantenere **unica modalità supportata**:
  - preview locale (Docker / HonKit).
- Ambito:
  - codice (errori, utility, CI),
  - documentazione,
  - checklist operative.

**Stato:** Aperto
**Motivazione:** i riferimenti al push esistono ancora in più strati (code, docs, CI).

---

### Phase 2 — Allineamento Import Contract & bootstrap

**Obiettivo:** rendere il modello di import e bootstrap **deterministico e verificabile**.

**TODO-B — Eliminazione completa di `src.*` come namespace**
- Vietare `src.*`:
  - nel codice,
  - nei test,
  - **anche nella documentazione** (inclusi esempi e regex).
- I riferimenti al legacy devono essere:
  - astratti,
  - non matchabili come namespace reale.

**TODO-C — Normalizzazione `sys.path`**
- Consentire `sys.path.insert/append` **solo** in:
  - entrypoint dichiarati,
  - con motivazione documentata.
- Vietato l’uso in moduli applicativi o di libreria.
- Questo punto costituisce **criterio di accettazione**, non un task isolato.

**Stato:** Aperto
**Nota:** questi punti definiscono il *DoD architetturale* del progetto.

---

### Phase 3 — Determinismo Vision & pipeline semantica

**Obiettivo:** stessa input → stesso output, o fallimento esplicito.

**TODO-D — Vision provisioning deterministico**
- Eliminare fallback “warning-only” che producono:
  - artefatti alternativi,
  - output incompleti non dichiarati.
- Distinzione chiara:
  - **Smoke** → Vision disabilitata, output dichiaratamente incompleto ma stabile.
  - **Deep** → Vision attiva, fallimento = errore esplicito (no artefatti sostitutivi).
- Nessuna generazione “silenziosa” di YAML/semantic alternativi.

**Stato:** Aperto
**Motivazione:** oggi esistono ancora percorsi che violano il determinismo.

---

### Phase 4 — Dummy revision (ultimo step)

**Obiettivo:** portare il Dummy a piena conformità con il Manifesto.

**TODO-E — Allineamento completo Dummy a ADR-0007**
- Il Dummy diventa:
  - fixture architetturale SSoT,
  - controprova end-to-end del sistema.
- Requisiti:
  - stessi entrypoint dei clienti reali,
  - step selezionabili (Drive / Vision / Semantic / Enrichment / Preview),
  - rigenerabilità senza residui,
  - smoke in CI, deep solo manuale.
- ADR-0006 resta valido **solo come applicazione subordinata**.

**Stato:** Pianificato (ultimo step)
**Nota:** questo punto **non va anticipato** prima della chiusura delle fasi precedenti.

---

### Out of scope / chiusi per decisione

- **Prompt N+1, push tag 1.0 Beta**
  Chiuso per cambio strategia di rilascio (decisione HiTL).

---

### Governance note

- Questo changelog è **intenzionale**, non descrittivo:
  ogni TODO rappresenta una decisione architetturale da chiudere.
- Nessun nuovo TODO verrà aggiunto fuori da questa struttura.
- La Beta 1.0 è bloccata finché **tutte le Phase 1–4** non sono completate.

---
