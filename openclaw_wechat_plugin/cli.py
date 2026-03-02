from __future__ import annotations

import argparse
import sys

from .app import run
from .connector import run_connector
from .openclaw_installer import format_install_result, install_openclaw_extension


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openclaw-wechat-plugin",
        description="Standalone WeChat adapter plugin for OpenClaw",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start the WeChat plugin service")
    subparsers.add_parser(
        "connector",
        help="Run outbound cloud connector (edge OpenClaw -> cloud WS)",
    )

    install_parser = subparsers.add_parser(
        "install-openclaw",
        help="Install bundled OpenClaw extension and enable the wechat plugin",
    )
    install_parser.add_argument(
        "--openclaw-bin",
        default="openclaw",
        help="Path or command name for OpenClaw CLI (default: openclaw)",
    )
    install_parser.add_argument(
        "--no-enable",
        action="store_true",
        help="Only install extension package, do not run `plugins enable wechat`",
    )
    install_parser.add_argument(
        "--link",
        action="store_true",
        help="Install with OpenClaw link mode (`plugins install --link`)",
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned OpenClaw commands without executing them",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command in (None, "serve"):
        run()
        return

    if args.command == "connector":
        run_connector()
        return

    if args.command == "install-openclaw":
        try:
            result = install_openclaw_extension(
                openclaw_bin=args.openclaw_bin,
                enable=not args.no_enable,
                link=args.link,
                dry_run=args.dry_run,
            )
        except RuntimeError as exc:
            print(f"[openclaw-wechat-plugin] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        print(format_install_result(result))
        return


if __name__ == "__main__":
    main()
