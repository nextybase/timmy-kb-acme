# Scopo

Regole per l’area AI (`src/ai/`), con focus su integrazione OpenAI/SDK, SSoT di configurazione e separazione netta tra infrastruttura e logica applicativa.

# Regole (override)

- Tutte le integrazioni con l’SDK OpenAI passano da `ai.client_factory.make_openai_client()`;
  è vietato istanziare `OpenAI()` o usare direttamente il modulo `openai` al di fuori di `src/ai/`.
- I parametri di timeout, retry e http2 devono essere letti solo tramite `Settings`
  (`config/config.yaml`, sezione `ai.openai.*`), mentre i segreti restano in `.env`
  (`OPENAI_API_KEY` e affini), in coerenza con la separazione config/segreti del runbook.
- I moduli in `src/ai/` non contengono prompt-engineering o regole di business:
  niente system prompt, template testuali o concatenazione di messaggi modello;
  qui vivono solo factory, wiring dei client e gestione tecnica delle chiamate.
- Il logging usa sempre `pipeline.logging_utils.get_structured_logger("ai.<sottoambito>")`;
  nessun `print()`, nessun side-effect a import-time.
- Nuovi client (Vision, tool, provider esterni) seguono lo stesso pattern:
  factory centralizzata, configurazione letta da `Settings`, path-safety/I/O delegati alle
  utility SSoT di pipeline (`ensure_within*`, `safe_write_*`).

# Criteri di accettazione

- Non esistono nel repository istanze di `OpenAI(` o uso diretto di `openai.*`
  al di fuori di `src/ai/`.
- Le chiamate ai modelli rispettano la configurazione definita in `config/config.yaml`
  (timeout, retry, http2) e falliscono in modo controllato tramite eccezioni di
  configurazione dedicate e logging strutturato.
- Nessuna logica di prompt o di dominio appare in `src/ai/`: i diff mostrano solo
  modifica/estensione di factory, parametri tecnici o wiring dei client.

# Riferimenti

- `docs/AGENTS_INDEX.md`
- `docs/runbook_codex.md`
- `docs/codex_integrazione.md`
- `src/ai/client_factory.py`
