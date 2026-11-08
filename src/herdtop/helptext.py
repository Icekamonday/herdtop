"""The help screen: the keys, then what each column, mark and colour means."""

KEYS = [
    ("j k ↑ ↓", "move row by row"),
    ("PgUp PgDn", "move ten rows"),
    ("g G", "go to the top, to the bottom"),
    ("l →", "open the group"),
    ("h ←", "close the group"),
    ("⏎", "open or close the group"),
    ("z", "open or close every group"),
    ("b", "group by working directory, by [Tag], or flat"),
    ("t", "sort by last answer or by title"),
    ("u", "keep only the sessions with no name set"),
    ("/", "filter on the title and the directory, as you type"),
    ("F", "search the full text of the prompts"),
    ("r", "read the store and the gauges again"),
    ("? F1", "this help; any key closes it"),
    ("Esc", "clear the filter and the search; with neither, quit"),
    ("q", "quit"),
]

COLUMNS = [
    ("age", "the time since the last answer"),
    ("sess", "the sessions of a group, once it holds two"),
    ("ran", "the time worked: the gaps under 15 minutes between two calls"),
    ("cost", "the bill; a dash until herdtop prices the calls"),
    ("req", "the number of calls"),
    ("size", "the transcript and its sidecar on disk"),
    ("ctx", "the context: what the next call sends again"),
    ("cache", "the minutes left on the cache, else cold"),
    ("model", "the model that wrote the most output"),
]

MARKS = [
    ("●", "green name: open in a Claude process"),
    ("○", ("maybe open: the registry is unreadable, and the transcript "
           "changed in the last 2 minutes")),
    ("!", "red name: the same id is in two project directories"),
    ("*", "after the title: no name was set, and the title is generated"),
    ("(n)", "after a group: how many of its sessions are open"),
    ("▲", ("yellow ctx: from 150k, decide (/compact keeps the thread, "
           "/clear drops it)")),
    ("▲▲", "red ctx: from 400k, write a handoff note, then /clear"),
    ("Nm", "green cache: still warm"),
]


def lines() -> list[str]:
    found = ["Keys", ""]
    found += [f"  {key:<10} {text}" for key, text in KEYS]
    found += ["", "Columns (a fold row shows a dash where states do not add up)",
              ""]
    found += [f"  {name:<10} {text}" for name, text in COLUMNS]
    found += ["", "Marks and colours (--no-color keeps the glyphs)", ""]
    found += [f"  {mark:<10} {text}" for mark, text in MARKS]
    return found
