
## <a name="docspolicy_push.md"></a>docs/policy_push.md
# <a name="policy-di-push-timmy-kb-v1.0.5"></a>Policy di Push – Timmy-KB (v1.0.5)
Questa policy definisce **quando** e **come** eseguire il push dei contenuti generati dalla pipeline verso un repository GitHub remoto.\
È aggiornata a **v1.0.5**: il push incrementale senza forzature rimane il comportamento predefinito, e sono state introdotte regole di governance per l’uso eccezionale del push forzato (doppia conferma e branch ammessi).

-----
## <a name="principi"></a>1) Principi
- La **fonte di verità** dei contenuti è sempre l’**output locale** generato dalla pipeline (output/timmy-kb-<slug>/book/). Il repository remoto deve rispecchiare esattamente questo output.
- Il push deve avvenire **solo a valle di una generazione valida**: i file Markdown pubblicati devono essere stati generati dalla pipeline senza errori e dopo le eventuali verifiche (anteprima, controlli link) in locale.
- Il branch remoto di destinazione è determinato dalla variabile **GIT\_DEFAULT\_BRANCH** (o, in mancanza, main). Assicurarsi di aver configurato questa variabile secondo la strategia di rilascio desiderata.
- Il push sul repository Git va considerato come un’operazione irreversibile sullo stato pubblico del progetto; va eseguito in maniera conservativa, evitando forzature a meno di motivi espliciti e approvati.
-----
## <a name="pre-condizioni-per-il-push"></a>2) Pre-condizioni per il push
Esegui il push **solo se**:

1. La fase di conversione ha prodotto una cartella book/ completa e priva di errori (inclusi file README.md e SUMMARY.md aggiornati).
1. Nei log **non** compaiono errori e il codice di uscita finale della pipeline è 0.
1. Hai un **token GitHub valido** in GITHUB\_TOKEN (se vuoi procedere con il push); in caso contrario, decidi consapevolmente di non eseguire push (flag --no-push o risposta negativa al prompt).
1. Il branch di destinazione è corretto e coerente con la tua strategia (controlla GIT\_DEFAULT\_BRANCH nel contesto o nel .env).

In **modalità non-interattiva** (batch/CI), il push è **disabilitato** di default. Devi specificare esplicitamente --push per attivarlo, altrimenti la pipeline completerà il processo senza tentare il push.

-----
## <a name="modalità-operative"></a>3) Modalità operative
### <a name="interattiva"></a>Interattiva
- Al termine della pipeline (dopo conversione e anteprima), l’orchestratore chiede all’utente se eseguire il push (prompt *«Eseguire il push su GitHub?»*, default **NO** per sicurezza).
- Se l’utente conferma (risponde Sì), la pipeline avvia la procedura di push: carica il token da GITHUB\_TOKEN, determina il branch (da GIT\_DEFAULT\_BRANCH), ed esegue push\_output\_to\_github(...).
- In caso di esito positivo, i contenuti sono allineati sul branch remoto; eventuali differenze vengono risolte secondo la logica incrementale (vedi sezione 4). Se il push viene rifiutato per divergenze, la pipeline tenterà un pull --rebase e un nuovo push, come da implementazione interna.
### <a name="non-interattiva-ci"></a>Non-interattiva / CI
- Il push è **NO** per default. Per abilitarlo in script o CI, devi lanciare l’orchestratore con flag --push esplicito.
- Se GITHUB\_TOKEN non è impostato in ambiente, il push fallirà con un errore ConfigError: in uno scenario CI questo significa che dovresti aggiungere --no-push per eseguire solo la generazione dei file, oppure assicurarti di avere un token configurato come secret.
- Non essendoci prompt, assicurati che tutte le variabili (token, branch, ecc.) siano corrette a priori. Il codice uscirà con codice 0 solo se il push è completato o se è stato esplicitamente escluso; in caso di errore durante il push, avrai un exit code specifico (es. 40 per PushError).
-----
## <a name="x3507463818a83a9a8ad652355dbb21b23395224"></a>4) Modalità di push (default: incrementale, no force)
Il push di default avviene in modo **incrementale**, seguendo questi passi:

