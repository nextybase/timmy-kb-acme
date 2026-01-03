# Explainability end-to-end (ingest -> semantic -> retriever -> manifest)

Questa pagina riassume il flusso di explainability introdotto.

## Percorso dati
- **Ingest/Semantic**: ogni chunk porta `meta["lineage"]` con `source_id` e `chunk_id`/`path`; log canonici `semantic.input.received`, `semantic.lineage.chunk_created`, `semantic.lineage.embedding_registered`.
- **Retriever**: usa le embedding dal DB; eventi `retriever.query.*`, `retriever.candidates.fetched`, `retriever.evidence.selected` raccontano query, fetch e top-k (solo ID e score).
- **Manifest di risposta**: struttura per-risposta (`response_id.json`) con query, parametri, evidence (rank/score/source_id/chunk_id/snippet opzionale), metrics e flags.
- **ExplainabilityService**: arricchisce il manifest con path/version/chunk_index dal DB e con eventi semantic*/retriever* catturati, producendo l'Explainability Packet.

## Output/artefatti
- `retriever.response.manifest` (log): path locale del manifest e lista sintetica delle evidenze (niente snippet/testo).
- Manifest JSON salvato con `safe_write_manifest` (scrittura atomica, path-safe).
- Packet finale (in memoria) pronto per UI/CLI/Assistant.

## Privacy & safety
- I log non includono snippet o testo query; gli snippet restano solo nel manifest locale.
- Nessuna modifica allo schema DB; lookup lineage solo read-only via `fetch_candidates`.
- Scritture manifest atomiche nel workspace scelto; nessun side-effect a import.
