import sys
import uuid
import subprocess
from pathlib import Path
import pytest

PY = sys.executable


def run(cmd, env=None):
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, env=env)


@pytest.mark.slow
def test_smoke_dummy_e2e(tmp_path: Path, monkeypatch):
    # Slug unico per evitare collisioni fra run
    slug = "dummy-" + uuid.uuid4().hex[:8]
    out = Path("output") / f"timmy-kb-{slug}"

    # 1) pre: solo locale (dry-run evita Drive)
    run(
        [
            PY,
            "src/pre_onboarding.py",
            "--slug",
            slug,
            "--name",
            "Cliente Dummy",
            "--non-interactive",
            "--dry-run",
        ]
    )

    # 2) genera sandbox dummy (PDF + tags_raw.csv)
    run([PY, "src/tools/gen_dummy_kb.py", "--slug", slug])

    # 3) tag: usa LOCAL perché i PDF sono già in RAW (è più rapido e stabile in CI)
    run(
        [
            PY,
            "src/tag_onboarding.py",
            "--slug",
            slug,
            "--source",
            "local",
            "--non-interactive",
            "--proceed",
        ]
    )

    # 4) semantic: senza preview
    run([PY, "src/semantic_onboarding.py", "--slug", slug, "--no-preview", "--non-interactive"])

    # Assert principali
    assert (out / "raw").exists()
    assert (out / "semantic" / "tags.db").exists()
    assert (out / "book" / "README.md").exists()
    assert (out / "book" / "SUMMARY.md").exists()

    # NB: non testiamo il push in CI (richiede GITHUB_TOKEN). Se vuoi abilitarlo:
    # os.environ["GITHUB_TOKEN"] = "<token>"
    # run([PY, "src/onboarding_full.py", "--slug", slug, "--non-interactive"])
