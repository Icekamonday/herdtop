# herdtop

herdtop is a full-screen terminal browser of the coding-agent sessions on one machine: it tells which session to touch, what touching it costs, and why.

## Installation

herdtop needs Linux and Python 3.11 or later, and has no other dependency.

```sh
uv tool install git+https://github.com/Icekamonday/herdtop
```

`pipx install git+https://github.com/Icekamonday/herdtop` works too. To run it from a clone without installing it, use `uv run herdtop`.

## Usage

```sh
herdtop              # the sessions tab, in the terminal
herdtop --once       # the same tab printed as text, every group open
herdtop --changes    # the history of herdtop
```

`?` shows the keys and what each column, mark and colour means. `b` groups the sessions by working directory, by the `[Tag]` at the head of their title, or not at all. `/` filters on the title and the directory, and `F` searches the text of the prompts.

`--group`, `--sort`, `--unnamed` and `--filter` set the view at start. `--once` also takes `--width`; its default is the width of the terminal, else 160. `--no-color`, or the `NO_COLOR` variable, shows a glyph in place of each colour.

herdtop reads the store of Claude Code and writes nothing there. These variables move what it reads and writes:

| Variable | Default | What it holds |
|---|---|---|
| `HERDTOP_CLAUDE_HOME` | `$CLAUDE_CONFIG_DIR`, else `~/.claude` | the transcripts and the process registry |
| `HERDTOP_PAYLOAD_DIR` | `$XDG_STATE_HOME/claude-tmux`, else `~/.local/state/claude-tmux` | the payloads that the status line saves |
| `HERDTOP_CACHE_DIR` | `$XDG_CACHE_HOME/herdtop`, else `~/.cache/herdtop` | the counts of each transcript, so a run reads only what changed |

### The status line payload

Claude Code passes a JSON payload to its status line command. It holds the cache of the session and the rate-limit windows of the account. A status line command can save it as `<session id>.raw.json` in the payload directory. herdtop then shows the gauges in its header and reads the cache from it. Without it, herdtop takes the cache from the transcript alone. This command saves the payload; it needs `jq`:

```sh
#!/bin/sh
dir="${HERDTOP_PAYLOAD_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/claude-tmux}"
payload=$(cat)
id=$(printf '%s' "$payload" | jq -r '.session_id // empty')
if [ -n "$id" ]; then
    mkdir -p "$dir"
    printf '%s' "$payload" > "$dir/$id.raw.json.tmp" &&
        mv "$dir/$id.raw.json.tmp" "$dir/$id.raw.json"
fi
printf '%s\n' "$(printf '%s' "$payload" | jq -r '.model.display_name // empty')"
```

### In a sandbox

From a sandbox or a container, the pids of the process registry are not visible. herdtop then says `registry unreadable` in its header, and marks with `○` each transcript that changed in the last two minutes, as it may be open.

## Status

Version 0.1.0 lists the Claude Code sessions with the figures that need no price. herdtop rewrites cctop, an earlier browser of Claude Code sessions, with one reader per agent kind: Claude Code and Codex first. [docs/functional-description.md](docs/functional-description.md) describes cctop, which is the behaviour that herdtop starts from. herdtop runs in any terminal, with or without [Herdr](https://github.com/herdrdev/herdr).

The checks that the CI runs are `ruff check .`, `pytest` and `scripts/no-secrets.sh`.

herdtop is under the MIT licence: see [LICENSE](LICENSE).
