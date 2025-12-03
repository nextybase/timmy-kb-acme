# Sicurezza  Timmy-KB

##  Segnalazione vulnerabilita
Se scopri una vulnerabilita di sicurezza in **Timmy-KB**, ti chiediamo di **non** aprire una issue pubblica.

Invece, invia una segnalazione **privata** al team di manutenzione tramite:
- **Email**: security@nextybase.com
- **Canale interno** (per membri del team)

Indica nella segnalazione:
1. Descrizione dettagliata della vulnerabilita
2. Passaggi per riprodurla
3. Impatto potenziale
4. Eventuali suggerimenti di correzione

---

##  Tempi di risposta
Il team si impegna a rispondere entro **72 ore** dalla ricezione della segnalazione e a:
- Confermare la ricezione
- Avviare la revisione tecnica
- Comunicare lo stato di avanzamento

---

##  Buone pratiche di sicurezza
- Non includere credenziali o dati sensibili nei commit
- Utilizzare file `.env` per variabili di ambiente
- Validare sempre gli input esterni nelle funzioni
- Gestione dipendenze con **pip-tools**:
  - modifica solo i file `requirements*.in`
  - rigenera i pin con `pip-compile`  `requirements*.txt` (e `constraints.txt` se previsto)
  - installa sempre dai `.txt` generati
  - evita installazioni ad hoc non riproducibili
- Esegui periodicamente uno **scan** con `pip-audit` (gia incl'uso tra le dipendenze degli hook QA).
- Per note su licenze e componenti opzionali (es. uso di PyMuPDF per funzioni Vision) vedi anche `docs/SECURITY.md`.

---

##  Riconoscimenti
Gli utenti che segnalano in buona fede una vulnerabilita e collaborano alla sua risoluzione possono essere citati nella sezione *Security Acknowledgements* del progetto (su richiesta).
