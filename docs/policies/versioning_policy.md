# Policy di Versioning - Timmy-KB (v1.0 Beta)

Questa policy definisce come versioniamo il codice, etichettiamo le release e gestiamo la compatibilita.

## 1) Schema: SemVer

Usiamo SemVer `MAJOR.MINOR.PATCH`:

- PATCH: bugfix/refactor compatibili (es. 1.2.0  1.2.1)
- MINOR: nuove feature retro-compatibili (es. 1.2.1  1.3.0)
- MAJOR: cambi API o comportamenti non compatibili (es. 1.3.0  2.0.0)

### Regole pratiche
- In PATCH non cambiare default, firme pubbliche o comportamento di CLI compatibile.
- In MINOR puoi aggiungere opzioni e moduli, mantenendo i vecchi percorsi.
- In MAJOR e consentita la rimozione di opzioni/percorsi e la modifica dei contratti.

## 2) Tagging Git

- Ogni release viene taggata come: `vMAJOR.MINOR.PATCH` (es. `v1.2.1`).
- Il tag referenzia una commit in `main` (o `GIT_DEFAULT_BRANCH`).
- Il changelog (`CHANGELOG.md`) deve essere aggiornato contestualmente al tag.

## 3) Branching

- main: stabile, sempre rilasciabile (protetto).
- feat/*: feature branch
- fix/*: bugfix
- docs/*: aggiornamenti documentazione
- hotfix/*: patch urgenti su `main`

PR obbligatorie verso `main`. Protezioni:
- Require status checks (lint/test base)
- Require linear history (no merge commit, preferisci squash)

## 4) compatibilita & Deprecazioni

- Ogni breaking change richiede:
  - incremento MAJOR
  - nota in CHANGELOG
  - piano di migrazione (se rilevante)
- Deprecazioni:
  - annuncio in MINOR N
  - rimozione in MAJOR N+1

## 5) Versioni dei documenti

- `system/architecture.md`
- `docs/user/user_guide.md`
- `docs/developer/developer_guide.md`
- `docs/developer/coding_rule.md`
- Nessuna policy di rilascio esterno attiva.
- `versioning_policy.md`
- `CHANGELOG.md`

## 6) Rilascio tipico

1. Verifica lint/test e guide aggiornate.
   - **Prerequisito runtime (Beta 1.0):** Responses richiede `output_text` dal client OpenAI.
     Assicurare SDK OpenAI pin/compatibile con l'API Responses e il campo `output_text`.
2. Aggiorna `CHANGELOG.md`.
3. Bump versione nei doc.
4. Merge in `main`.
5. Crea il tag `vX.Y.Z` e sincronizzalo con origin.

## 7) Allineamento orchestratori per v1.2.1

- Facade `semantic.api` (conversione/enrichment/preview) come SSoT; e disponibile un thin wrapper CLI `timmy_kb.cli.semantic_onboarding` che richiama la facade per simmetria con gli altri orchestratori.
- Ridotto: preview locale gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).
- SSoT: `ensure_within` in `pipeline.path_utils`.

Queste modifiche sono retro-compatibili a livello di CLI (MINOR  1.2.x), con breaking nullo lato utente.

## Enforcement & References

- **Enforcement:**
  - Git workflow e branching descritti qui (processo repo).
  - Tagging e release su `main` con aggiornamento `CHANGELOG.md`.
  - PR review e status checks richiesti su `main`.
- **References:**
  - [Coding Rules](../developer/coding_rule.md#10-git--pr-policy)
  - [CHANGELOG.md](../../CHANGELOG.md)
