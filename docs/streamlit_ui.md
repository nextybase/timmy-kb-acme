# Streamlit (UI) - Regole 2025 - Add-on a `coding_rule.md` (v2.1.0)

**Baseline**: target `Streamlit==1.50.*` (compat ≥ 1.45). Evitare API `experimental`/`beta` in produzione.

---

## Deprecazioni → Migrazioni obbligatorie

| Obsoleto                                                               | Sostituisci con                             | Regola d’uso                                                                                                                   |
| ---------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `st.experimental_get_query_params`, `st.experimental_set_query_params` | `st.query_params`                           | API dict-like: lettura/scrittura atomica; disponibili `clear()`, `from_dict()`, `get_all()`, `to_dict()`.                      |
| `st.experimental_rerun`                                                | `st.rerun`                                  | Rerun esplicito; rimuovere prefisso experimental.                                                                              |
| `st.cache`                                                             | `@st.cache_data` **o** `@st.cache_resource` | **Data**: funzioni pure, return pickleable, imposta `ttl`/`max_entries`. **Resource**: client/connessioni/modelli thread-safe. |
| `st.experimental_memo`                                                 | `@st.cache_data`                            | Stesse regole di caching dati.                                                                                                 |
| `st.experimental_singleton`                                            | `@st.cache_resource`                        | Stesse regole di caching risorse.                                                                                              |
| `st.experimental_data_editor`                                          | `st.data_editor`                            | Adegua la gestione stato: da `edited_cells` a `edited_rows` (formato diverso).                                                 |
| Navigazione via directory `pages/`                                     | `st.navigation` + `st.Page`                 | Entry-point come router; `pages/` viene **ignorata** se usi `st.navigation`. `position="sidebar"\|"top"`.                      |
| `st.experimental_user`                                                 | `st.user`                                   | Oggetto read-only con info utente; per OIDC usa `st.login()`/`st.logout()` e configura `[auth]` in `secrets.toml`.             |

> **Nota**: rimuovere ogni utilizzo residuo di `st.experimental_*`.

---

## Larghezze & altezze — Migrazioni grafiche (2025)

| Componente           | Deprecato                                       | Usa invece                                                  | Mappatura rapida                           |
| -------------------- | ----------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------ |
| `st.image`           | `use_column_width` / `use_container_width`      | `width="content"\|"stretch"\|<int>`                         | `True`→`"stretch"`, `False`→`"content"`.   |
| `st.dataframe`       | `use_container_width`                           | `width="stretch"\|"content"\|<int>`, `height="auto"\|<int>` | Preferisci `width="stretch"`.              |
| `st.data_editor`     | `use_container_width`                           | `width="stretch"\|"content"\|<int>`, `height="auto"\|<int>` | Uniformare anche lo stato (`edited_rows`). |
| `st.pyplot`          | `use_container_width`, figura globale implicita | `width="stretch"\|"content"\|<int>` **e** `fig=` esplicito  | Passa sempre `fig`; globale **deprecata**. |
| `st.graphviz_chart`  | `use_container_width`                           | `width="stretch"\|"content"\|<int>`                         | 1:1.                                       |
| `st.download_button` | `use_container_width`                           | `width="stretch"\|"content"\|<int>`                         | 1:1.                                       |
| `st.button`          | `use_container_width`                           | `width="stretch"\|"content"\|<int>`                         | 1:1.                                       |
| `st.link_button`     | `use_container_width`                           | `width="stretch"\|"content"\|<int>`                         | 1:1.                                       |

**Regole pratiche**

- Default consigliato: `width="stretch"` per componenti principali; usa `"content"` quando serve dimensione naturale.
- Evita `use_(container|column)_width` in nuove PR; migra i warning esistenti.

---

## HTML sicuro (UI)

- Usa `` per HTML/CSS *senza JS*. È sanificato; accetta stringhe o path locali (un file `.css` viene iniettato come `<style>`).
- Evita `st.markdown(..., unsafe_allow_html=True)` in produzione: sostituiscilo con `st.html(...)` per ancore/badge/snippet stilistici.
- Per HTML+JS, usa componenti (`streamlit.components.v1.html`) e trattali come dipendenze da auditare.

**Pattern**

```python
# Ancore / micro-markup
st.html("<a id='top'></a>")

# Badge semplice (HTML+CSS inline)
st.html("""
<span style="padding:.2rem .5rem;border-radius:999px;background:#E8F5E9;color:#2E7D32;font:600 12px/1.2 system-ui;">OK</span>
""")

# CSS locale
from pathlib import Path
st.html(Path("assets/app.css"))
```

**Sicurezza**

1. Non interpolare input utente crudi in HTML. 2) Evita asset remoti non necessari. 3) Per JS reale, usa componenti in iframe.

---

## Pattern prescritti

### Query params

```python
q = st.query_params.to_dict()
st.query_params["slug"] = slug
st.query_params.from_dict({"tab": "settings", "filters": ["a", "b"]})
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

# Evitare widget nei cached salvo necessità
@st.cache_data(experimental_allow_widgets=True)
def filtered(limit: int):
    lim = st.slider("Limite", 10, 1000, limit)
    return query(lim)
```

### Stato & layout

- Ogni widget ha `key` esplicito; stato condiviso via `st.session_state`.
- Layout nidificati max **2 livelli** per leggibilità (anche mobile).
- Tema runtime: `st.get_option("theme.base")`; lascia a Streamlit la gestione del toggle.
  Il CSS brand viene iniettato senza interferire con il tema.

---

## Definition of Done (UI)

- Nessun simbolo `experimental`/`beta` nel codice.
- **Zero** `use_column_width` / `use_container_width` nei sorgenti; usare `width=`/`height=`.
- Navigazione unificata con `st.navigation` (no mix con `pages/`).
- Solo `@st.cache_data` / `@st.cache_resource` per caching; verifiche memoria su filtri.
- Query string solo via `st.query_params`.
- Se presente auth OIDC: `st.login()`/`st.logout()` e `st.user`.
