# Contributing  Timmy-KB

Questa guida stabilisce come contribuire al progetto Timmy-KB. Ogni modifica al codice o alla documentazione deve mantenere **coerenza, stabilita e tracciabilita**. Le regole qui indicate sono vincolanti per pull request, issue e revisioni.

---

## 1) Workflow

- **Branch model**: sviluppo su branch dedicati, PR verso `main`.
- **Naming branch**: `feature/<slug>`, `fix/<slug>`, `docs/<slug>`.
- **PR obbligatorie**: ogni modifica deve passare revisione.
- **CI/CD**: i test devono superare senza errori prima del merge.

---

## 2) Stile e coerenza

- Seguire le [Coding Rules](docs/developer/coding_rule.md).
- Tipizzazione obbligatoria, docstring brevi, logger strutturati.
- Nessun `print()`, nessuna variabile d'ambiente hardcoded.
- Aggiornare sempre documentazione correlata (README, docs/).

---

## 3) Commit e changelog

- Commit **atomici**, messaggi chiari e al presente.
- Formato consigliato: `<tipo>(<scope>): descrizione`.
  - Tipi: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Ogni PR che modifica logica deve aggiornare `CHANGELOG.md`.
- Seguire [Versioning Policy](docs/policies/versioning_policy.md).

---

## 4) Issue e revisioni

- Ogni issue deve avere titolo descrittivo e label.
- Le PR devono collegarsi a issue (quando esistono).
- I reviewer devono verificare:
  - Rispetto delle regole di codifica.
  - Assenza di regressioni.
  - Documentazione aggiornata.

---

## 5) Documentazione

- Ogni modifica tecnica richiede aggiornamento coerente di:
  - `README.md`
  - `docs/user/user_guide.md`
  - `docs/developer/developer_guide.md`
  - `system/architecture.md`
  - `docs/developer/coding_rule.md`
- La documentazione e **bloccante** per il merge.

---

## 6) Note finali

- In caso di dubbio, aprire prima una **discussion**.
- Le modifiche devono essere **retro-compatibili** salvo pianificato diversamente.
- La qualita del codice e la coerenza con le guide valgono quanto la funzionalita stessa.
- Tutti i contributori devono attenersi a [LICENSE](LICENSE.md), [Code of Conduct](CODE_OF_CONDUCT.md) e [Security Policy](SECURITY.md).

# Dependency Updates (Dependabot) - Beta 1.0 Policy

Durante la fase Beta 1.0 adottiamo una strategia di aggiornamenti piccoli e continui,
per evitare accumulo di debito tecnico senza introdurre entropia nel sistema.

## Ritmo

- 1 maintenance slot fisso a settimana (30-60 min)
- Max 2 PR Dependabot mergiate per slot

## Regole di merge (hard constraints)

Una PR Dependabot può essere mergiata solo se:

- CI completamente verde (python -m pytest -q)
- 1 dipendenza per PR (no batch)
- Nessun breaking change dichiarato nelle release notes

## Priorità (ordine)

1. **Security patch** (sempre prima)
2. Tooling/dev-only (
uff, pre-commit, 	ypes-*)
3. Runtime sensibili (pydantic, openai, protobuf, ...) solo se delta minimo

## Guardrail anti-entropia

- Mai mergiare più PR insieme  in blocco
- Se una PR rompe anche un solo test: si rimanda o si chiude
- Non si fanno fix al volo nello stesso slot (slot ? progetto)

## Labels consigliate

- deps:security
- deps:tooling
- deps:runtime

## Auto-merge (opzionale)

Consentito solo per PR di tooling con CI verde.
Le dipendenze runtime richiedono sempre review umana.
