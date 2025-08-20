-----
## <a name="docsversioning_policy.md"></a>docs/versioning_policy.md
# <a name="xbee3289fe311ce2d709c6c5d8ccc547ca0b2e9e"></a>Versioning & Release Policy – Timmy‑KB (v1.0.5 Stable)
Questa policy descrive **come versioniamo** il progetto e **come gestiamo i rilasci**. È allineata alla versione 1.0.5 e alle pratiche introdotte nelle ultime patch. L’obiettivo è evitare rotture non intenzionali e mantenere la documentazione sempre coerente con il codice ad ogni release.

-----
## <a name="obiettivi"></a>1) Obiettivi
- **Stabilità dei flussi** – Le interfacce degli orchestratori e i comportamenti base non devono cambiare in modo inaspettato per gli utenti finali se non in major release pianificate.
- **Tracciabilità delle modifiche** – Ogni cambiamento rilevante deve essere documentato (CHANGELOG obbligatorio per ogni release). Questo aiuta i manutentori e gli utenti avanzati a capire cosa è cambiato.
- **Allineamento codice-doc** – Qualsiasi modifica al comportamento o alle API deve essere accompagnata, nella **stessa PR**, da aggiornamenti alla documentazione (docs/ e README.md). Codice e doc viaggiano insieme, così che la versione rilasciata abbia sempre documentazione aggiornata.
-----
## <a name="schema-di-versioning-semver-leggero"></a>2) Schema di versioning (SemVer “leggero”)
Usiamo un approccio ispirato a [Semantic Versioning](https://semver.org/) ma tarato per un’applicazione CLI interna:

- **MAJOR (X.0.0)** – cambiamenti **incompatibili** per l’utente o le integrazioni. Esempi: rimozione di flag CLI o opzioni, modifica del flusso degli orchestratori, ristrutturazione della struttura di output. Queste versioni richiedono particolare attenzione nella comunicazione e spesso includono note di migrazione.
- **MINOR (X.Y.0)** – nuove funzionalità **retro‑compatibili**. Esempi: aggiunta di nuovi flag o variabili d’ambiente (senza cambiare i default esistenti), ottimizzazioni o modifiche non disruptive (es. anteprima migliorata, nuovi controlli, logging arricchito). Possono deprecare funzionalità vecchie ma le mantengono compatibili fino alla major successiva.
- **PATCH (X.Y.Z)** – bugfix, refactor interni, pulizia di script e documentazione **senza impatto sul flusso**. Esempio: correzione di messaggi di log, miglioramenti di resilienza, divisione del codice in moduli senza cambiare il comportamento esterno, aggiornamento documentazione per riflettere accuratamente lo stato del codice. Le patch **non devono introdurre rotture** né richiedere azioni agli utenti.

Esempio concreto: la **1.0.3** è stata una release di tipo **PATCH** che ha principalmente rimosso print() dagli orchestratori in favore del logger, ripulito la gestione dell’anteprima e allineato la documentazione, senza modificare come si usa la pipeline (nessun flag nuovo o rimosso, nessun cambiamento di default).

-----
## <a name="criteri-pratici-per-il-bump"></a>3) Criteri pratici per il bump
Alcune linee guida su come decidere la nuova versione quando si introduce un cambiamento:

- Stai per **aggiungere un flag CLI** (o parametro) nuovo, mantenendo i comportamenti di default invariati → incrementa la **MINOR** (funzionalità aggiunta retrocompatibile).
- Hai deciso di **deprecare** un flag esistente (es. supporti ancora --skip-drive ma avvisi che è deprecato a favore di --no-drive) → anche questo è un aggiustamento **MINOR** (feature ancora supportata ma contrassegnata come in via di eliminazione).
- Hai rimosso effettivamente un flag o una funzionalità precedentemente deprecata → questo è un cambiamento **MAJOR**, perché potenzialmente rompe gli script degli utenti. Assicurati di aver comunicato la deprecazione almeno una minor release prima.
- Hai modificato il **comportamento di default** di un comando (es. decidiamo che di default il push avvenga sempre, invertendo la logica attuale) → questo è un cambiamento **MAJOR** perché utenti senza modificare nulla otterrebbero un comportamento diverso.
- Stai facendo solo modifiche interne (refactoring, migliorando logging, sistemando bug) ma l’uso esterno non cambia affatto → va bene una **PATCH**.
- Stai introducendo nuovi codici di errore o cambi la mappatura di EXIT\_CODES senza però rompere chiamate esistenti (ad es. aggiungi un nuovo Exit Code per un caso nuovo) → questo è accettabile in una **MINOR** (è una funzionalità in più, compatibile, ma documentalo bene).
- Cambi la **struttura di output** (es. aggiungi nuove cartelle, rinomini file generati, ecc.) → potenzialmente **MAJOR** se gli utenti o sistemi esterni si aspettavano il vecchio formato.

Questi criteri aiutano a decidere se bumpare versione Major, Minor o Patch. In caso di dubbio, prediligi la cautela: meglio rilasciare una 1.1.0 se non sei sicuro che una modifica minore possa rompere qualcosa a qualcuno.

-----
## <a name="rilascio-artefatti-e-checklist"></a>4) Rilascio (artefatti e checklist)
Ogni rilascio ufficiale dovrebbe includere:

1. **Tag Git** – creare un tag annotato nel formato vX.Y.Z sul commit appropriato (di norma sul commit di merge nel branch principale). Esempio: git tag -a v1.0.5 -m "Timmy-KB 1.0.5 – migliorie tool e fix".
1. **CHANGELOG.md** – aggiornato con la nuova versione, la data di rilascio e le sezioni *Added/Changed/Fixed/Deprecated/Removed/Security* compilate. Seguire lo stile Keep a Changelog per coerenza.
1. **Documentazione** – tutti i file rilevanti (README.md e i .md in docs/) aggiornati nella stessa PR in cui si fanno le modifiche di codice. La versione e la data vanno aggiornate in docs/index.md e altrove come visto.
1. **Test manuali** – eseguire i test manuali minimi (vedi Guida Sviluppatore) su pre-onboarding e onboarding in vari scenari, per assicurare che la release non abbia introdotto regressioni evidenti.
1. *(Opzionale)* Aggiornamento versione in uno script o modulo se il tool lo mostra a runtime (non applicabile in tutti i casi; se l’app avesse un --version, andrebbe aggiornato).

Esempio di tagging post-merge:

git checkout main  # assicurati di essere sul branch principale aggiornato\
git pull\
git tag -a v1.0.5 -m "Timmy-KB 1.0.5 – minor improvements and fixes"\
git push origin --tags

Assicurati di spingere anche i tag al remoto (git push --tags). I tag servono da riferimento per distribuire le versioni e per eventuali rollback.

-----
## <a name="deprecation-policy"></a>5) Deprecation Policy
- Un elemento marcato come **Deprecated** deve restare supportato per **almeno una versione MINOR** successiva all’annuncio. Esempio: se in 1.1.0 deprechi un flag, dovrai aspettare almeno la 1.2.0 (o oltre) per rimuoverlo effettivamente.
- Niente rimozioni in patch: le versioni PATCH **non rimuovono** funzionalità pubbliche, al massimo introducono warning. Le rimozioni vere e proprie avvengono in MAJOR (o in MINOR se si tratta di funzionalità mai dichiarate stabili, ma è un caso limite).
- Documenta sempre cosa usare al posto di ciò che è deprecato, e per quanto tempo resterà disponibile. La documentazione dovrebbe indicare chiaramente l’alternativa consigliata e se possibile quando avverrà la rimozione (es. “sarà rimossa nella 2.0.0”).
- **Caso attuale:** i flag --skip-drive / --skip-push sono deprecati (dalla 1.0.3) ma continuano a funzionare con un semplice warning. L’alternativa è usare --no-drive / --no-push. La loro rimozione definitiva avverrà non prima di una release **MAJOR** futura (annunciata con preavviso in una minor precedente).
-----
## <a name="changelog-regole-editoriali"></a>6) CHANGELOG: regole editoriali
Il CHANGELOG segue le linee guida di [Keep a Changelog](https://keepachangelog.com/it/1.0.0/). Alcune regole pratiche:

- Scrivi voci **brevi e orientate all’utente**: devono far capire cosa cambia in termini di funzionalità o comportamento, non solo a livello di codice.
- Usa tempi verbali al **passato** (“aggiunto X”, “corretto Y”) per uniformità.
- Includi la **data** di rilascio accanto alla versione, formato ISO YYYY-MM-DD, preceduta da una e n-dash (es: ## [1.0.5] — 2025-08-19).
- Se la modifica si riferisce a un PR o issue interno, valuta se menzionarlo (nel contesto di un repo privato va bene anche ometterlo, ma se fosse pubblico si potrebbero linkare).
- Ogni sezione (Added, Changed, Fixed, etc.) va inclusa solo se ci sono elementi in essa. Se ad esempio non ci sono deprecazioni, puoi omettere la sezione Deprecated per quella release.
- Se una modifica richiede azioni da parte dell’utente (es. rigenerare qualcosa, aggiornare .env), segnalalo tra parentesi o con un breve “**Nota:**” nella voce stessa.

Struttura consigliata di una entry:

\## [X.Y.Z] — YYYY-MM-DD\
\
\### Added\
\- …\
\
\### Changed\
\- …\
\
\### Fixed\
\- …\
\
\### Deprecated\
\- …\
\
\### Removed\
\- …\
\
\### Security\
\- …

*(Se una categoria non ha voci, puoi ometterla per quella release.)*

-----
## <a name="allineamento-con-cicd-facoltativo"></a>7) Allineamento con CI/CD (facoltativo)
- Potrebbe essere utile configurare un job di CI che **blocchi il merge** di una PR se la documentazione in docs/ o il README.md non sono aggiornati quando vengono modificate parti del codice correlate a CLI/comportamento. Ad esempio, usare parole chiave nei commit o file touched come trigger.
- Allo stesso modo, un controllo automatizzato per assicurarsi che ogni PR che cambia la logica abbia una voce in CHANGELOG.md può prevenire dimenticanze. Si può implementare uno script che esamina il diff e segnala se manca un aggiornamento del changelog.
- Queste misure non sono ancora attive, ma si considerano best practice man mano che il progetto cresce, per mantenere ordine e coerenza.
-----
**Stato:** Policy attiva dalla versione 1.0.4 (inclusa). Le release successive, come la 1.0.5, hanno seguito queste linee guida. È responsabilità di ogni maintainer assicurarsi che vengano rispettate in fase di review e rilascio.

-----
