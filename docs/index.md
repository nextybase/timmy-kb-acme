## <a name="docsindex.md"></a>docs/index.md
# <a name="xe09dcdb8fbc9c1f9794ebbaed8d0b414460c30b"></a>Documentazione Timmy-KB – Versione 1.0.5 (Stable)
Benvenuto nella documentazione ufficiale di **Timmy-KB**, organizzata per fornire una panoramica chiara e navigabile delle funzionalità, dell’architettura e delle regole di sviluppo del progetto.

-----
## <a name="indice-dei-documenti"></a>📚 Indice dei documenti
### <a name="architettura-e-struttura-tecnica"></a>1. Architettura e Struttura Tecnica
- [Architettura tecnica](architecture.md) → Panoramica del sistema, flusso degli orchestratori, funzioni chiave e struttura dei dati.
### <a name="sviluppo-e-standard"></a>2. Sviluppo e Standard
- [Guida sviluppatore](developer_guide.md) → Struttura del repository, principi architetturali e flussi di lavoro.
- [Regole di codifica](coding_rule.md) → Convenzioni, standard di scrittura del codice, sicurezza e principi NeXT.
### <a name="utilizzo-e-operatività"></a>3. Utilizzo e Operatività
- [Guida utente](user_guide.md) → Installazione, esecuzione pipeline (pre-onboarding e onboarding completo), output e troubleshooting.
### <a name="policy-e-governance-documentale"></a>4. Policy e Governance Documentale
- [Policy di push](policy_push.md) → Quando pubblicare, quando usare --no-push, uso consapevole di --force e coerenza con GIT_DEFAULT_BRANCH.
- [Versioning](versioning_policy.md) → Regole di versionamento (SemVer leggero), tag di rilascio e aggiornamento contestuale del CHANGELOG.
-----
## <a name="come-usare-questa-documentazione"></a>🔍 Come usare questa documentazione
1. **Per iniziare** – leggi la [Guida utente](user_guide.md) per capire come installare e avviare Timmy-KB.
2. **Per contribuire** – consulta la [Guida sviluppatore](developer_guide.md) e le [Regole di codifica](coding_rule.md) prima di aprire una Pull Request.
3. **Per comprendere il funzionamento interno** – approfondisci l’[Architettura tecnica](architecture.md).
4. **Per pubblicare correttamente** – verifica la [Policy di push](policy_push.md) e la [Versioning](versioning_policy.md) prima di effettuare rilasci o push forzati.

> **Nota sul pre-onboarding (comportamento reale):** non sono previsti **prompt di conferma** per la creazione della struttura locale o per le operazioni su Drive. Se le variabili Drive **mancano** e non usi `--dry-run`, l’orchestratore termina con **ConfigError**. Usa `--dry-run` per preparare solo l’ambiente locale.

-----
## <a name="versione-attuale"></a>📅 Versione attuale
- **Versione:** 1.0.5 Stable
- **Data rilascio:** 19 Agosto 2025
- **Stato:** Documentazione aggiornata e allineata al CHANGELOG **1.0.5**.
### <a name="note-su-questa-versione"></a>Note su questa versione
- **Strumenti CLI potenziati:** `refactor_tool.py` supporta la modalità “Trova” (solo ricerca di occorrenze, senza modifica automatica); `cleanup_repo.py` è ora sempre interattivo, con opzioni avanzate (inclusa eliminazione del repo remoto via `gh`) e conferma finale; `gen_dummy_kb.py` allineato al comportamento del repository (slug fisso `dummy`, struttura generata da YAML, fallback a `.txt` se `fpdf` non disponibile).
- **Script obsoleti rimossi:** eliminato `validate_structure.py` (funzionalità integrate altrove).
- **Pipeline invariata:** nessuna modifica ai flussi di pre-onboarding/onboarding rispetto alla 1.0.4 (patch di mantenimento completamente retro-compatibile).

-----
## <a name="note-finali"></a>📌 Note finali
- Tutti i file `.md` nella cartella `docs/` vengono mantenuti aggiornati in parallelo all’evoluzione del codice.
- Ogni modifica al codice che impatta il comportamento **deve** essere accompagnata da un aggiornamento coerente della documentazione (in `docs/` e nel `README.md`).