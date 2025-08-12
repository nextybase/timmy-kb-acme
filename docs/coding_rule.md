# Regole di Codifica – Timmy-KB

Questo documento definisce gli standard di sviluppo per **Timmy-KB** e i principi generali di NeXT. L’obiettivo è mantenere coerenza, qualità e leggibilità del codice lungo tutto il ciclo di vita del progetto.

---

## 📂 Struttura del codice

- **Separazione logica**:
  - `pipeline/` → orchestrazione e flussi di esecuzione.
  - `semantic/` → logica semantica e di elaborazione.
  - `tools/` → utility e funzioni di supporto.
- File di supporto condivisi devono avere il suffisso `_utils.py`.
- Nessun file deve superare **500 righe** di codice: se necessario, suddividere in moduli.

---

## 🧩 Naming e convenzioni

- **File e cartelle**: snake\_case, nomi descrittivi, evitare abbreviazioni ambigue.
- **Classi**: PascalCase.
- **Funzioni e variabili**: snake\_case.
- **Costanti**: UPPER\_SNAKE\_CASE, definite in `pipeline/constants.py` o moduli equivalenti.
- Nessun uso di camelCase.

---

## ⚙️ Funzioni e parametri

- Nessuna variabile globale (tranne costanti).
- Massimo **5 parametri** per funzione; oltre, raggruppare in oggetti o dict.
- Funzioni CLI devono usare `argparse` e fornire `--help`.
- Ogni funzione deve avere una docstring che descrive:
  - Scopo
  - Parametri e tipi
  - Valore di ritorno
  - Eventuali eccezioni sollevate

---

## 🛠 Logging e gestione errori

- Usare esclusivamente `pipeline/logging_utils.py` per il logging.
- Livelli consentiti: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Messaggi chiari e contestuali: includere sempre il nome del modulo e il contesto dell’operazione.
- Gli errori critici devono essere gestiti con messaggi chiari per l’utente e stack trace nel log.

---

## 🔄 Workflow di sviluppo

1. Creare un branch per ogni feature o bugfix.
2. Seguire la convenzione di naming branch: `feature/<descrizione>` o `fix/<descrizione>`.
3. Aggiornare la documentazione quando il codice cambia.
4. Aggiornare il `CHANGELOG.md` prima di un merge in `main`.
5. Aprire una Pull Request con descrizione chiara e link a eventuali issue.

---

## 🧪 Testing

- I test vanno in `tests/` e devono seguire la struttura `test_<modulo>.py`.
- Usare `pytest` come framework principale.
- Preferire test end-to-end, ma includere test unitari per funzioni critiche.
- I test non devono contenere dati sensibili.
- Comando di esecuzione tipico:

```bash
pytest tests/ --maxfail=1 --disable-warnings -q
```

---

## 🔐 Sicurezza e configurazioni

- Nessuna credenziale hardcoded: tutte devono essere in `.env`.
- File `.env` non deve essere tracciato su Git.
- Configurazioni YAML in `config/` devono essere validate.
- Le path devono essere validate con `is_safe_subpath`.

---

## 🎯 Principi generali NeXT

- **Modularità**: ogni componente deve essere sostituibile senza impatti estesi.
- **Trasparenza**: ogni passaggio deve essere tracciabile e comprensibile.
- **Scalabilità**: il codice deve poter essere esteso con il minimo sforzo.
- **Affidabilità**: priorità alla robustezza rispetto alla velocità di sviluppo.
- **Coerenza**: uniformità di stile, nomi e comportamenti in tutto il codice.

---

## 📚 Collegamenti utili

- [Architettura tecnica](architecture.md)
- [Guida sviluppatore](developer_guide.md)
- [Guida utente](user_guide.md)

