#!/usr/bin/env python3
"""Refuse an internal name in the tracked files and the commits to push:
their messages, their authors and their committers.

The names are stored as SHA-256 hashes of their lowercase form, so that
the repository does not publish the list it guards against. A host under
the `.corp` suffix is caught by its suffix. To add a name, print its hash
with `--hash <name>` and append it to NAMES.

The report gives a place and never the word: a CI log can be public.

    name_scan.py                  the tracked files, and the messages of
                                  the commits that the upstream lacks
    name_scan.py --log <range>    the messages of <range> instead
    name_scan.py --stdin          the text on stdin only, such as a patch
    name_scan.py --hash <name>    the hash to append to NAMES
"""

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterator

NAMES = frozenset({
    "a64e48dc697c60b671078087af0f34aa798bbd660072f3e198f52f8a0530fa73",
    "e977bf5b27e919c96c38137874225831b4728080c3c585357a587cc3c6e2ce17",
    "ae983afbe1727132530218178f03537df15fb540dc5ada74ace31113683eb7fd",
    "47612b3175fece07f6c3e91992412c5b16ca88a9068cb72fecbcf653eb5ffcd7",
    "385880023dde865910c04d07cd7fd92d4538fe8933634bdbb58bcef5766cf295",
    "f92ad9b4f4730b573cb7169c3880fb599881170b92bed44f5ab84b4f38cec080",
    "a709d04f2354d699c37d074de70b81fee166f89756e94ec72b15579e15df0bb9",
    "0417a0c68f3c483eb729fe694d7643965712a2bad0e1b19d02774ab28b0f38c8",
    "f7070d57bbe5496e29249421e91572f46ac4c2b62953b7ea046fa3707b9e6b2a",
})

_WORD = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_HOST = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.corp\b", re.IGNORECASE)
# A listed name has at most this many parts joined by hyphens.
_MAX_PARTS = 3


def digest(name: str) -> str:
    return hashlib.sha256(name.lower().encode()).hexdigest()


def candidates(text: str) -> Iterator[tuple[int, str]]:
    """Yield each word, and each run of its hyphenated parts, with its
    column: `x-name-plugins` must match a listed `name`."""
    for m in _WORD.finditer(text.lower()):
        parts = re.split(r"[-_]", m.group(0))
        for i in range(len(parts)):
            for j in range(i + 1, min(i + _MAX_PARTS, len(parts)) + 1):
                yield m.start(), "-".join(parts[i:j])


def hits(text: str, names: frozenset[str] | None = None) -> Iterator[int]:
    """Yield the column of each internal name or host in one line."""
    names = NAMES if names is None else names
    for m in _HOST.finditer(text):
        yield m.start()
    for column, word in candidates(text):
        if digest(word) in names:
            yield column


def scan(label: str, text: str,
         names: frozenset[str] | None = None) -> list[str]:
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        found += [f"{label}:{number}:{column + 1}: an internal name"
                  for column in sorted(set(hits(line, names)))]
    return found


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def tracked_files() -> list[str]:
    found = []
    for path in _git("ls-files", "-z").split("\0"):
        if not path:
            continue
        found += scan(f"{path} (file name)", path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"\0" not in data:
            found += scan(path, data.decode("utf-8", errors="replace"))
    return found


def default_range() -> str:
    try:
        _git("rev-parse", "--verify", "-q", "@{upstream}")
    except subprocess.CalledProcessError:
        return "HEAD"
    return "@{upstream}..HEAD"


def messages(revisions: str) -> list[str]:
    found = []
    log = _git("log", "--format=%h%x00%an <%ae> %cn <%ce>%x00%B%x01",
               revisions)
    for entry in log.split("\x01"):
        sha, _, rest = entry.strip("\n").partition("\0")
        identities, _, body = rest.partition("\0")
        if sha:
            found += scan(f"commit {sha} (author and committer)",
                          identities)
            found += scan(f"commit {sha}", body)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", metavar="RANGE",
                        help="the commits whose messages to scan")
    parser.add_argument("--stdin", action="store_true",
                        help="scan the text on stdin only")
    parser.add_argument("--hash", metavar="NAME",
                        help="print the hash of NAME and exit")
    args = parser.parse_args()
    if args.hash:
        print(digest(args.hash))
        return 0
    if args.stdin:
        found = scan("stdin", sys.stdin.read())
    else:
        found = tracked_files() + messages(args.log or default_range())
    for line in found:
        print(line)
    if found:
        print("no-secrets: replace the internal names at the places above",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
