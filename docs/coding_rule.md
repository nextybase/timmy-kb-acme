## <a name="docscoding_rule.md"></a>docs/coding_rule.md
# <a name="coding-rules-timmykb-v1.0.5"></a>Coding Rules — Timmy‑KB (v1.0.5)
Regole operative per scrivere e manutenere il codice della pipeline Timmy-KB. L’obiettivo è garantire stabilità, tracciabilità, sicurezza e comportamento deterministico (specie in modalità batch) attraverso uno stile di codice coerente.

-----
## <a name="linguaggio-stile-tipizzazione"></a>1) Linguaggio, stile, tipizzazione
- **Python ≥ 3.10** – utilizzare le feature del linguaggio disponibili (es. type hinting avanzato, match-case se utile) ma mantenere compatibilità con 3.10.
- **Type hints** – aggiungere annotazioni di tipo a tutte le funzioni pubbliche e alle strutture dati complesse; usare typing.Optional, Dict, List ecc. dove necessario per chiarezza. I protocolli o ABC possono essere usati se migliorano la leggibilità dei contratti.
- **Docstring** – scrivere docstring brevi e chiare (stile [Google](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods) consigliato). Fornire esempi d’uso solo se aiutano a chiarire casi non ovvi.
- **Naming** – usare snake\_case per variabili e funzioni, PascalCase per classi ed eccezioni, MACRO\_CASE per costanti. I nomi dovrebbero essere esplicativi (evitare abbreviazioni criptiche).
- **Import** – ordine: librerie standard, poi terze parti, poi moduli locali del progetto. Separare i gruppi con una riga vuota. Preferire import **assoluti** (es. from pipeline import content\_utils anziché relativi) per chiarezza e per agevolare eventuale refactoring del package.
- **Formattazione** – seguire PEP 8. Utilizzare strumenti automatici come *Black* per l’indentazione e la formattazione, e *Ruff* per il linting (incluso check degli import inutilizzati). I commit dovrebbero preferibilmente passare i controlli di pre-commit configurati nel repository.
- **Commenti** – inserire commenti dove il codice potrebbe non essere immediatamente chiaro. Evitare commenti superflui su cose ovvie; privilegiare commenti che spiegano il *perché* di una scelta implementativa piuttosto che il *cosa* fa il codice.
-----
## <a name="orchestratori-vs-moduli"></a>2) Orchestratori vs Moduli
- **Orchestratori** – contengono la logica di flusso e interazione: parsing degli argomenti CLI, prompt all’utente (solo in interattivo), gestione delle modalità (--non-interactive, --dry-run, --no-drive, --push, etc.), avvio e arresto dell’anteprima Docker, e gestione centralizzata delle eccezioni (catch ed exit con codici). Devono mantenere il controllo del processo (chiamate finali a sys.exit() solo qui).
- **Moduli** – implementano operazioni tecniche (accesso a Drive, conversione file, push GitHub, ecc.). Non devono leggere input dall’utente né terminare il programma. Espongono funzioni che gli orchestratori chiamano, e sollevano eccezioni in caso di problemi. In questo modo possono essere testati in isolamento e riutilizzati facilmente.
- **Output utente** – solo gli orchestratori stampano messaggi “per l’utente” (ma anche questi preferibilmente via logger con stdout come fallback). I moduli, se hanno bisogno di comunicare informazioni, lo fanno restituendo valori o lanciando eccezioni, mai con print(). Questo garantisce che in modalità batch non ci siano output inattesi.
- **Batch-safe** – tutto il codice nei moduli deve poter girare senza interazione. Ciò significa evitare di richiedere input, evitare loop di attesa, e assicurarsi che i default permettano l’esecuzione end-to-end senza intervento. Gli orchestratori possono invece gestire interattività e comportamenti differenti tra batch e interattivo.
-----
## <a name="logging-ed-errori"></a>3) Logging ed errori
- **No print()** – qualsiasi informazione rilevante deve passare per il logging strutturato. Configurare il logger con nome del modulo (logging\_utils.get\_structured\_logger(\_\_name\_\_)) e usare livelli appropriati (DEBUG per dettagli tecnici, INFO per fasi completate, WARNING per situazioni anomale recuperabili, ERROR per problemi bloccanti).
- **Metadati nei log** – includere nei messaggi di log informazioni contestuali utili. Esempio: quando logghi l’inizio di una conversione, aggiungi extra={"slug": context.slug, "file\_path": str(pdf\_path)}. Questi extra appariranno nel log JSON e aiuteranno a tracciare cosa è successo. Non abusare di stringhe statiche: preferisci messaggi formattati con %s e parametri extra.
- **Niente segreti nei log** – se c’è anche una minima possibilità che una stringa contenga un token o un identificativo sensibile, assicurati che venga mascherata. Usa la funzione di redazione (env\_utils.redact\_secrets) sui testi grezzi o, meglio, lascia che sia il logger a farlo passando context.redact\_logs quando richiesto. Ad esempio, le funzioni Drive accettano redact\_logs=True per evitare di loggare ID di file/cartelle.
- **Eccezioni tipizzate** – lancia eccezioni specifiche per i vari errori (vedi pipeline.exceptions). Questo rende il flusso chiaro e permette agli orchestratori di distinguere le cause. Ad esempio, se manca un file locale richiesto, lancia InputFileMissing invece di una generica Exception. Gli orchestratori mappano poi ciascuna eccezione a un exit code (definito in EXIT\_CODES) assicurando che ogni tipo di errore abbia un codice univoco.
- **Gestione deterministica degli errori** – niente catch-all generici nei moduli (evitare except Exception: a meno che non si stia rilanciando come errore di pipeline). Specificare i casi noti e lasciare propagare gli imprevisti: saranno comunque catturati dall’orchestratore come PipelineError generico (exit code 1) se sfuggono a controlli specifici.
- **Messaggi di errore chiari** – i messaggi delle eccezioni dovrebbero spiegare il problema in maniera comprensibile (es. “File PDF mancante nella cartella raw/” invece di “Exception occurred”). Questo testo può essere mostrato all’utente se l’orchestratore lo logga prima di uscire.
-----
## <a name="io-sicurezza-e-atomicità"></a>4) I/O, sicurezza e atomicità
- **Pathlib & encoding** – utilizzare oggetti Path per gestire file e directory. Prima di aprire un file, specificare sempre encoding="utf-8" (salvo binari) per evitare dipendenze dalla locale di sistema. Aprire i file con contesto (with open(...) as f:) per assicurare la chiusura.
- **Path traversal** – sempre prevenuto con is\_safe\_subpath(child, base): questa funzione (in path\_utils.py) verifica che il path child sia all’interno del path base. Usala quando compongono path utente (slug, nomi file derivati da PDF, ecc.) per evitare che uno slug malevolo come ../etc/passwd crei problemi.
- **Scritture atomiche** – per file critici come config.yaml o output Markdown, adotta sempre un meccanismo atomico: scrivi su un file temporaneo nella stessa directory, poi fai move/replace sul file definitivo. La funzione write\_client\_config\_file in config\_utils.py è un esempio: crea un .bak e poi sostituisce il config precedente. Questo evita config parziali se qualcosa va storto durante la scrittura.
- **No segreti su disco** – Non salvare mai su disco informazioni sensibili: credenziali, token, contenuti dei PDF (oltre ai PDF stessi), ecc. I token rimangono in variabili d’ambiente, i PDF vengono solo letti e convertiti. Se per debug hai bisogno di loggare strutture dati, assicurati che non contengano sezioni sensibili o puliscile prima.
- **Chiusura risorse** – Chiudi esplicitamente file, sessioni di rete, cursori di database (se ce ne fossero). Usa i context manager quando disponibili (with statement) così da gestire automaticamente la chiusura anche in caso di eccezioni.
-----
## <a name="configurazioni-e-cache"></a>5) Configurazioni e cache
- **YAML config** – utilizza yaml.safe\_load per leggere i file YAML di configurazione ed evitare rischi di esecuzione arbitraria. Gestisci con cura i casi di chiavi mancanti: prevedi default sensati o lancia errori chiari (ConfigError) se una chiave obbligatoria non c’è.
- **Regex dello slug** – definita in config/config.yaml (chiave slug\_regex). Questa regex viene caricata una volta e memorizzata (cache) per evitare ricompilazioni ripetute. Se per qualche motivo modifichi a runtime la regex (evento raro, ad esempio caricando un nuovo config), chiama path\_utils.clear\_slug\_regex\_cache() per forzare il ricalcolo. In caso contrario, potresti continuare a validare slug con la vecchia regex.
- **Variabili d’ambiente** – accedi alle env solo tramite le funzioni centralizzate in env\_utils.py (get\_env\_var, get\_bool, get\_int, etc.). Queste funzioni gestiscono i default e l’errore in modo consistente (es. get\_env\_var(required=True) lancia ConfigError se manca). Evita os.environ[...] sparsi nel codice: centralizzando gli accessi è più facile fare debug e mockare in test.
- **Cache di runtime** – se implementi meccanismi di cache in memoria (es. caching di risultati tra chiamate), assicurati che siano invalidati correttamente quando cambia lo scenario. Ad esempio la cache per la regex slug è invalidata dalla funzione di clear. Mantieni le cache isolate all’interno del modulo (variabili globali private) e fornisci eventuali funzioni di invalidazione se necessario.
-----
## <a name="subprocess-docker-github"></a>6) Subprocess, Docker, GitHub
- **Esecuzione di comandi esterni** – Usa subprocess.run([...], check=True, capture\_output=... ) specificando la lista di argomenti. **Non usare** shell=True a meno che strettamente necessario (in tal caso, occhio alla sanitizzazione degli input per evitare injection). In genere, per chiamare Docker o Git, passa i parametri come lista, ad es. subprocess.run(["docker", "info"], ...).
- **Chiamate Docker** – Il modulo gitbook\_preview.py richiama Docker per buildare e servire la documentazione. Assicurati che tali chiamate non blocchino: per il serve usa l’opzione detached (docker run -d ...). Non aspettare in polling il termine del container; l’orchestratore terminerà il container con docker rm -f al termine. Logga l’output di build e eventuali errori in modo da avere traccia in caso di fallimento.
- **Chiamate Git/GitHub** – Usa l’API git tramite CLI (subprocess con comandi git) oppure la CLI gh se già in uso nel progetto, sempre con attenzione a non esporre credenziali. Nel nostro caso, github\_utils.py usa git direttamente. Valida sempre le precondizioni (ad es. se manca GITHUB\_TOKEN, lancia ConfigError subito). Segui la policy di push incrementale: commit solo se ci sono modifiche, push normale, e gestisci un eventuale rifiuto con un retry. **Non forzare** push a meno che un flag specifico lo richieda, e comunque con --force-with-lease per minimizzare i rischi.
- **Sicurezza token** – Per push su GitHub, non includere il token nell’URL remota. Usa invece GIT\_HTTP\_EXTRAHEADER per impostare l’header Authorization, come fatto internamente (il token è gestito in ambiente e mai passato in chiaro al comando git). Nei log, maschera gli estremi del token se per qualche ragione compaiono (in genere il logger già non logga l’header).
-----
## <a name="drive-e-rete"></a>7) Drive e rete
- **Retry Exponential Backoff** – Per operazioni di rete (es. chiamate alle API Drive), implementa un retry con backoff esponenziale e jitter. Ad es., se fallisce una richiesta, attendi 1s, poi 2s, 4s... fino a un massimo (configurato in drive/client.py). Logga i tentativi e i backoff accumulati, così da poter capire se un’operazione impiega molto tempo a causa dei retry.
- **Idempotenza download** – La funzione di download Drive (download\_drive\_pdfs\_to\_local) deve evitare di riscaricare file invariati: utilizza gli hash MD5 e la dimensione per verificare se un file locale corrisponde a quello remoto. Se coincidono, salta il download e passa oltre. Questo consente di ri-eseguire la pipeline senza duplicare il lavoro già fatto.
- **Struttura locale = struttura remota** – Mantieni la gerarchia: i PDF scaricati da Drive vanno posizionati in raw/ rispettando le eventuali sottocartelle presenti su Drive. Analogamente, la generazione dei Markdown in book/ deve rispecchiare la struttura (un Markdown per categoria top-level). Ciò rende più semplice navigare i file e confrontare locale vs remoto.
- **Metriche e logging** – Se implementi metriche (numero di retry, tempo totale speso in attesa, conteggio di file scaricati, ecc.), assicurati di loggarle a fine operazione. Ad esempio, dopo un download completo, potresti loggare quanti file sono stati scaricati e quanti skip per cache. Queste informazioni aiutano a capire le performance nel tempo.
- **Redazione dati sensibili** – Qualsiasi output che contenga ID di file Drive, nomi di cartelle utente o altri dati sensibili deve essere soggetto a redazione se abilitata. Segui il pattern: passa sempre redact\_logs=context.redact\_logs alle funzioni di Drive e simili, e all’interno di esse usa \_mask() o funzioni analoghe per loggare versioni parziali degli ID (es. mostrando solo le ultime 4-6 cifre e mascherando il resto).
-----
## <a name="deprecation-compat"></a>8) Deprecation & compat
- **Alias e funzioni deprecate** – mantieni la compatibilità per almeno una versione MINOR dopo aver dichiarato qualcosa deprecato. Ad esempio, --skip-drive/--skip-push sono deprecati dalla 1.0.3 ma ancora supportati in 1.0.5 con semplici warning; prevediamo di rimuoverli solo in una futura versione 1.1.0 (MINOR successiva).
- **Segnalazione** – quando qualcosa è deprecato, emetti un warning chiaro (es. logger.warning che indica cosa usare al posto del deprecato). Documenta nella sezione pertinente (README o docs) la deprecazione e l’alternativa.
- **No breaking changes in PATCH** – aderiamo al SemVer leggero: in una release di PATCH (come 1.0.5) non vanno rimossi comportamenti supportati né modificati i default in modo incompatibile. Limitarsi a bugfix, refactor interni e aggiunte retrocompatibili. Se proprio necessario cambiare qualcosa di osservabile, rivalutare se non debba essere una MINOR.
- **Compat test** – dopo modifiche significative, prova i comandi base (elencati anche nel README e in questa guida) per assicurarti che tutto funzioni come prima. La retrocompatibilità non è uno slogan: va verificata sul campo.
-----
## <a name="test-minimi-manuali"></a>9) Test minimi (manuali)
Prima di completare una PR, esegui almeno questi test manuali per assicurare che i percorsi critici funzionino:

