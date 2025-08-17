# tests/test_exceptions.py
import inspect
import types
import pytest

import pipeline.exceptions as ex


def test_exit_codes_is_dict_and_values_are_valid():
    assert isinstance(ex.EXIT_CODES, dict), "EXIT_CODES deve essere un dict"
    # valori 0..255 (compatibili con exit code POSIX)
    for v in ex.EXIT_CODES.values():
        assert isinstance(v, int), "Tutti i valori di EXIT_CODES devono essere int"
        assert 0 <= v <= 255, f"Exit code fuori range: {v}"


def test_error_classes_shape_and_str_message():
    # Raccogliamo tutte le classi nel modulo che sono Exception (e non built-in)
    error_classes = []
    for name, obj in vars(ex).items():
        if isinstance(obj, type) and issubclass(obj, Exception) and obj.__module__ == ex.__name__:
            error_classes.append(obj)

    assert error_classes, "Nessuna classe di eccezione definita in pipeline.exceptions"

    # Ogni eccezione dev’essere istanziabile con un messaggio e preservarlo in str()
    for err_cls in error_classes:
        e = err_cls("msg-di-prova")
        s = str(e)
        assert isinstance(s, str) and "msg-di-prova" in s, f"{err_cls.__name__} non preserva il messaggio in str()"


def test_exit_codes_keys_match_names_or_types_of_errors():
    # Le chiavi di EXIT_CODES possono essere nomi (str) o i tipi stessi
    keys = list(ex.EXIT_CODES.keys())
    # Prendiamo le classi errore dichiarate nel modulo
    error_types = {
        obj.__name__: obj
        for _, obj in vars(ex).items()
        if isinstance(obj, type) and issubclass(obj, Exception) and obj.__module__ == ex.__name__
    }

    # Se sono nomi: esistono tra le classi; se sono tipi: sono subclass di Exception
    for k in keys:
        if isinstance(k, str):
            assert k in error_types, f"Chiave '{k}' non corrisponde a nessuna eccezione definita"
        elif isinstance(k, type):
            assert issubclass(k, Exception), f"Chiave {k} non è un tipo di eccezione"
        else:
            pytest.fail(f"Chiave non supportata in EXIT_CODES: {type(k)}")


def test_no_sys_exit_on_raise_errors(monkeypatch):
    # Verifica che sollevare le eccezioni non invochi sys.exit (deve restare a carico degli orchestratori)
    called = {"exit": False}

    def fake_exit(_code):
        called["exit"] = True
        raise AssertionError("sys.exit non deve essere chiamato dai moduli di eccezioni")

    import sys
    monkeypatch.setattr(sys, "exit", fake_exit, raising=True)

    # Solleviamo una (la prima) delle eccezioni trovate
    error_classes = [
        obj for _, obj in vars(ex).items()
        if isinstance(obj, type) and issubclass(obj, Exception) and obj.__module__ == ex.__name__
    ]
    assert error_classes, "Nessuna eccezione da testare"

    with pytest.raises(Exception):
        raise error_classes[0]("boom")

    assert called["exit"] is False
