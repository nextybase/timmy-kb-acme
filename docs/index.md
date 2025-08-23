# Documentazione Timmy-KB – Versione 1.1.0 (Stable)

Benvenuto nella documentazione ufficiale di **Timmy-KB**, organizzata per fornire una panoramica chiara e navigabile delle funzionalità, dell’architettura e delle regole di sviluppo del progetto.

---

## 📚 Indice dei documenti

### 1. Architettura e Struttura Tecnica
- [Architettura tecnica](architecture.md) → Panoramica del sistema, flusso degli orchestratori, funzioni chiave e struttura dei dati.

### 2. Sviluppo e Standard
- [Guida sviluppatore](developer_guide.md) → Struttura del repository, principi architetturali e flussi di lavoro.
- [Regole di codifica](coding_rule.md) → Convenzioni, standard di scrittura del codice, sicurezza e principi NeXT.

### 3. Utilizzo e Operatività
- [Guida utente](user_guide.md) → Installazione, esecuzione pipeline (pre-onboarding, tag-onboarding e onboarding completo), output e troubleshooting.

### 4. Policy e Governance Documentale
- [Policy di push](policy_push.md) → Quando pubblicare, quando usare `--no-push`, uso consapevole di `--force` e coerenza con `GIT_DEFAULT_BRANCH`.
- [Versioning](versioning_policy.md) → Regole di versionamento (SemVer leggero), tag di rilascio e aggiornamento contestuale del CHANGELOG.

---

## 🔍 Come usare questa documentazione

1. **Per iniziare** – leggi la [Guida utente](user_guide.md) per capire come installare e avviare Timmy-KB.
2. **Per contribuire** – consulta la [Guida sviluppatore](developer_guide.md) e le [Regole di codifica](coding_rule.md) prima di aprire una Pull Request.
3. **Per comprendere il funzionamento interno** – approfondisci l’[Architettura tecnica](architecture.md).
4. **Per pubblicare correttamente** – verifica la [Policy di push](policy_push.md) e la [Versioning](versioning_policy.md) prima di effettuare rilasci o push forzati.

> **Nota sul pre-onboarding (comportamento reale):** non sono previsti **prompt di conferma** per la creazione della struttura locale o per le operazioni su Drive. Se le variabili Drive **mancano** e non usi `--dry-run`, l’orchestratore termina con **ConfigError**. Usa `--dry-run` per preparare solo l’ambiente locale.

> **Nota sul tag-onboarding:** questa fase è stata introdotta per scaricare i PDF in `raw/`, estrarre i tag semantici e generare i file `tags_raw.csv`, `tags_reviewed.yaml` e `tags.yaml`. È un passaggio intermedio tra pre-onboarding e onboarding completo, ed è richiesto per l’arricchimento del frontmatter dei Markdown.

---

## 📅 Versione attuale

- **Versione:** 1.1.0 Stable
- **Data rilascio:** 23 Agosto 2025
- **Stato:** Documentazione aggiornata e allineata al CHANGELOG **1.1.0**.

---

## 📌 Note finali

- Tutti i file `.md` nella cartella `docs/` vengono mantenuti aggiornati in parallelo all’evoluzione del codice.
- Ogni modifica al codice che impatta il comportamento **deve** essere accompagnata da un aggiornamento coerente della documentazione (in `docs/` e nel `README.md`).

