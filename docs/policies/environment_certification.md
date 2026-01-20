# Environment Certification Policy

Status: draft  
Owner: Team C

## Scopo
Definire cosa significa "ambiente certificato" per questa repo e quando una run
puo' dichiararsi conforme, garantendo determinismo operativo e auditabilita'.

## Definizioni
- **Ambiente certificato:** stack software, configurazione e dipendenze
  verificate e coerenti con la policy Beta; nessun fallback silenzioso o shim.
- **Run conforme:** esecuzione che rispetta i requisiti minimi, fallisce in modo
  hard su non conformita', e produce evidenze verificabili.

## Scope: pipeline semantica
Questa policy si applica alle esecuzioni CLI dei seguenti entrypoint:
- `src/timmy_kb/cli/tag_onboarding.py` (orchestrator tagging; modalita' strict
  con `TIMMY_BETA_STRICT`, flag `--nlp`, pipeline entities opzionale).
- `src/timmy_kb/cli/semantic_headless.py` (pipeline RAW->BOOK con 4 step:
  `convert_markdown`, `require_reviewed_vocab`, `enrich_frontmatter`,
  `write_summary_and_readme`; `bootstrap_config` esplicito, default vietato).

## Requisiti minimi (ambiente certificato)
- Versioni e dipendenze devono essere fissate e riproducibili (venv dedicato,
  lock o requirements coerenti con il repo).
- `TIMMY_BETA_STRICT` deve essere allineato alla modalita' richiesta dalla run.
- Nessun comportamento best-effort o fallback che modifichi l'output tra macchine.
- Se `source=drive`, l'ambiente deve includere l'extra `.[drive]` e le variabili
  `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`; in assenza la run deve fallire.
- I backend NLP effettivi (spaCy/sentence-transformers se usati) devono avere
  versioni note e registrate.

## Non conformita' (errori)
Esempi che devono produrre FAIL HARD in modalita' certificata:
- **Drive missing:** `source=drive` ma extra `.[drive]` o env var mancanti.
- **Strict disallineato:** `TIMMY_BETA_STRICT` non coerente con la modalita'
  richiesta dalla run o dal workflow.
- **Bootstrap implicito:** avvio di `semantic_headless` con `bootstrap_config`
  non esplicito o con default vietato.
- **Preview/placeholder headless:** qualsiasi comportamento che sostituisce
  output reali con placeholder o preview e che possa alterare gli artefatti.

## Verifiche e controlli
- La configurazione cliente e la repo config devono essere accessibili e valide.
- La presenza di extra e credenziali deve essere verificata prima dell'esecuzione.
- Le versioni di runtime (Python, pacchetti chiave) devono essere coerenti con il
  baseline di certificazione dichiarato per il repo.

## Evidence & Auditability
Ogni run conforme deve produrre metadati osservabili in log strutturati e/o in
`ledger` (es. `evidence_json`), includendo almeno:
- `TIMMY_ENV`, `TIMMY_BETA_STRICT`, e modalita' esecuzione.
- hash del codice (commit SHA) e hash della config cliente usata.
- backend NLP effettivo e versioni (spaCy, sentence-transformers se pertinenti).
- modello AI/embedding effettivo e versione (se usato).
- capability attive (es. Drive) e relativa disponibilita'.

## Responsabilita'
- **Operatori:** assicurano che i prerequisiti siano presenti e coerenti.
- **Maintainers:** definiscono il baseline certificato e aggiornano questa policy
  quando cambiano dipendenze o requisiti di esecuzione.

## Checklist pre-run (manuale)
- [ ] Venv dedicato attivo e dipendenze allineate al repo.
- [ ] `TIMMY_BETA_STRICT` impostato e coerente con la run.
- [ ] Config cliente presente e valida (hash calcolabile).
- [ ] `bootstrap_config` esplicito per `semantic_headless`.
- [ ] Se `source=drive`: extra `.[drive]` installato.
- [ ] Se `source=drive`: `SERVICE_ACCOUNT_FILE` e `DRIVE_ID` disponibili.
- [ ] Versioni backend NLP note e registrabili.
- [ ] Commit SHA corrente registrabile.
