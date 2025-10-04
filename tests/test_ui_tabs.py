import importlib
import sys
import types


def _ensure_streamlit_stub() -> None:
    try:
        streamlit = importlib.import_module("streamlit")
    except ModuleNotFoundError:
        stub = types.ModuleType("streamlit")
        stub.session_state = {}

        def _noop(*_args, **_kwargs):
            return False

        def _noop_none(*_args, **_kwargs):
            return None

        class _Expander:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *_exc: object) -> bool:
                return False

        stub.sidebar = types.SimpleNamespace(button=_noop, markdown=_noop_none)
        stub.button = _noop
        stub.markdown = _noop_none
        stub.toast = _noop_none
        stub.link_button = _noop_none
        stub.metric = _noop_none
        stub.subheader = _noop_none
        stub.info = _noop_none
        stub.error = _noop_none
        stub.write = _noop_none
        stub.download_button = _noop_none
        stub.set_page_config = _noop_none
        stub.expander = lambda *_args, **_kwargs: _Expander()
        stub.empty = lambda: types.SimpleNamespace(info=_noop_none, empty=_noop_none)
        sys.modules["streamlit"] = stub
        streamlit = stub

        runtime_module = types.ModuleType("streamlit.runtime")
        scriptrunner_utils = types.ModuleType("streamlit.runtime.scriptrunner_utils")
        exceptions_mod = types.ModuleType("streamlit.runtime.scriptrunner_utils.exceptions")

        class RerunException(Exception):
            pass

        exceptions_mod.RerunException = RerunException
        scriptrunner_utils.exceptions = exceptions_mod
        runtime_module.scriptrunner_utils = scriptrunner_utils
        streamlit.runtime = types.SimpleNamespace(scriptrunner_utils=scriptrunner_utils)
        sys.modules["streamlit.runtime"] = runtime_module
        sys.modules["streamlit.runtime.scriptrunner_utils"] = scriptrunner_utils
        sys.modules["streamlit.runtime.scriptrunner_utils.exceptions"] = exceptions_mod
    else:
        runtime_attr = getattr(streamlit, "runtime", None)
        s_utils = getattr(runtime_attr, "scriptrunner_utils", None) if runtime_attr else None
        exceptions_mod = getattr(s_utils, "exceptions", None) if s_utils else None
        if exceptions_mod is None or not hasattr(exceptions_mod, "RerunException"):
            exceptions_mod = types.ModuleType("streamlit.runtime.scriptrunner_utils.exceptions")

            class RerunException(Exception):
                pass

            exceptions_mod.RerunException = RerunException
            scriptrunner_utils = types.SimpleNamespace(exceptions=exceptions_mod)
            runtime_module = types.SimpleNamespace(scriptrunner_utils=scriptrunner_utils)
            streamlit.runtime = runtime_module
            sys.modules["streamlit.runtime.scriptrunner_utils"] = scriptrunner_utils  # type: ignore[assignment]
            sys.modules["streamlit.runtime.scriptrunner_utils.exceptions"] = exceptions_mod


def test_compute_sem_enabled():
    _ensure_streamlit_stub()
    ui = importlib.import_module("onboarding_ui")
    assert ui._compute_sem_enabled("pronto") is True
    assert ui._compute_sem_enabled("arricchito") is True
    assert ui._compute_sem_enabled("finito") is True
    assert ui._compute_sem_enabled("bozza") is False
    assert ui._compute_sem_enabled(None) is False


def test_compute_manage_and_home_enabled():
    _ensure_streamlit_stub()
    ui = importlib.import_module("onboarding_ui")
    assert ui._compute_manage_enabled("inizializzato") is True
    assert ui._compute_manage_enabled("Pronto") is True
    assert ui._compute_manage_enabled("arricchito") is True
    assert ui._compute_manage_enabled("finito") is True
    assert ui._compute_manage_enabled("bozza") is False
    assert ui._compute_manage_enabled(None) is False
    assert ui._compute_home_enabled("inizializzato") is True
    assert ui._compute_home_enabled("bozza") is False


def test_init_tab_state_resets_tabs(monkeypatch):
    _ensure_streamlit_stub()
    ui = importlib.import_module("onboarding_ui")
    streamlit = importlib.import_module("streamlit")

    streamlit.session_state.clear()
    streamlit.session_state["active_tab"] = ui.TAB_SEM
    ui._init_tab_state(home_enabled=True, manage_enabled=True, sem_enabled=False)
    assert streamlit.session_state["active_tab"] == ui.TAB_HOME

    streamlit.session_state["active_tab"] = ui.TAB_MANAGE
    ui._init_tab_state(home_enabled=True, manage_enabled=False, sem_enabled=True)
    assert streamlit.session_state["active_tab"] == ui.TAB_HOME

    streamlit.session_state["active_tab"] = ui.TAB_HOME
    ui._init_tab_state(home_enabled=False, manage_enabled=False, sem_enabled=False)
    assert streamlit.session_state["active_tab"] == ui.TAB_HOME