1. **Pre‑onboarding (solo locale)** –

   py src/pre\_onboarding.py --slug demo --non-interactive --dry-run

   (Dovrebbe terminare senza errori, creare la struttura locale output/timmy-kb-demo/ con config e log, e non richiedere input né toccare servizi esterni.)
1. **Onboarding base (niente Drive, niente push)** –

   py src/onboarding\_full.py --slug demo --no-drive --non-interactive

   (Deve scaricare eventuali PDF **solo se** presenti localmente da esecuzioni precedenti, convertire i PDF dummy in Markdown, generare README/SUMMARY, saltare automaticamente la preview se Docker non è attivo, e terminare con exit code 0.)
1. **Onboarding con Docker attivo** – (Prerequisito: Docker installato e in esecuzione)\
   Esegui py src/onboarding\_full.py --slug demo in modalità interattiva. Conferma l’anteprima quando richiesto. Verifica che:
1. la preview parta in pochi secondi su http://localhost:4000,
1. l’esecuzione della pipeline non sia bloccata durante la preview,
1. alla fine, dopo aver risposto al prompt di push (scegliendo No) e al prompt di cleanup, il container Docker venga **fermato automaticamente** (controlla con docker ps che non sia più presente).
1. **Push in batch** – *Richiede un repository GitHub configurato per la destinazione*\
   Imposta GITHUB\_TOKEN e GIT\_DEFAULT\_BRANCH=main in ambiente, poi esegui:

   py src/onboarding\_full.py --slug demo --no-drive --non-interactive --push

   (Deve clonare il repo, copiare i file Markdown, fare commit e push su main. Se sul repo remoto c’erano commit aggiuntivi, dovrebbe fare pull --rebase e riprovare. Nessun push forzato deve avvenire a meno che tu aggiunga --force-push --force-ack X per testare il caso di force: in tal caso, verifica che senza --force-ack esca con errore 41, e con entrambi proceda con --force-with-lease.)
