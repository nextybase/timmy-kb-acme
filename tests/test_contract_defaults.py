import inspect

from timmykb.tag_onboarding import tag_onboarding_main


def test_tag_onboarding_default_is_drive():
    sig = inspect.signature(tag_onboarding_main)
    assert sig.parameters["source"].default == "drive"
