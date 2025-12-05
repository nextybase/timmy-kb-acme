# SPDX-License-Identifier: GPL-3.0-only
from pipeline.config_utils import ClientEnvSettings


def test_client_env_settings_instantiation() -> None:
    settings = ClientEnvSettings(
        DRIVE_ID="drive",
        SERVICE_ACCOUNT_FILE="service_account.json",
        GITHUB_TOKEN="dummy-token",  # noqa: S106 - valore fittizio per test
        slug="dummy",
    )

    assert settings.DRIVE_ID == "drive"
    assert settings.SERVICE_ACCOUNT_FILE == "service_account.json"
    assert settings.GITHUB_TOKEN == "dummy-token"  # noqa: S105 - valore fittizio per test
    assert settings.slug == "dummy"
