#!/usr/bin/env python3
import argparse
import subprocess
import sys


BINARIES = {
    "fast": 'unit and not slow',
    "arch": "arch or contract",
    "full": None,
}


def _build_pytest_command(binary: str, extra_args: list[str]) -> list[str]:
    marker_expr = BINARIES[binary]
    cmd = [sys.executable, "-m", "pytest", "-q"]
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

    cmd = _build_pytest_command(args.binary, extra_args)
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
