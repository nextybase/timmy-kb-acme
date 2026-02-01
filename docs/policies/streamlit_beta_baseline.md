# Streamlit Baseline for Beta 1.0

Questo documento definisce la **baseline minimale di API Streamlit** richiesta per l'esecuzione Beta 1.0.
Gli ambienti dedicati devono fornire queste API in modo deterministico e stabile; eventuali mancanze
devono essere trattate come errore di provisioning.

## API obbligatorie
1. `st.page_link` - il routing interno (PagePaths, `st.switch_page`) si basa su questa funzione.
2. `st.query_params` - lettura/scrittura dei tab e dello slug avviene tramite questo mapping.
3. `st.toast` - notifiche brevi (es. `ui.utils.logging.show_success`) devono poter inviare toast.
4. `st.progress` - la progress bar (es. `ui.utils.progress.run_with_progress`) deve esistere.
5. `st.json` - il rendering dei payload control-plane (`ui.utils.control_plane.display_control_plane_result`) richiede `json`.

## Strategie di verifica
- L'environment di provisioning deve installare la versione Streamlit usata in CI/production (>= X.Y.Z, che espone le API sopra).
- I tool *smoke* e la documentazione devono riportare chiaramente l'enforcement di queste API (qui e nella policy `docs/policies/environment_certification.md`).
- Se un'app rileva l'assenza di una di queste API deve fallire (raise RuntimeError/ConfigError) invece di fare fallback.

## Riferimenti pratici
- I commenti `TODO(Beta1.0)` in `src/ui/utils/control_plane.py`, `progress.py`, `logging.py`, `route_state.py` puntano a questa policy: rimuovere il fallback una volta che l'ambiente garantisce le API.
- Gli strumenti di test e smoke sono invitati a verificare `st.page_link`/`st.query_params`/`st.toast`/`st.progress`/`st.json` nei loro stub.
