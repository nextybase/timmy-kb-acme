# Versioning Policy — Timmy-KB (v1.2.0)

Questa policy definisce le regole di versioning per la pipeline Timmy-KB. L’obiettivo è garantire stabilità, compatibilità e chiarezza evolutiva per sviluppatori e utenti.

---

## 1) Schema di versioning (SemVer)

La pipeline adotta **Semantic Versioning (SemVer 2.0.0)**:

- **MAJOR (X.0.0)** → cambi incompatibili con versioni precedenti (breaking changes).
- **MINOR (0.Y.0)** → nuove funzionalità retro-compatibili.
- **PATCH (0.0.Z)** → fix e refactor senza modifiche API/CLI.

---

## 2) Regole pratiche

- Ogni orchestratore ha API/CLI stabili all’interno della stessa **MINOR**.
- I moduli interni possono cambiare senza bump **MAJOR**, se non rompono orchestratori/API pubbliche.
- Gli helper privati non hanno garanzia di stabilità.

---

## 3) Tag e release

- Ogni rilascio è taggato in Git (`vX.Y.Z`).
- Il changelog descrive:
  - **Added** (nuove feature)
  - **Changed** (modifiche retro-compatibili)
  - **Fixed** (bugfix)
  - **Removed** (solo in MAJOR)
- Ogni PR che impatta API/CLI deve aggiornare `CHANGELOG.md`.

---

## 4) Compatibilità CLI

- Nessun breaking in PATCH.
- Le opzioni CLI rimosse/deprecate richiedono un ciclo di almeno una MINOR prima della rimozione effettiva.
- Default invariati salvo bump MAJOR.

---

## 5) Policy di documentazione

- Ogni release MINOR/MAJOR deve aggiornare:  
  - `docs/architecture.md`  
  - `docs/developer_guide.md`  
  - `docs/coding_rules.md`  
  - `docs/user_guide.md`  
  - `docs/policy_push.md`  
  - `docs/versioning_policy.md`
- PATCH: aggiornamento documentazione solo se impatta comportamenti visibili.

---

## 6) Roadmap stabilità

- **v1.x** → fase stabile, garantita compatibilità CLI.  
- **v2.0.0** → eventuale revisione architetturale e nuove API pubbliche.
