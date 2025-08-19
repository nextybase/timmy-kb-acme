# Policy di Push – Timmy-KB (v1.0.4)

Questa policy definisce quando e **come** eseguire il push dei contenuti generati dalla pipeline verso il repository remoto.  
È allineata alle modifiche introdotte in **v1.0.4**: **push incrementale di default** (senza `--force`), orchestratori invariati.

---

## 1) Principi
- La **fonte autoritativa** dei contenuti generati è l’**output locale** della pipeline (`output/timmy-kb-<slug>/book/`).
- Il push deve **riflettere esattamente** lo stato dell’output locale validato (nessuna modifica manuale in pubblicazione).
- Il branch di destinazione è letto da **`GIT_DEFAULT_BRANCH`** (fallback: `main`).

---

## 2) Pre-condizioni per il push
Esegui il push solo se:
1. La fase di conversione ha prodotto `book/` valido (inclusi `README.md` e `SUMMARY.md`).
2. Non vi sono errori nei log ed il codice di uscita è `0`.
3. Hai un **token valido** in `GITHUB_TOKEN` (oppure desideri esplicitamente **non** eseguire il push).
4. Il branch di destinazione è configurato e coerente con la tua strategia (`GIT_DEFAULT_BRANCH`).

> In **modalità non-interattiva**, il push è **disabilitato** a meno di `--push` esplicito.

---

## 3) Modalità operative
### Interattiva
- Al termine della pipeline, viene chiesto se eseguire il push (default **NO**).  
- Se confermi, la pipeline esegue `push_output_to_github(...)` sul branch da `GIT_DEFAULT_BRANCH`.

### Non-interattiva / CI
- Il push è **NO** per default. Abilitalo con `--push`.  
- Se `GITHUB_TOKEN` non è impostato, il push fallisce: usa `--no-push` o configura il token.

---

## 4) **Modalità di push (default: incrementale, senza force)**
Il push avviene in modo **incrementale**:
1. **Clone** del repo remoto in una working dir temporanea **dentro** `output/timmy-kb-<slug>/`  
   (es. `output/timmy-kb-<slug>/.push_<rand>`).
2. **Checkout** del branch (`GIT_DEFAULT_BRANCH`; se assente, viene creato).
3. **Sync iniziale**: `git pull --rebase origin <branch>` se il branch esiste.
4. **Copia** dei soli `*.md` (esclusi `.bak`) da `book/` nella working dir clonata, preservando la struttura.
5. **Stage & commit**: `git add -A` → commit **solo se** ci sono modifiche.
6. **Push**: `git push origin <branch>` (**senza `--force`**).
7. **Retry automatico (1x)** in caso di rifiuto non-fast-forward: `pull --rebase` + nuovo `push`.
8. **Conflitti**: se il rebase produce conflitti, il push viene **interrotto** con un errore chiaro.  
   Suggerimenti: usare un **branch dedicato** e aprire una PR, oppure pianificare un push forzato approvato.

**Nota sicurezza**
- La working dir temporanea è **interna** a `output/timmy-kb-<slug>` per garantire path-safety.
- Il token GitHub è passato come header HTTP tramite `GIT_HTTP_EXTRAHEADER` (non compare nella command line).

---

## 5) Uso di `--no-push` e casi d’uso
- **Validazione locale**: usa `--no-push` per ispezionare i Markdown generati, indici e collegamenti.
- **Debug**: durante test/bugfix evita side-effect remoti.
- **Approvals**: in scenari con revisione umana, conserva lo stato locale finché non ottieni l’ok.

---

## 6) Quando (e come) considerare il push forzato
Evita il `--force` salvo necessità, ad esempio per riallineare rapidamente lo stato remoto quando:
- il branch remoto è **divergente** per modifiche manuali non più desiderate;
- è necessario **riscrivere** la storia pubblicata per allinearla alla pipeline.

**Linee guida per il force-push**
1. Informare il team e ottenere approvazione.
2. Taggare la release precedente (rollback facile).
3. Eseguire il push forzato solo sul branch definito in `GIT_DEFAULT_BRANCH`.
4. Annotare il motivo nel `CHANGELOG`.

---

## 7) Verifiche consigliate prima del push
- [ ] `book/` contiene tutti i `.md` attesi; `SUMMARY.md` e `README.md` coerenti.
- [ ] Link interni funzionanti (anteprima consigliata; se Docker non è disponibile, prosegui senza preview).
- [ ] Log senza errori; exit code `0`.
- [ ] `GITHUB_TOKEN` impostato; branch da `GIT_DEFAULT_BRANCH` corretto.

---

## 8) Esempi
**Interattivo con push su conferma**
```bash
py src/onboarding_full.py --slug acme
# conferma prompt di push

### CI non-interattivo con push esplicito
```bash
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --push --non-interactive

### Branch dedicato “safe” (PR verso main)
```bash
export GIT_DEFAULT_BRANCH="kb/acme-20250819"
py src/onboarding_full.py --slug acme --no-drive --push --non-interactive

## 9) Anti-pattern

- Eseguire push con book/ incompleto o non validato.
- Pubblicare modifiche manuali direttamente sul remoto senza rigenerazione pipeline.
- Confidare nel force-push come routine: deve restare un’eccezione governata.

**Stato**: policy allineata a v1.0.4. Default aggiornato: push incrementale senza force; orchestratori invariati.