1. **Clone** – viene clonato il repository remoto in una working directory temporanea **interna** a output/timmy-kb-<slug>/ (ad es. output/timmy-kb-<slug>/.push\_<random>/).
1. **Checkout branch** – si esegue il checkout del branch di destinazione (letto da GIT\_DEFAULT\_BRANCH, o creato se non esiste ancora sul remoto).
1. **Sync iniziale** – se il branch esiste già sul remoto, viene eseguito un git pull --rebase origin <branch> per sincronizzare eventuali commit remoti (evitando merge commit).
1. **Aggiornamento contenuti** – tutti i file \*.md generati in locale nella cartella book/ vengono copiati (sovrascritti) nella working directory del repo clonato, mantenendo la stessa struttura di cartelle. Eventuali file Markdown presenti nel repo che non sono più generati (es. vecchie categorie rimosse) vengono eliminati durante il git add -A.
1. **Commit** – viene eseguito git add -A per stage di tutti i cambiamenti, quindi un commit con messaggio generico (es. “Aggiornamento contenuti KB <slug>”) **solo se** ci sono modifiche rispetto all’ultimo commit noto. Se non ci sono differenze (contenuti identici), non viene creato alcun nuovo commit.
1. **Push** – viene eseguito git push origin <branch>. Questo è un push **senza** --force, quindi rispetta le regole standard di GitHub: se il branch remoto ha divergenze non risolvibili con il rebase già fatto, il push verrà rifiutato.
1. **Retry automatico** – se il push viene rifiutato per un errore di fast-forward (qualcun altro ha pushato nel frattempo, o il rebase locale non ha incluso tutti i commit remoti), la pipeline effettua un nuovo git pull --rebase e riprova il git push una seconda volta. Questo dovrebbe risolvere casi di race condition minori. Se anche il secondo tentativo fallisce, non si insiste oltre.
1. **Conflitti** – se durante il rebase si verificano conflitti di merge (ad esempio, modifiche manuali sui file .md sul remoto), la procedura si interrompe segnalando l’errore. In tal caso la pipeline lancia un’eccezione (exit code 40) e fornisce suggerimenti: ad esempio, usare un branch dedicato per il push o valutare un push forzato eccezionale (vedi sezione 6).

**Nota sulla sicurezza:** - La working directory temporanea del push è creata all’interno della cartella output/ del cliente, per garantire che script malevoli non possano influenzare percorsi al di fuori (segue il concetto di sandbox per ogni slug). - Il token GitHub è passato al comando git tramite header HTTP (GIT\_HTTP\_EXTRAHEADER) così che non compaia nella command line né nei log di Git. In caso di errori, il logger maschera eventuali occorrenze del token.

-----
## <a name="uso-di---no-push-e-casi-duso"></a>5) Uso di --no-push e casi d’uso
- **Validazione locale:** eseguire la pipeline con --no-push è utile se si vuole ispezionare il risultato (i Markdown generati in book/) prima di pubblicare. Questo permette di verificare i contenuti, correggere eventuali errori, e poi eventualmente rilanciare con push abilitato.
- **Debug sviluppo:** durante lo sviluppo o test, evitare il push previene modifiche inutili al repository remoto e riduce i tempi. Ad esempio, se stai iterando sulla conversione Markdown, usa sempre --no-push per concentrarti su quella parte.
- **Processi approvativi:** in contesti dove la pubblicazione richiede un’approvazione (umana), puoi generare tutto in locale (--no-push), far revisionare i file .md a qualcuno, e solo dopo eseguire manualmente il push (o aprire una PR separata).
- **Utilizzo CI/CD:** spesso in CI si genera la documentazione ma non si pusha direttamente su main. Invece, si potrebbe usare un branch temporaneo e aprire automaticamente una Pull Request. In questi casi, lancia la pipeline con --no-push e gestisci il push tramite script separati o azioni CI (o imposta GIT\_DEFAULT\_BRANCH a un branch dedicato per quella run, senza forzare).
-----
## <a name="xb54d557fcc503bf2562c62408ecce7affa9cced"></a>6) Quando (e come) considerare il push forzato
Il push forzato (--force) va **evitato** salvo situazioni eccezionali. È preferibile correggere divergenze tramite merge o rebase manuali, o eliminare modifiche remote non desiderate con commit correttivi. Tuttavia, se ci si trova in uno dei seguenti scenari, un force push potrebbe essere giustificato:

- Il branch remoto è **divergente** a causa di modifiche manuali o commit errati che si decide di scartare completamente in favore dello stato generato dalla pipeline.
- È necessario **riscrivere la storia** pubblicata (ad es. per rimuovere informazioni errate o sensibili nei commit) riallineandola all’output attuale della pipeline.

**Linee guida per l’uso di --force (forzatura):**

1. **Comunicazione e approvazione** – Informa il team o i responsabili del repository che intendi fare un push forzato e ottieni il loro consenso. Un force-push cambia la cronologia git e può confondere i collaboratori se fatto senza preavviso.
1. **Tag di backup** – Prima di forzare, crea un tag sulla commit attuale del branch remoto (es. pre-force-push-2025-08-19) così da poter facilmente recuperare la situazione precedente in caso di problemi. Questo tag fungera da àncora di rollback.
1. **Limita al branch giusto** – Esegui push forzato **solo** sul branch che è destinato a ricevere la documentazione generata (es. main o un branch dedicato di pubblicazione). Non forzare mai su branch di sviluppo condivisi. Assicurati che il branch sia ammesso dalla policy interna (GIT\_FORCE\_ALLOWED\_BRANCHES).
1. **Forza con criterio** – Usa --force-with-lease (è ciò che fa la pipeline) anziché --force puro: questa opzione assicura che il force avvenga solo se la base remota è quella che ti aspetti, riducendo il rischio di sovrascrivere commit di qualcun altro in modo incontrollato.
1. **Documenta nel CHANGELOG** – Se effettui un push forzato, aggiungi una voce nel CHANGELOG o nella documentazione di rilascio spiegando il motivo e le implicazioni. Questo serve per audit e per memoria storica del team.

