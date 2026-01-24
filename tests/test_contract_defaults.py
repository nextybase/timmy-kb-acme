# SPDX-License-Identifier: GPL-3.0-only
import inspect

from timmy_kb.cli.tag_onboarding import tag_onboarding_main


def test_tag_onboarding_does_not_expose_source_parameter():
    sig = inspect.signature(tag_onboarding_main)
    assert "source" not in sig.parameters
