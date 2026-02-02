#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


BINARIES = {
    "fast": 'unit and not slow',
    "arch": "arch or contract",
    "full": None,
}

TEST_TEMP_DIR = Path("test-temp")
CLIENTS_TEMP_DIR = TEST_TEMP_DIR / "clients_db"
CLIENTS_DB_TEST_DIR = CLIENTS_TEMP_DIR / ".pytest_clients_db"
OUTPUT_TEMP_DIR = TEST_TEMP_DIR / "output"
PYTEST_TEMP_DIR = TEST_TEMP_DIR / "pytest"


def _safe_remove(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except (OSError, PermissionError):
        return


def _prepare_test_temp() -> None:
    if TEST_TEMP_DIR.exists():
        for child in TEST_TEMP_DIR.iterdir():
            _safe_remove(child)
    else:
        TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    CLIENTS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    CLIENTS_DB_TEST_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PYTEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _pytest_executable() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return sys.executable


def _build_pytest_command(binary: str, extra_args: list[str]) -> list[str]:
    marker_expr = BINARIES[binary]
    cmd = [_pytest_executable(), "-m", "pytest", "-q"]
    if marker_expr:
        cmd.extend(["-m", marker_expr])
    cmd.extend(extra_args)
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-platform test runner for FAST/ARCH/FULL binaries."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show binary to marker mappings and exit.",
    )
    parser.add_argument(
        "binary",
        nargs="?",
        choices=BINARIES.keys(),
        help="Test binary to run: fast, arch, or full.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra pytest args after -- (e.g. -- -k expr).",
    )
    args = parser.parse_args()

    if args.list:
        for name, expr in BINARIES.items():
            marker = expr if expr else "(no marker filter)"
            print(f"{name}: {marker}")
        return 0
    if not args.binary:
        parser.error("binary is required unless --list is used")

    extra_args = args.pytest_args
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    _prepare_test_temp()
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    subprocess_env = os.environ.copy()
    python_path = subprocess_env.get("PYTHONPATH")
    if python_path:
        subprocess_env["PYTHONPATH"] = f"{python_path}{os.pathsep}{src_path}"
    else:
        subprocess_env["PYTHONPATH"] = str(src_path)
    if "PYTHONPATH" in os.environ and os.environ["PYTHONPATH"]:
        subprocess_env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    subprocess_env["CLIENTS_DB_DIR"] = str(CLIENTS_DB_TEST_DIR.resolve())
    subprocess_env["CLIENTS_DB_FILE"] = "clients.yaml"
    subprocess_env["WORKSPACE_ROOT_DIR"] = str(OUTPUT_TEMP_DIR.resolve())
    subprocess_env["TIMMY_KB_DUMMY_OUTPUT_ROOT"] = str(TEST_TEMP_DIR.resolve())
    subprocess_env.setdefault("PYTEST_TMPDIR", str(PYTEST_TEMP_DIR.resolve()))

    cmd = _build_pytest_command(args.binary, extra_args)
    if args.binary in {"fast", "full"}:
        subprocess_env["TIMMY_ALLOW_BOOTSTRAP"] = "1"
        subprocess_env["TIMMY_BETA_STRICT"] = "0"
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, env=subprocess_env)


if __name__ == "__main__":
    raise SystemExit(main())
