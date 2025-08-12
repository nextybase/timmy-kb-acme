# Contributing – Timmy-KB

Grazie per il tuo interesse a contribuire a **Timmy-KB**! Segui queste linee guida per garantire coerenza e qualità nel codice e nella documentazione.

---

## 📌 Come iniziare
1. **Fork** del repository e crea un branch dedicato:
   ```bash
   git checkout -b feature/nome-funzionalita
   ```
2. Assicurati di avere Python 3.9+ e tutte le dipendenze installate.
3. Configura variabili `.env` e file YAML in `config/` se necessari.

---

## 🛠 Stile di sviluppo
- Segui le regole definite in [`docs/coding_rules.md`](docs/coding_rules.md).
- Mantieni separazione tra moduli `pipeline/`, `semantic/` e `tools/`.
- Usa **logging strutturato** tramite `pipeline/logging_utils.py`.
- Niente `print()` nei moduli di produzione.
- Evita hardcoding di percorsi o credenziali: usa configurazione esterna.

---

## 🧪 Test
- I nuovi contributi devono includere test pertinenti.
- Esegui i test prima di creare la pull request:
  ```bash
  pytest tests/
  ```
- Mantieni il codice compatibile con la struttura esistente.

---

## 🔄 Processo Pull Request
1. **Commit chiari e descrittivi**:
   - Usa il formato: `tipo: descrizione breve` (es. `fix: corregge parsing PDF`).
   - Esempi di tipi: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
2. Aggiorna il `CHANGELOG.md` nella sezione *Unreleased* con le modifiche.
3. Apri la PR verso il branch `main`.
4. Compila il template PR fornito.
5. Aspetta la revisione e applica eventuali modifiche richieste.

---

## 🛡 Licenza
Contribuendo accetti che il tuo codice sia rilasciato sotto la licenza [MIT](LICENSE).

---

Per domande o chiarimenti, apri una **issue** o contatta il team di mantenimento.

