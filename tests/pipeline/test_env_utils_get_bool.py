# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from typing import Dict

from pipeline.env_utils import get_bool


class TestGetBool(unittest.TestCase):
    def test_truthy_values_true(self) -> None:
        data: Dict[str, str] = {"A": "1", "B": "true", "C": "Yes", "D": "On"}
        for key, value in data.items():
            with self.subTest(value=value):
                self.assertTrue(get_bool(key, default=False, env=data))

    def test_falsy_values_false(self) -> None:
        data: Dict[str, str] = {"A": "0", "B": "false", "C": "No", "D": "Off"}
        for key, value in data.items():
            with self.subTest(value=value):
                self.assertFalse(get_bool(key, default=True, env=data))

    def test_missing_returns_default(self) -> None:
        data: Dict[str, str] = {}
        self.assertTrue(get_bool("MISSING", default=True, env=data))
        self.assertFalse(get_bool("MISSING", default=False, env=data))

    def test_unrecognized_returns_default(self) -> None:
        data: Dict[str, str] = {"FLAG": "maybe"}
        self.assertTrue(get_bool("FLAG", default=True, env=data))
        self.assertFalse(get_bool("FLAG", default=False, env=data))

    def test_env_none_uses_os_environ(self) -> None:
        import os

        key = "TEST_BOOL_ENV_UTILS"
        os.environ[key] = "true"
        try:
            self.assertTrue(get_bool(key, default=False, env=None))
        finally:
            os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()
