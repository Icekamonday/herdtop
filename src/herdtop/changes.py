"""The history of herdtop, printed by `herdtop --changes`."""

CHANGES: list[tuple[str, list[str]]] = [
    ("0.1.0", [
        "The package, its checks and its CI.",
    ]),
]


def text() -> str:
    lines = []
    for version, items in CHANGES:
        lines.append(version)
        lines += [f"  - {item}" for item in items]
    return "\n".join(lines)
