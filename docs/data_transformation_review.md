# Revisione pipeline di trasformazione dati (v1.0 Beta)

Nel contesto di Timmy-KB come ambiente di creazione e governo, questa review descrive strumenti specifici della pipeline di fondazione mantenuti entro l’envelope epistemico e soggetti a Human-in-the-Loop.

## Stato attuale
- **Vision  mapping**: `semantic.vision_provision.provision_from_vision` continua a orchestrare l'impaginazione dal VisionStatement e produce `semantic_mapping.yaml` e `cartelle_raw.yaml`.
- **Conversione RAW  Markdown**: `semantic.convert_service.convert_markdown` converte i PDF in `.md` con frontmatter semplificato e ora inserisce un `excerpt` estratto dal PDF, mantenuto da cache per evitare riscritture inutili, oltre a lasciare il placeholder contestuale per la tracciabilita.
- **Pipeline unificata libro**: `semantic.api.build_markdown_book` esegue conversione, arricchimento frontmatter, README/SUMMARY e, aggiunta di questa iterazione, scrive un file `semantic/layout_proposal.yaml` derivato da `layout_enricher`.
- **Frontmatter & layout**: i `.md` ora includono il campo `layout_section` dedotto dalla proposta ER, e la UI documenta i top-level suggeriti aggiungendo una nota nel README generato.
- **Pubblicazione GitBook/Drive**: ora scriviamo anche `book/layout_summary.md` con i top-level suggeriti, cosi la preview GitBook/Drive puo leggere direttamente la proposta ER e infrastruttura di cartelle.
- **Automazione GitBook**: `onboarding_full.py` tenta ora un upload automatico usando `GITBOOK_TOKEN` + `GITBOOK_SPACE_ID`, caricando il contenuto di `book/` (zip) e allegando la summary per guidance di layout.
- **Codici documentali**: i prefissi (PRJ-, ORG-, CTR-, DEC-, ...) sono parte del layer semantico; il mapping `entity_to_document_type` vive in `semantic/semantic_mapping.yaml` e guida layout, frontmatter ed embedding.

## Gap mitigati
- Il contenuto Markdown ora contiene un estratto reale dal PDF (se disponibile), quindi il corpo non e piu solo un placeholder.
- E stata introdotta una proposta ER persistente (`semantic/layout_proposal.yaml`) che conserva la struttura suggerita da `layout_enricher`, pronta per essere utilizzata dalla UI o ad ulteriori arricchimenti.

## Prossimi passi
- Validare le integrazioni di README/SUMMARY con la nuova proposta ER, assicurandosi che i file client (PDF/README cartella) siano sincronizzati con la struttura `layout_proposal`.
- Collegare la proposta ER alla generazione di tag/entita (frontmatter) e automatizzare la pubblicazione su GitBook/Drive, mantenendo i controlli di path-safety e scritture atomiche.