-----
## <a name="qualità-del-codice"></a>10) Qualità del codice
- **Funzioni piccole e focalizzate** – ogni funzione dovrebbe svolgere un compito preciso. Se ti accorgi che una funzione sta crescendo troppo o gestendo troppe cose, valuta di scomporla in sotto-funzioni. Ciò semplifica test e manutenzione.
- **Chiarezza vs. performance** – privilegia codice chiaro e manutenibile rispetto a ottimizzazioni premature. Ottimizza solo quando hai evidenza (profiling) che un blocco è critico per le performance. Anche in quei casi, commenta bene il perché di eventuali trick non intuitivi.
- **Evita duplicazione** – se lo stesso blocco di codice o logica è usato in più punti, considera di estrarlo in una funzione condivisa. Mantieni la DRY (Don’t Repeat Yourself) principle, purché non crei dipendenze incrociate strane (valuta se mettere in utils o in moduli già esistenti).
- **Testabilità** – scrivi il codice in modo da poterlo testare. Funzioni pure quando possibile, modulare, con pochi effetti collaterali. Usa dipendenze iniettate (es. passare l’oggetto logger o context) invece di prendere globali all’interno, così da poterle sostituire in test.
- **Commenti e TODO** – se qualcosa è migliorabile ma esula dallo scope corrente, inserisci un # TODO: con breve descrizione. Tienili d’occhio nelle PR e magari apri issue dedicate. Non lasciare però blocchi di codice commentato morto: se non serve, rimuovi.
- **Consistenza** – segui lo stile già presente nel codice: ad esempio, se in tutto il progetto le costanti booleane si chiamano ENABLE\_XYZ, non introdurre XYZ\_ENABLED altrove. Mantieni consistenza nei nomi delle variabili, nel tono dei log (evita slang o stili troppo divergenti) e nell’uso delle emoji nei log (limitarle a casi di uso semantico come “⏭️” per skip, “✅” per successi, in linea con quanto fatto finora).
-----
### <a name="esempi-rapidi"></a>Esempi rapidi
**Logger corretto in un modulo**

