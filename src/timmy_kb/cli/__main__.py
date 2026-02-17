# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse

from pipeline.env_attestation import ensure_env_attestation, write_env_attestation
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

    attest_parser = subparsers.add_parser(
        "env-attest",
        help="Genera/verifica attestato ambiente runtime strict.",
    )
    attest_parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verifica solo l'attestato esistente senza rigenerarlo.",
    )
    attest_parser.add_argument(
        "--installed-by",
        default="",
        help="Annotazione opzionale (es. utente o host) dentro l'attestato.",
    )
    return parser


def _run_ledger_status(args: argparse.Namespace) -> int:
    ensure_strict_runtime(context="cli.__main__.ledger_status", require_workspace_root=True)
    return int(ledger_status.run(slug=args.slug, json_output=bool(args.json)))


def _run_env_attest(args: argparse.Namespace) -> int:
    ensure_strict_runtime(context="cli.__main__.env_attest", require_workspace_root=False)
    if bool(args.verify_only):
        ensure_env_attestation()
        return 0
    installed_by = str(args.installed_by).strip() or None
    write_env_attestation(installed_by=installed_by)
    ensure_env_attestation()
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "ledger-status":
        return _run_ledger_status(args)
    if args.command == "env-attest":
        return _run_env_attest(args)
    parser.error(f"Comando non supportato: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
