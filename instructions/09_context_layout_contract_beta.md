# 09 — Context/Layout Contract (1.0 Beta, envelope chiuso)

**Status:** CONGELATO (definitivo per 1.0 Beta)
**Scope:** contratto normativo per Context/Layout e derivazione path nel workspace cliente
**Authority:** questo documento è vincolante e non introduce HOW/implementazioni

## Scopo
Definire il contratto definitivo “Context/Layout” per la 1.0 Beta: un solo perimetro valido, nessun fallback silenzioso, fail-fast obbligatorio.

## Definizioni (minime)
- **context**: oggetto di contesto di esecuzione (slug, repo_root_dir, config) usato per costruire il layout.
- **WorkspaceLayout**: struttura che espone i path canonici del workspace cliente.
- **repo_root_dir**: root del repository; è un input obbligatorio del contratto.

## 1) Single Source of Truth (SSoT)
- `WorkspaceLayout.from_context(context)` MUST essere l’unica fonte di verità per i path canonici.
- Qualsiasi path usato dal runtime MUST derivare dal `WorkspaceLayout` risultante.

## 2) `repo_root_dir` (obbligatorio, nessun alias)
- `repo_root_dir` MUST essere presente sempre.
- `repo_root_dir` MUST NOT essere derivato da CWD, env, heuristics, risalita directory, o valori “di comodo”.
- `base_dir` FORBIDDEN come alias/alternativa per derivare o sostituire `repo_root_dir`.

## 3) Path derivati (layout-first)
- `raw_dir`, `book_dir` (o `md_dir`), `semantic_dir`, `logs_dir`, `config_dir` MUST essere ottenuti dal `WorkspaceLayout`.
- I consumer (UI/CLI/services/tools runtime) MUST NOT:
  - leggere `context.*_dir` (se presenti),
  - ricostruire path concatenando stringhe,
  - calcolare path “equivalenti” fuori dal layout.

Esempio minimo ammesso (solo illustrativo):
```
layout = WorkspaceLayout.from_context(context)
raw_dir = layout.raw_dir
book_dir = layout.book_dir
```

## 4) Divieti espliciti (pattern proibiti)
I seguenti pattern sono FORBIDDEN quando coinvolgono path/config critici o campi obbligatori del contratto:

### 4.1 `getattr` con default
```
getattr(context, "repo_root_dir", None)
getattr(context, "raw_dir", default)
```

### 4.2 OR-chain / defaulting implicito
```
repo_root = context.repo_root_dir or Path.cwd()
raw_dir = context.raw_dir or (repo_root / "output" / slug / "raw")
```

### 4.3 try/except assorbenti (error masking)
```
try:
    layout = WorkspaceLayout.from_context(context)
except Exception:
    layout = WorkspaceLayout.from_defaults(...)
```

### 4.4 default silenziosi su campi/dir obbligatori
Qualsiasi comportamento che “prosegue” senza `repo_root_dir` o senza layout valido è FORBIDDEN.

## 5) Error policy (fail-fast, rumorosa, esplicita)
- Ogni violazione di questo contratto MUST essere trattata come **errore contrattuale**.
- L’errore MUST essere **fail-fast**, **rumoroso** (log/evento esplicito) e **non recuperato** implicitamente.
- Nessuna recovery implicita è ammessa: MUST NOT esistere “auto-fix” silenziosi o fallback automatici per tornare in un percorso alternativo.

## 6) Distinzione fondamentale: HiTL checkpoint ≠ fallback
- Un **checkpoint HiTL** è uno STOP governato: blocca il progresso finché non esiste una decisione/artefatto umano previsto dal contratto.
- Un **fallback** è un percorso alternativo che permette di proseguire senza decisione esplicita: è FORBIDDEN nel perimetro Beta.
- I checkpoint HiTL MUST essere espliciti, tracciabili e non ambigui; non costituiscono alternative al contratto, ma condizioni per continuare dentro l’envelope.

## 7) Perimetro Beta (runtime critico)
- Il runtime critico Beta riconosce **un solo contratto** Context/Layout: quello in questo documento.
- Strumenti dev-only/esperimenti MAY esistere solo fuori dal runtime critico e MUST NOT introdurre pluralità di contratti (né path derivati alternativi, né fallback).