\# pipeline/content\_utils.py\
from pipeline.logging\_utils import get\_structured\_logger\
logger = get\_structured\_logger("pipeline.content\_utils")\
\
def convert\_pdf\_to\_md(context, pdf\_path):\
`    `# Metadati slug e file nei log, redazione automatica se abilitata\
`    `logger.info("Convertendo PDF in Markdown", extra={"slug": context.slug, "file\_path": str(pdf\_path)})\
`    `try:\
...  # conversione\
`        `logger.info("Conversione completata", extra={"slug": context.slug, "file\_path": str(pdf\_path)})\
`    `except Exception as e:\
`        `logger.error(f"Errore durante la conversione: {e}", extra={"slug": context.slug, "file\_path": str(pdf\_path)})\
`        `raise

**Errore tipizzato + mapping orchestratore**

\# Esempio modulo pipeline/preview\_utils.py\
from pipeline.exceptions import PreviewError\
\
def generate\_preview(context):\
`    `# ... codice che tenta di avviare Docker ...\
`    `if error\_docker:\
`        `raise PreviewError("Build anteprima fallita", slug=context.slug)\
\
\# Nell’orchestratore onboarding\_full.py\
from pipeline.exceptions import EXIT\_CODES, PreviewError\
\
try:\
`    `generate\_preview(context)\
except PreviewError as e:\
`    `logger.error(str(e))\
`    `sys.exit(EXIT\_CODES["PreviewError"])

*(Gli esempi mostrano come loggare correttamente con contesto e come propagare errori tipizzati all’orchestratore.)*

-----