# Architettura — Aggiornamento Fase 1 (redazione e contesto)

Queste note aggiornano l’architettura a valle della Fase 1. Non ci sono modifiche a UX o flussi.

---

## Policy di redazione log

- **Decisione canonica** in `env_utils.compute_redact_flag(env, log_level)`.
- La redazione è **OFF** in `DEBUG`, **ON** se `LOG_REDACTION=on|always|true`, **OFF** se `off|never|false`.  
  Con `auto` (default), è **ON** se `ENV ∈ {prod, production, ci}` **o** `CI=true` **o** sono presenti credenziali (`GITHUB_TOKEN`/`SERVICE_ACCOUNT_FILE`).
- `is_log_redaction_enabled(context)` rimane **solo** per retro‑compat; da non usare nelle nuove parti.

## ClientContext e helper interni

`ClientContext.load(...)` è scomposto in helper (stesso modulo):
- `_init_logger`, `_init_paths`, `_load_yaml_config`, `_load_env`
- calcolo redazione delegato a `compute_redact_flag`

**Obiettivo**: ridurre complessità, facilitare unit test e mantenere API/pubbliche stabili.

## Compatibilità

- Nessun cambiamento ai moduli orchestratori, né ai contratti pubblici.
- Log strutturati invariati; migliorata la leggibilità del codice e la separazione delle responsabilità.
