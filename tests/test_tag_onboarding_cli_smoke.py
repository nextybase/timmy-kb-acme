# SPDX-License-Identifier: GPL-3.0-only
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

PY = sys.executable
LOG = logging.getLogger("tests.tag_onboarding_cli_smoke")


def _write_stub_nlp(stub_root: Path) -> None:
    pkg = stub_root / "nlp"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "nlp_keywords.py").write_text(
        """
from typing import Iterable, List, Sequence, Tuple


def extract_text_from_pdf(path: str) -> str:
    return "dummy text"


def spacy_candidates(text: str, lang: str) -> List[str]:
    return ["alpha", "beta"]


def yake_scores(text: str, top_k: int, lang: str) -> List[Tuple[str, float]]:
    return [("alpha", 0.9), ("beta", 0.4)]


def keybert_scores(text: str, candidates: Iterable[str], model_name: str, top_k: int) -> List[Tuple[str, float]]:
    return [("alpha", 0.8), ("beta", 0.3)]


def fuse_and_dedup(text: str, cand_spa: Sequence[str], sc_y, sc_kb) -> List[Tuple[str, float]]:
    return [("alpha", 0.9), ("beta", 0.6)]


def topn_by_folder(items: Sequence[Tuple[str, float]], k: int):
    return list(items)[:k]


def cluster_synonyms(items: Sequence[Tuple[str, float]], model_name: str, sim_thr: float):
    if not items:
        return []
    canonical, _ = items[0]
    members = [phrase for phrase, _ in items]
    synonyms = members[1:]
    return [
        {
            "canonical": canonical,
            "members": members,
            "synonyms": synonyms,
        }
    ]
        """,
        encoding="utf-8",
    )


def _run(cmd, *, env, cwd):
    LOG.info("tests.tag_onboarding_cli_smoke.run", extra={"cmd": " ".join(str(c) for c in cmd)})
    subprocess.check_call(cmd, env=env, cwd=cwd)


@pytest.mark.slow
def test_tag_onboarding_cli_scan_raw_and_nlp_respect_context(tmp_path: Path):
    slug = "dummy"
    client_dir = tmp_path / f"timmy-kb-{slug}"
    raw_dir = client_dir / "raw"
    semantic_dir = client_dir / "semantic"
    logs_dir = client_dir / "logs"
    stub_root = tmp_path / "stubs"

    raw_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)

    pdf_path = raw_dir / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%\n")

    _write_stub_nlp(stub_root)

    env = dict(os.environ)
    env["REPO_ROOT_DIR"] = str(client_dir)
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(stub_root) if not existing_path else f"{stub_root}{os.pathsep}{existing_path}"

    repo_root = Path(__file__).resolve().parents[1]

    _run(
        [
            PY,
            "src/tag_onboarding.py",
            "--slug",
            slug,
            "--scan-raw",
            "--non-interactive",
        ],
        env=env,
        cwd=repo_root,
    )

    _run(
        [
            PY,
            "src/tag_onboarding.py",
            "--slug",
            slug,
            "--nlp",
            "--non-interactive",
            "--lang",
            "it",
            "--only-missing",
            "--topn-doc",
            "1",
            "--topk-folder",
            "1",
            "--cluster-thr",
            "0.5",
            "--model",
            "stub-model",
        ],
        env=env,
        cwd=repo_root,
    )

    assert raw_dir.exists()
    assert semantic_dir.exists()
    assert (semantic_dir / "tags.db").exists()
