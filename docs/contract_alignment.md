# Contract Alignment Notes

Questo documento non introduce nuove regole: riallinea la descrizione di runtime ai contratti già in essere nel MANIFEST e nelle `instructions/` (in caso di conflitto prevalgono i documenti di livello più alto). Riporta solo ciò che il runtime fa oggi, senza proposte creative.

Per allineare la documentazione ai comportamenti reali del runtime (no silenziosi downgrade, contratti testabili), registriamo qui i mismatch risolti:

1. **db_path è sempre esplicito/assoluto.** `QueryParams` ora documenta che `db_path` non può essere `None` e deve derivare da `WorkspaceLayout`/`ClientContext`; `storage.kb_db._resolve_db_path` e `KbStore` lo richiedono effettivamente (no fallback su `None`, `kb.sqlite` globale o path relativo).  
2. **KB DB init fallisce su duplicati.** L’indice UNIQUE non fa “warn and continue”, ma genera un `ConfigError` che obbliga a rigenerare il DB, come chiarito nel commento che segue la creazione dell’indice.  
3. **_load_env espone valori testuali.** Il contesto restituisce stringhe raw (anche per `CI`, `LOG_REDACTION`, ecc.); se un flag deve essere booleano, la conversione viene fatta dal caller che ha il contesto operativo.  
4. **RawTransformService segnala fallimenti con eccezioni.** La docstring ora specifica che `FAIL` non viene mai restituito; in caso di errore viene sollevato `PipelineError`, mentre `SKIP` indica formati non supportati e `OK` il flusso riuscito.

Queste note servono a documentare i vincoli smistati tra codice e contratti (Beta 1.0: determinismo, fail-fast, nessun fallback implicito). Ogni modifica futura che tocchi uno di questi punti deve riportare il relativo aggiornamento qui.

Change discipline: ogni modifica che altera una di queste garanzie deve aggiornare anche questa nota e i docstring/commenti associati.
