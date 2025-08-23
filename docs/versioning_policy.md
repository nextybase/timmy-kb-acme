# Versioning Policy — Timmy-KB (v1.1.0)

Questa policy definisce come versionare il progetto Timmy-KB, seguendo lo schema **Semantic Versioning (SemVer)** adattato al contesto della pipeline. L’obiettivo è garantire chiarezza, prevedibilità e compatibilità retroattiva ove possibile.

---

## 1) Regole di versionamento

- **MAJOR (X.0.0)** — Cambiamenti incompatibili (breaking changes).
- **MINOR (0.Y.0)** — Nuove funzionalità mantenendo la compatibilità.
- **PATCH (0.0.Z)** — Correzioni di bug e refactor interni senza modifiche di UX o API pubbliche.

### Estensioni locali

- La pipeline può adottare un SemVer **leggero**: per refactor/documentazione si aggiorna comunque il numero di PATCH.
- I suffissi `-beta`, `-rc`, ecc. indicano versioni pre-release.

---

## 2) CHANGELOG

- Ogni modifica **rilevante** deve essere documentata in `CHANGELOG.md`.
- Formato di riferimento: [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
- Sezioni standard: **Added, Changed, Fixed, Security, Deprecated, Removed, Notes**.
- Le modifiche interne di refactor vanno comunque tracciate.

---

## 3) Allineamento documentazione

- Ogni nuova release deve aggiornare:
  - `README.md` → quickstart e note utente.
  - `docs/user_guide.md` → UX e CLI.
  - `docs/developer_guide.md` → scelte architetturali/refactor.
  - `docs/architecture.md` → struttura e API interne.
  - `docs/coding_rule.md` → regole operative.
- Il **CHANGELOG** rappresenta la fonte unica di verità temporale delle modifiche.

---

## 4) Note operative

- In caso di rilascio **incompleto**, aggiungere suffisso `-dev` o `-draft`.
- La data di rilascio va sempre riportata accanto alla versione.
- I tag Git devono coincidere con la versione (es. `v1.1.0`).
- In CI/CD le release stabili sono marcate su branch `main`.

---

## 5) Compatibilità retroattiva

- Nessuna rimozione immediata di CLI o flag: introdurre **avvisi di deprecazione** e rimuovere solo in release MAJOR.
- Gli orchestratori mantengono la compatibilità verso CLI storiche, con warning.

---

## 6) Versione corrente

- **Versione:** 1.1.0 (Stable)
- **Data:** 23 Agosto 2025
- **Note:** prima base stabile.

