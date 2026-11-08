"""The command line of herdtop."""

import argparse
import os
import shutil
import sys
import time

from herdtop import __version__, changes, render, store, view
from herdtop.readers.claude import ClaudeReader


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="herdtop",
        description="Browse the Claude Code sessions of this machine.",
    )
    parser.add_argument("--version", action="version",
                        version=f"herdtop {__version__}")
    parser.add_argument("--changes", action="store_true",
                        help="print the history of herdtop and exit")
    parser.add_argument("--once", action="store_true",
                        help="print the sessions tab as text, every group "
                             "open, and exit")
    parser.add_argument("--width", type=int,
                        help="the width of --once (default: the terminal, "
                             "else 160)")
    parser.add_argument("--group", choices=view.GROUPS, default="repo",
                        help="group by working directory, by [Tag], or not")
    parser.add_argument("--sort", choices=view.SORTS, default="answer",
                        help="sort by last answer or by title")
    parser.add_argument("--unnamed", action="store_true",
                        help="keep only the sessions with no name set")
    parser.add_argument("--filter", default="",
                        help="keep the sessions whose title or directory "
                             "matches every word")
    return parser.parse_args(argv)


def state_of(args: argparse.Namespace) -> view.ViewState:
    return view.ViewState(group=args.group, sort=args.sort,
                          unnamed=args.unnamed, filter=args.filter)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    if args.changes:
        print(changes.text())
        return 0
    state = state_of(args)
    size = args.width
    if size is None:
        size = (shutil.get_terminal_size((160, 24)).columns
                if sys.stdout.isatty() else 160)
    now = time.time()
    sessions = store.load([ClaudeReader()], now)
    state.all_open = True
    rows = view.rows(sessions.sessions, state)
    try:
        print(render.once(sessions, state, rows, size, now), flush=True)
    except BrokenPipeError:
        # A reader such as `head` left: the rest of the text has no reader.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0
