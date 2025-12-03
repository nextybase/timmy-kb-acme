# NeXT Principles & Probabilismo (minimo)

- Human-in-the-Loop: gli agenti propongono, il team decide. Iterazioni brevi e verificabili.
- Probabilismo: decisioni guidate da evidenze (test, metriche, log). Aggiorna regole quando i dati cambiano.
- Coerenza: una sola fonte della verita per path/I-O (SSoT) e per i tag (SQLite in `semantic/tags.db`).
- Sicurezza: nessuna scrittura fuori dal perimetro cliente; maschera segreti nei log.
- Portabilita: supporto Win/Linux; attenzione a encoding e path (POSIX vs Windows) nei file scambiati.
