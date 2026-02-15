# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse

from pipeline.runtime_guard import ensure_strict_runtime
from timmy_kb.cli import ledger_status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Timmy KB CLI dispatcher")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ledger_parser = subparsers.add_parser(
        "ledger-status",
        help="Read-only status from output/<slug>/config/ledger.db",
    )
    ledger_parser.add_argument("--slug", required=True, help="Slug cliente")
    ledger_parser.add_argument("--json", action="store_true", help="Output JSON deterministico")
    return parser


def _run_ledger_status(args: argparse.Namespace) -> int:
    ensure_strict_runtime(context="cli.__main__.ledger_status", require_workspace_root=True)
    return int(ledger_status.run(slug=args.slug, json_output=bool(args.json)))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "ledger-status":
        return _run_ledger_status(args)
    parser.error(f"Comando non supportato: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
