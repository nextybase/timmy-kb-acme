# Registro delle Decisioni (ADR)

Questo directory raccoglie le **Architecture / Technical Decision Records** del progetto. Ogni ADR documenta il contesto, la decisione presa, le alternative considerate e quando rivederla.

## Convenzioni

- Naming: `000X-titolo-breve.md` (incrementare il numero con padding a 4 cifre).
- Lingua: italiano sintetico; allegati/estratti tecnici possono essere in inglese.
- Struttura minima:

```markdown
# ADR-Titolo
- Stato: Accepted | Superseded | Proposed
- Data: YYYY-MM-DD
- Responsabili: <chi ha approvato>

## Contesto
...

## Decisione
...

## Alternative considerate
- Opzione A ...
- Opzione B ...

## Revisione
- Trigger / metriche per rivalutare la decisione.
```

## Workflow

1. Crea il file ADR nel PR che introduce la decisione.
2. Aggiorna l'indice (questo README) con un bullet che collega il nuovo ADR.
3. Se un ADR viene superato, aggiorna Stato e aggiungi il riferimento al successore.

## ADR disponibili

- [ADR-0001: SQLite come SSoT per i tag runtime](0001-sqlite-ssot-tags.md)
