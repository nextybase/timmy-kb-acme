# Official Actions Tag Policy

Codex releases devono affidarsi a **tag stabili** per le GitHub Actions ufficiali (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`, `actions/setup-node`, ecc.).

- **Regola fondamentale**: mai pinnare a SHA commit specifici per le action ufficiali. Un tag stabile (`v4`, `v5`, `v4.4.3`, ...) garantisce compatibilità e usabilità dei workflow da GitHub.
- **Quando si può usare uno SHA?** Solo per action di terze parti (non `actions/*`) o mirror interno controllato. In quei casi la scelta deve essere giustificata nel file YAML/commento associato.
- **Chi legge:** i maintainer e gli automation engineer che aggiornano `.github/workflows`. Questa policy può essere richiamata in PR quando si modifica un workflow.

Documentare questa regola evita future regressioni simili a `actions/checkout@<sha>` che falliscono quando il commit viene rimosso dai mirror di GitHub.
