"""The history of herdtop, printed by `herdtop --changes`."""

CHANGES: list[tuple[str, list[str]]] = [
    ("0.1.0", [
        ("The sessions tab: the Claude Code store of this machine, flat or "
         "grouped by working directory or by [Tag], with its folds."),
        ("The figures that need no price: ran, req, size, ctx, cache and "
         "model. The cost columns show a dash."),
        ("The live state from the process registry and /proc, and the cache "
         "and the gauges from the payload of the status line."),
        ("The keys of the list, the filter, the prompt search, the help, "
         "--no-color, and --once to print the tab as text."),
    ]),
]


def text() -> str:
    lines = []
    for version, items in CHANGES:
        lines.append(version)
        lines += [f"  - {item}" for item in items]
    return "\n".join(lines)
