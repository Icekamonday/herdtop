"""The command line of herdtop."""

import argparse

from herdtop import __version__, changes


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="herdtop",
        description="Browse the Claude Code sessions of this machine.",
    )
    parser.add_argument("--version", action="version",
                        version=f"herdtop {__version__}")
    parser.add_argument("--changes", action="store_true",
                        help="print the history of herdtop and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    if args.changes:
        print(changes.text())
        return 0
    return 0
