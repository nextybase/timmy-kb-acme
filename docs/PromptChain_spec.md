# Prompt Chain Spec (SSoT)

## 1. Introduzione
- **Scopo**: separare la fase progettuale (Planner → OCP) dalla fase operativa (Codex), garantendo che ogni passaggio sia controllato, tracciabile e micro-PR compliant.
- **Perché uno SSoT**: evitare frammentazione tra documenti, fornire un riferimento unico su attori, regole e output attesi per la Prompt Chain.
- **Principi**: micro-PR, sicurezza (path-safety, I/O atomico), controllo umano (HiTL) e QA esplicita.

## 2. Parte A – Governance (Planner + OCP)

### 2.1 Attori
- **Planner**: pianifica obiettivi, decide se procedere, correggere o chiudere la chain; non modifica il codice.
- **OCP (OrchestratoreChainPrompt)**: traduce obiettivi del Planner in prompt numerati (Prompt 0, 1, ...), mantiene lo scope e l’ordine; non modifica il repository.
- **Codex**: esegue un prompt alla volta, agente repo-aware; applica patch limitate con QA e rispetto delle policy AGENT.

### 2.2 Onboarding Task Codex (entrypoint obbligatorio)
- Procedura iniziale con cui Codex carica contesto e regole del repo (AGENTS_INDEX, AGENTS locali, policy operative).
- Serve per attivare path-safety, confermare applicabilità del modello micro-PR e impostare gli SSoT.
- Eseguito una sola volta all’inizio della Prompt Chain, prima di qualsiasi prompt operativo.

### 2.3 Definizione di Prompt Chain
- Sequenza numerata di prompt (Prompt 0..N).
- Ogni prompt è uno step autonomo, con scope limitato e trattato come micro-PR con QA.
- Non esecuzioni in batch: un prompt alla volta.

### 2.4 Ciclo di vita della Prompt Chain

- **Avvio**
  - Il Planner decide di iniziare una Prompt Chain.
  - L’Onboarding Task Codex viene eseguito come prerequisito, assicurando che Codex abbia caricato SSoT, policy AGENT e regole di path-safety.
  - Solo dopo l’Onboarding l’OCP può generare il Prompt 0.

- **Svolgimento**
  - L’OCP genera un solo prompt alla volta (Prompt N).
  - Codex esegue il prompt, applica micro-PR limitati allo scope, e produce:
    - diff unificato,
    - report strutturato con esito e note operative.
  - Il Planner decide se proseguire, modificare la direzione o avviare la chiusura.

- **Chiusura (regola obbligatoria)**
  - Anche se il Planner richiede una chiusura anticipata, l’OCP genera comunque un **Prompt finale di QA**.
  - Il Prompt finale di QA ha l’obiettivo di portare a verde l’intera repository eseguendo realmente:
    ```
    pre-commit run --all-files
    pytest -q
    ```
  - Se uno dei due comandi fallisce, Codex applica micro-correzioni e reitera l’esecuzione (fino a un massimo di 10 tentativi).
  - La Prompt Chain è considerata conclusa solo quando entrambi i comandi risultano verdi.
  - In risposta al Prompt finale, **Codex deve proporre un commit one-line di sintesi** del lavoro svolto nella catena, come chiusura formale del ciclo.

## 3. Parte B – Contratto Operativo per Codex

### 3.1 Che cos’è una Prompt Chain per Codex
- Sequenza di prompt numerati, ciascuno con scope limitato e rappresentante un micro-PR.
- Esegui un solo prompt alla volta; non anticipare futuri passi; non generare prompt autonomi.

### 3.2 Regole fondamentali
- Rispetta sempre: path-safety, scritture atomiche, AGENTS_INDEX + AGENTS locali, questo SSoT, QA locale (formatter/linter/type/pytest mirato).
- Modifica solo i file esplicitamente permessi nel prompt; segui lo scope indicato.

### 3.3 Formato dei prompt di una Prompt Chain
- Ogni prompt esplicita: Scopo (1–3 righe), File ammessi/proibiti, Output richiesto (diff, report, QA), Divieti espliciti.

### 3.4 Output richiesto per ogni prompt
- Diff unificato (se ci sono modifiche).
- Report strutturato con: Modifiche applicate, Impatto, QA eseguita, Step successivi suggeriti; dichiarare assunzioni se il prompt non era completo.

### 3.5 Anti-pattern
- Aggiungere contesto non richiesto; modificare file non menzionati; interventi troppo ampi; unire domini eterogenei nello stesso prompt (codice + config + doc pesante).
