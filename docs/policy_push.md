# Policy di Push  —  Timmy-KB (v1.6.1)

Questa policy definisce come eseguire il push su GitHub in modo sicuro, tracciabile e riproducibile.

## 1) Responsabilità e orchestratori

- **`semantic_onboarding.py`**: conversione RAW → BOOK, enrichment, README/SUMMARY, preview Docker. **Non fa push.**
  - La UI Streamlit non usa direttamente gli helper interni ma passa dalla façade `semantic.api` (API pubblica stabile).
- **`onboarding_full.py`**: esegue **solo** il push GitHub (e in futuro l'integrazione GitBook). Richiede che `book/` sia già pronto.

## 2) Prerequisiti

- `GITHUB_TOKEN` valido (permessi `repo`).
- Repo e branch configurati nel contesto/`config.yaml per cliente`.
- Rete accessibile (CI o locale).

## 3) Regole operative

- **Branch protetti**: push su `main` solo via PR. In CI → merge protetto.
- **Force push**: vietato di default. Consentito solo con:
  - flag espliciti (es. `--force-push` + `--force-ack`) quando previsti dall'orchestratore
  - strategia `--force-with-lease`
  - autorizzazione esplicita in PR/policy team

- **Scope dei contenuti**: versionare solo `book/` e file di progetto necessari. Escludere asset temporanei e `.bak`.
- **Messaggi di commit**: chiari, includere slug cliente e run_id se disponibile (es. `onboarding_full(acme): build book v1.2.1`).

## 4) Sicurezza

- **Token**: non in chiaro nei log; mai in URL. Usare header.
- **Redazione log**: abilitata se `compute_redact_flag(...)` restituisce `True`. Dati sensibili mascherati.
- **Path-safety & atomicità**: garantita a monte in fase di generazione contenuti (`ensure_within`, `safe_write_*`).

## 5) Sequenza tipica (CLI)

```bash
# 1) Prepara contenuti
py src/semantic_onboarding.py --slug acme --non-interactive --no-preview

# 2) Push (solo push)
py src/onboarding_full.py --slug acme --non-interactive
```

Opzioni comuni:
- `--no-preview` (non usato in `onboarding_full.py`, resta per compatibilità in v1.2.x se previsto)
- `--no-push` (non applicabile: l'orchestratore è solo push)
- `--force-with-lease` / `--force-push` (se/quando supportati: usare con cautela)

## 6) Error handling

- Errori di autenticazione → `PushError` con exit code dedicato (40).
- Errori di rete/permessi → log strutturati con contesto (`slug`, branch, repo).
- Nessun fallback locale: se il push fallisce, la pipeline non tenta ritenti non guidati.

## 7) CI / CD

- Pipeline CI deve:
  - validare build/lint/test
  - eseguire `semantic_onboarding.py` (senza preview) su branch di lavoro
  - creare PR verso `main`
  - dopo approvazione, eseguire `onboarding_full.py` (solo push) sul merge in `main`.

## 8) Tracciabilità

- Ogni esecuzione ha `run_id` nei log.
- I commit devono contenere riferimenti minimi (slug, step, versione).
- Conservare i log in `output/timmy-kb-<slug>/logs/`.

## 9) Roadmap integrazione GitBook

- Pubblicazione automatica su GitBook a valle del push (`onboarding_full.py`).
- Gestione token GitBook con redazione log.
- Allineamento contenuti `book/` → spazio GitBook.

> **Nota:** fino al completamento della roadmap, `onboarding_full.py` gestisce esclusivamente il push GitHub.