**Nota tecnica:** a partire dalla versione 1.0.4 la pipeline stessa ha introdotto un meccanismo di sicurezza per i push forzati: in modalità non-interattiva non esegue mai force push a meno che non siano presenti *due* flag (--force-push **e** --force-ack <TAG>), e verifica comunque che il branch sia consentito. In modalità interattiva, chiede una conferma aggiuntiva e un tag di ack all’utente se viene richiesto un force push. Questo significa che la pipeline rende volutamente scomodo (e tracciabile) l’uso di push forzati, scoraggiandolo salvo casi eccezionali e deliberati.

-----
## <a name="verifiche-consigliate-prima-del-push"></a>7) Verifiche consigliate prima del push
Prima di eseguire il push (soprattutto in contesti manuali), passa in rassegna questa checklist:

- [ ] La cartella book/ contiene tutti i file .md attesi (ogni categoria top-level ha il suo Markdown, tutti i PDF hanno contribuito al contenuto). I file SUMMARY.md e README.md in book/ sono aggiornati e coerenti.
- [ ] I link interni tra i file Markdown funzionano correttamente. Per verificarlo, è utile usare l’anteprima HonKit (in locale via Docker) oppure uno strumento di controllo link. Se Docker non è disponibile, procedi senza preview ma fai un controllo manuale a campione sui link generati.
- [ ] Il log (output/timmy-kb-<slug>/logs/onboarding.log) non mostra errori né warning gravi. Eventuali avvisi (warning) li hai interpretati e ritenuti non problematici per la pubblicazione.
- [ ] Il processo è terminato con exit code 0 (successo completo).
- [ ] La variabile GITHUB\_TOKEN è impostata correttamente e ha i permessi necessari sul repository di destinazione.
- [ ] Il branch di destinazione (GIT\_DEFAULT\_BRANCH) è quello voluto e allineato alla strategia corrente (es. non stai pushando su main mentre volevi aggiornare un branch di feature, o viceversa).
- [ ] (Opzionale) Se temi di sovrascrivere qualcosa di importante, hai creato un branch dedicato e stai pushando lì (così da poter aprire una Pull Request e fare review prima di unire su main).
-----
## <a name="esempi"></a>8) Esempi
**Interattivo con push su conferma**

py src/onboarding\_full.py --slug acme\
\# ... al prompt finale seleziona "Sì" quando chiede se eseguire il push

*Comportamento:* verrà pushato in modo incrementale sul branch di default (es. main) dopo conferma, senza forzare.

**CI non-interattivo con push esplicito**

export GITHUB\_TOKEN=ghp\_ABC123...\
export GIT\_DEFAULT\_BRANCH=main\
py src/onboarding\_full.py --slug acme --no-drive --push --non-interactive

*Comportamento:* la pipeline esegue tutto in batch e poi push in automatico su main. Se manca il token o c’è un errore, il job CI fallirà (exit code ≠ 0).

**Branch dedicato “safe” (PR verso main)**

export GIT\_DEFAULT\_BRANCH="kb/acme-$(date +%Y%m%d)"\
py src/onboarding\_full.py --slug acme --no-drive --push --non-interactive

*Comportamento:* i contenuti verranno pushati su un branch nuovo, ad esempio kb/acme-20250819. Questo branch può essere usato per fare una Pull Request verso main, permettendo revisione prima di merge.

-----
## <a name="anti-pattern"></a>9) Anti-pattern
Evita assolutamente questi scenari nell’uso del push:

- **Push con book/ incompleto** – non eseguire il push se la generazione dei file non è arrivata a completamento o se alcuni file Markdown sembrano mancanti/obsoleti. Pubblicare uno stato incoerente della documentazione può creare confusione (o rompere l’anteprima pubblicata).
- **Modifiche manuali post-pipeline non rigenerate** – non modificare a mano i file nel repo remoto senza aggiornare quelli generati localmente. Se hai bisogno di aggiustare qualcosa, fallo sui sorgenti (PDF o config) e rigenera la KB. Il repository remoto **deve** essere output “pulito” della pipeline, senza patch manuali fuori band.
- **Force-push di routine** – non utilizzare push forzati come parte normale del processo. Se ti accorgi che sei tentato di usare --force spesso, è un segnale che va rivista la strategia di branch o il flusso (ad es. usare branch dedicati per cliente). Il force-push deve restare un’eccezione estrema, e come tale va documentata e approvata ogni volta.

**Stato:** policy valida e aggiornata per v1.0.5. Il comportamento predefinito resta il push incrementale (senza forzature), con barriere aggiunte per i push forzati. Seguendo queste linee guida, garantiamo che la Knowledge Base pubblicata sia sempre consistente e tracciabile.

