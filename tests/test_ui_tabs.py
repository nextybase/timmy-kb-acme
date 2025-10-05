import importlib
import sys
import types
from pathlib import Path


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

        stub.sidebar = types.SimpleNamespace(
            button=_noop, markdown=_noop_none, image=_noop_none, link_button=_noop_none
        )
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
        stub.get_option = lambda *_args, **_kwargs: None
        stub.title = _noop_none
        stub.caption = _noop_none
        stub.divider = _noop_none
        stub.header = _noop_none

        class _Column:
            def image(self, *_a, **_k):
                return None

            def title(self, *_a, **_k):
                return None

            def caption(self, *_a, **_k):
                return None

            def markdown(self, *_a, **_k):
                return None

            def metric(self, *_a, **_k):
                return None

            def button(self, *_a, **_k):
                return False

        def _columns(layout):
            return [_Column() for _ in layout]

        stub.columns = _columns
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
    assert ui._compute_manage_enabled("inizializzato", slug="demo") is True
    assert ui._compute_manage_enabled("Pronto", slug=None) is True
    assert ui._compute_manage_enabled("arricchito", slug="demo") is True
    assert ui._compute_manage_enabled("finito", slug="demo") is True
    assert ui._compute_manage_enabled("bozza", slug="demo") is True
    assert ui._compute_manage_enabled(None, slug="demo") is True
    assert ui._compute_manage_enabled(None, slug=None) is False
    assert ui._compute_home_enabled("inizializzato", slug="demo") is True
    assert ui._compute_home_enabled("bozza", slug="demo") is True
    assert ui._compute_home_enabled(None, slug="demo") is True
    assert ui._compute_home_enabled(None, slug=None) is False


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
    ui._init_tab_state(home_enabled=True, manage_enabled=True, sem_enabled=True)
    assert streamlit.session_state["active_tab"] == ui.TAB_MANAGE

    streamlit.session_state["active_tab"] = ui.TAB_HOME
    ui._init_tab_state(home_enabled=False, manage_enabled=False, sem_enabled=False)
    assert streamlit.session_state["active_tab"] == ui.TAB_HOME


def test_resolve_theme_logo_path_respects_theme(monkeypatch):
    _ensure_streamlit_stub()
    streamlit = importlib.import_module("streamlit")
    core = importlib.import_module("src.ui.utils.core")
    repo_root = Path(__file__).resolve().parents[1]

    streamlit.session_state.clear()
    monkeypatch.setattr(streamlit, "get_option", lambda key: "dark" if key == "theme.base" else None, raising=False)
    assert core.get_theme_base() == "dark"
    dark_logo = core.resolve_theme_logo_path(repo_root)
    assert dark_logo.name == "next-logo-bianco.png"

    streamlit.session_state.clear()
    monkeypatch.setattr(streamlit, "get_option", lambda key: "light" if key == "theme.base" else None, raising=False)
    assert core.get_theme_base() == "light"
    light_logo = core.resolve_theme_logo_path(repo_root)
    assert light_logo.name == "next-logo.png"


def test_render_quick_nav_sidebar_targets_correct_container(monkeypatch):
    _ensure_streamlit_stub()
    streamlit = importlib.import_module("streamlit")
    app = importlib.import_module("src.ui.app")
    importlib.reload(app)

    sidebar_calls: list[tuple[str, str]] = []
    main_calls: list[tuple[str, str]] = []

    def _sidebar_markdown(text: str, **_kwargs: object) -> None:
        sidebar_calls.append(("sidebar", text))

    def _main_markdown(text: str, **_kwargs: object) -> None:
        main_calls.append(("main", text))

    monkeypatch.setattr(streamlit.sidebar, "markdown", _sidebar_markdown, raising=False)
    monkeypatch.setattr(streamlit, "markdown", _main_markdown, raising=False)

    app.render_quick_nav_sidebar(sidebar=True)
    assert sidebar_calls and all(target == "sidebar" for target, _ in sidebar_calls)
    assert not main_calls

    sidebar_calls.clear()
    main_calls.clear()

    app.render_quick_nav_sidebar()
    assert main_calls and all(target == "main" for target, _ in main_calls)


def test_sidebar_skiplink_and_quicknav_invokes_nav(monkeypatch):
    _ensure_streamlit_stub()
    streamlit = importlib.import_module("streamlit")
    ui = importlib.import_module("onboarding_ui")

    skip_calls: list[str] = []

    def _sidebar_markdown(text: str, **_kwargs: object) -> None:
        skip_calls.append(text)

    monkeypatch.setattr(streamlit.sidebar, "markdown", _sidebar_markdown, raising=False)

    nav_calls: list[bool] = []

    def _fake_import(name: str):
        assert name == "src.ui.app"
        return types.SimpleNamespace(render_quick_nav_sidebar=lambda *, sidebar=False: nav_calls.append(sidebar))

    monkeypatch.setattr(ui, "importlib", types.SimpleNamespace(import_module=_fake_import))

    ui._sidebar_skiplink_and_quicknav()

    assert nav_calls == [True]
    assert any("#main" in text for text in skip_calls)
