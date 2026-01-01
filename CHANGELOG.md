# Changelog

All notable changes to this project are documented in this file.
The format follows *Keep a Changelog* and *Semantic Versioning*.

---

## [Beta 1.0] - Vision & Dummy hardening

- Rimossa ogni forma di fallback Vision/semantic (dummy YAML, semantic di emergenza).
- Introdotta semantica deterministica di `VISION_MODE`:
  - **SMOKE:** Vision sempre skip, nessun artefatto alternativo generato.
  - **DEEP:** Vision obbligatoria, fail-fast su errore.
- Gestito il caso "Vision already completed" tramite sentinel:
  - Vision/PDF non rieseguiti.
  - Nessun hard-fail se mapping/categorie assenti.
  - Nessun fallback generato.
- Ripristinato book skeleton minimo (`alpha.md`, `beta.md`, `README.md`, `SUMMARY.md`) indipendente da Vision.
- Test suite allineata alle nuove semantics (QA verde).

**TODO (intenzionale):**
- Definire se il flusso Dummy debba prevedere un semantic minimo dichiarato o rimanere semantic-less.

---

## [Unreleased] - Dummy decision (unico TODO aperto)

**Obiettivo:** chiarire il ruolo del Dummy nella Beta 1.0.

**TODO-E - Allineamento Dummy a ADR-0007 (decisione progettuale)**
- Il Dummy come fixture architetturale SSoT.
- Scelta esplicita: semantic minimo dichiarato **oppure** semantic-less.

**Stato:** Aperto

---

### Governance note

- Questo changelog e **intenzionale**, non descrittivo: ogni TODO rappresenta una decisione architetturale da chiudere.
- Nessun nuovo TODO verra aggiunto fuori da questa struttura.
