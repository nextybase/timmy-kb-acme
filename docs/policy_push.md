# Policy di Push – Timmy‑KB (v1.0.4 Stable)

Questa policy definisce quando e come eseguire il **push** dei contenuti generati dalla pipeline verso il repository remoto (e, a cascata, gli spazi di pubblicazione). È coerente con le modifiche della sessione corrente e con il CHANGELOG 1.0.3.

---

## 1) Principi
- La **fonte autoritativa** dei contenuti generati è l’**output locale** della pipeline (`output/timmy-kb-<slug>/book/`).
- Il push deve **riflettere esattamente** lo stato dell’output locale validato (nessuna modifica manuale in pubblicazione).
- Il branch di destinazione è letto da **`GIT_DEFAULT_BRANCH`** (fallback: `main`).

---

## 2) Pre‑condizioni per il push
Esegui il push solo se:
1. La fase di conversione ha prodotto `book/` valido (inclusi `README.md` e `SUMMARY.md`).
2. Non vi sono errori nei log (`onboarding.log`), e gli **Exit Codes** sono `0`.
3. Hai un **token valido** in `GITHUB_TOKEN` (oppure desideri esplicitamente **non** eseguire il push).
4. Il branch di destinazione è configurato e coerente con la tua strategia (`GIT_DEFAULT_BRANCH`).

> In **modalità non‑interattiva**, il push è **disabilitato** a meno di `--push` esplicito.

---

## 3) Modalità operative
### Interattiva
- Al termine della pipeline, viene chiesto se eseguire il push (default **NO**).  
- Se confermi, la pipeline esegue `push_output_to_github(...)` sul branch da `GIT_DEFAULT_BRANCH`.

### Non‑interattiva / CI
- Il push è **NO** per default. Abilitalo con `--push`.  
- Se `GITHUB_TOKEN` non è impostato, il push fallisce: usa `--no-push` o configura il token.

---

## 4) Uso di `--no-push` e casi d’uso
- **Validazione locale**: usa `--no-push` per ispezionare i Markdown generati, eventuali indici e collegamenti.
- **Debug**: durante test/bugfix evita side‑effect remoti.
- **Approvals**: in scenari con revisione umana, conserva lo stato locale finché non ottieni l’ok.

---

## 5) Quando (e come) usare `--force`
Evita il `--force` salvo necessità. Può servire per riallineare rapidamente lo stato remoto con l’output locale quando:
- il branch remoto è **divergente** per modifiche manuali non più desiderate,
- è necessario **riscrivere** la storia del contenuto pubblicato per allinearlo alla pipeline.

**Linee guida `--force`**:
1. Informare il team e ottenere approvazione.
2. Taggare la release precedente in modo da poterla recuperare.
3. Eseguire il push forzato solo dal branch definito in `GIT_DEFAULT_BRANCH`.
4. Aggiornare il `CHANGELOG` indicando il motivo del force‑push.

---

## 6) Verifiche consigliate prima del push
- [ ] `book/` contiene tutti i `.md` attesi; `SUMMARY.md` e `README.md` sono coerenti.
- [ ] Link interni funzionanti (puoi usare la **preview**; se Docker non è disponibile, continua senza anteprima).
- [ ] `onboarding.log` non contiene errori; l’esecuzione è uscita con codice `0`.
- [ ] `GITHUB_TOKEN` impostato; branch da `GIT_DEFAULT_BRANCH` corretto.

---

## 7) Esempi
**Interattivo con push su conferma**
```bash
py src/onboarding_full.py --slug acme
# conferma prompt di push
```

**CI non‑interattivo con push esplicito**
```bash
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --push --non-interactive
```

**Dry‑run locale senza push**
```bash
py src/onboarding_full.py --slug demo --no-drive --no-push
```

---

## 8) Anti‑pattern
- Eseguire push con `book/` **incompleto** o non validato.
- Pubblicare modifiche manuali direttamente nello spazio remoto **senza** rigenerazione pipeline.
- Forzare il push senza condividere la decisione o senza taggare lo stato precedente.

---

**Stato:** policy allineata a v1.0.4, retro‑compatibile. Nessun cambio di flusso.
