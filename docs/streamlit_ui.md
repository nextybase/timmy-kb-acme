# Streamlit (UI) — Regole 2025 · Add-on a `coding_rule.md`

**Baseline**: target `Streamlit==1.50.*` (compat ≥ 1.45). Evitare API `experimental`/`beta` in produzione.

---

## Deprecazioni → Migrazioni obbligatorie

| Obsoleto                                                               | Sostituisci con                             | Regola d’uso                                                                                                                 |
| ---------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `st.experimental_get_query_params`, `st.experimental_set_query_params` | `st.query_params`                           | API dict-like: lettura/scrittura atomica, `clear()`, `from_dict()`, `get_all()` per chiavi ripetute.                         |
| `st.experimental_rerun`                                                | `st.rerun`                                  | Rerun esplicito; rimuovere prefisso experimental.                                                                            |
| `st.cache`                                                             | `@st.cache_data` **o** `@st.cache_resource` | **Data**: funzioni pure, return pickleable; usare `ttl`/`max_entries`. **Resource**: client/connessioni/modelli thread-safe. |
| `st.experimental_memo`                                                 | `@st.cache_data`                            | Stesse regole di caching dati.                                                                                               |
| `st.experimental_singleton`                                            | `@st.cache_resource`                        | Stesse regole di caching risorse.                                                                                            |
| `st.experimental_data_editor`                                          | `st.data_editor`                            | Cambia formato in `st.session_state` (usare `edited_rows`).                                                                  |
| Navigazione via directory `pages/`                                     | `st.navigation` + `st.Page`                 | Router unico nell’entrypoint; opzionale `position="top"`. `pages/` ignorata se usi `st.navigation`.                          |
| `st.experimental_user`                                                 | `st.user`                                   | Oggetto read-only con info utente; per OIDC usare `st.login()`/`st.logout()`.                                                |

> **Nota**: rimuovere ogni utilizzo residuo di `st.experimental_*`.

---

## Pattern prescritti

### Query params

```python
# Lettura
q = st.query_params.to_dict()

# Scrittura / aggiornamento
st.query_params["slug"] = slug
st.query_params.from_dict({"tab": "settings", "filters": ["a", "b"]})

# Pulizia
st.query_params.clear()
```

### Navigazione multipagina

```python
pages = {
    "Onboarding": [
        st.Page("ui/pre_onboarding.py", title="Pre-Onboarding"),
        st.Page("ui/onboarding.py", title="Onboarding"),
    ],
    "Tools": [
        st.Page("ui/cleanup.py", title="Cleanup"),
        st.Page("ui/preview.py", title="Docker Preview"),
    ],
}
pg = st.navigation(pages, position="top")
pg.run()
```

### Caching

```python
@st.cache_data(ttl=600, max_entries=64)
def load_client_docs(slug: str) -> list[str]:
    return fetch_docs(slug)

@st.cache_resource(ttl=3600)
def git_client():
    return make_git_client()

# Evitare widget in funzioni cache ate, salvo necessità:
@st.cache_data(experimental_allow_widgets=True)
def filtered(limit: int):
    lim = st.slider("Limite", 10, 1000, limit)  # entra nel keyspace della cache
    return query(lim)
```

**Regole di caching**

- Non cachiamo segreti o oggetti non pickleable.
- Per parametri da escludere dal key hashing, usare prefissi convenzionali (es. `_arg`).

### Stato & layout

- Ogni widget ha `key` esplicito e condivide stato via `st.session_state[<key>]`.
- Layout nidificati (columns/expanders/dialog/chat) consentiti, ma max **2 livelli reali**: priorità alla leggibilità (anche mobile).
- Grafici: non forzare `use_container_width=True` se non necessario (è spesso default).
- Tema runtime: `st.context.theme` (`"light" | "dark"`); usare micro-pattern visivi coerenti.

```python
mode = st.context.theme  # "light" | "dark"
st.badge("OK", variant="success")
```

### Sicurezza UI

- `st.html(...)` è sanificato e **non esegue JS**: usarlo solo per markup controllato.
- CSS locale: preferire file dedicati; evitare HTML non fidato.

---

## Definition of Done (UI)

- Nessun simbolo `experimental`/`beta` nel codice.
- Navigazione unificata con `st.navigation` (no mix con `pages/`).
- Solo `@st.cache_data` / `@st.cache_resource` per caching; verifiche di memoria su filtri con widget.
- Query string gestita esclusivamente via `st.query_params`.
- Se presente auth OIDC: `st.login()`/`st.logout()` e `st.user` (no `experimental_user`).

---

## Checklist migrazioni immediate

-
