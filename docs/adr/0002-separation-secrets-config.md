# 0002  Separare segreti da configurazione applicativa

## Stato
Accepted  25/10/2025

## Contesto
- Le pipeline Timmy-KB richiedono sia **valori sensibili** (token, API key, ID assistant) sia **parametri di business/UX** (modello da usare, soglie retriever, preferenze UI).
- Storicamente alcuni progetti duplicavano i valori in `config/config.yaml`, con conseguente rischio di commit di credenziali e incoerenze fra `.env` e YAML.
- La manutenzione di test e UI risultava fragile (varie componenti leggevano `.env` o YAML in modo diretto).

## Decisione
1. I **segreti vivono soltanto nel `.env`** (o in un vault esterno).
   Il codice non puo serializzarli nei config YAML.
2. `config/config.yaml` rimane la SSoT per le impostazioni applicative e contiene solo riferimenti `_env` ai segreti.
3. `pipeline.settings.Settings` diventa l'unico entrypoint di lettura:
   - espone accessor tipizzati;
   - fornisce `resolve_env_ref` e `get_secret`;
   - offre un catalogo centralizzato di variabili attese (`env_catalog()`).
4. Hook statici (`no-secrets-in-yaml`) in pre-commit + CI bloccano commit con chiavi/valori sensibili nei YAML.
5. La UI espone due pagine dedicate:
   - **Config Editor** (solo impostazioni applicative);
   - **Secrets Healthcheck** (stato delle ENV senza mostrare i valori).

## Trade-off
-  **Sicurezza**: niente segreti nel repository, verifica automatica in CI.
-  **DX**: `Settings` uniforma l'accesso a config/env; i test possono usare marker dedicati.
-  **Overhead**: chi modifica parametri deve aggiornare sia YAML sia `.env` (ma con tooling guidato).
-  **Compatibilita**: i consumer legacy devono passare dal wrapper (`ClientContext.settings`), pena failure dei nuovi test.

## Conseguenze
- Nuova documentazione: [docs/configurazione.md](../configurazione.md) e sezione "Settings & guard segreti" nella test suite.
- Test mirati (`pytest -m "settings or pipeline or ui or semantic"`) garantiscono che pipeline/semantic/UI usino `Settings`.
- Il comando `pre-commit run no-secrets-in-yaml --all-files` diventa parte del flusso locale; la CI fallisce se trova valori inline.
- Miglior DX Streamlit: gli operatori possono diagnosticare le ENV mancanti senza vedere i segreti.

## Collegamenti
- Hook e script: `scripts/dev/check_yaml_secrets.py`, `.pre-commit-config.yaml`.
- UI: `src/ui/pages/config_editor.py`, `src/ui/pages/secrets_healthcheck.py`.
