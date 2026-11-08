# Functional description of cctop

This document describes cctop 1.6, the terminal browser of Claude Code sessions that herdtop rewrites. With it, herdtop can be written without the cctop code.

It describes what the tool shows, what it does and what it reads. Paths and settings carry herdtop's names. The section "Codex" lists what a second reader must give.

## Purpose

cctop answers three questions about the sessions of one machine: which session to touch, what touching it costs, and why. It reads only what the agent records: the transcripts, the process registry and the payload of the status line.

Every figure on a row carries its verdict. The help and the `$` screen explain the cost model instead of giving a total.

Two rules hold on every screen:

- A colour asks for a decision. A figure that is only true stays plain.
- Each meaning also has a glyph or a word, so `--no-color` loses nothing.

## Words

- The store: every transcript under `~/.claude/projects/`.
- The project directory: one directory of the store, named after a working directory.
- A call: one request to the model.
- The context: what the last call sent, which the next call sends again.
- A restart: a call that writes more to the cache than it reads back. It happens when the cache has expired.
- A handoff note: a short text that carries the state of a session into a new one.

## Data that it reads

### Transcripts

Claude Code stores a session as `~/.claude/projects/<slug>/<id>.jsonl`. The slug is the absolute working directory with each `/` and `.` replaced by `-`. The tool finds the sessions with the glob `projects/*/*.jsonl`, as Claude Code does.

From each transcript the tool reads:

- The working directory: the first `cwd` field of the file. Two working directories can give the same slug, so the tool never derives the directory from the slug.
- The title. A `custom-title` record (a rename) wins over an `ai-title` record (the generated title), and the last record of each kind wins. The tool reads the last 64 KiB first. If the tail has no `custom-title` record and the file contains the bytes `"custom-title"`, it reads the whole file. Claude Code writes the generated title again through the file, so an early rename can sit far from the tail.
- The prompts and the answers. A prompt is a `user` record that is not `isMeta` and that holds a text block. The tool removes what the client adds around the typing: IDE selection blocks, paste markers, command and hook records, system reminders, interruption notes and continuation summaries. The answer of an exchange is the last assistant text before the next prompt.
- The usage of each call, from `message.usage`. A call counts once, on the pair (`requestId`, `message.id`), because a resume or a compaction writes the same records again. The thinking tokens come from `output_tokens_details.thinking_tokens`. `cache_creation_input_tokens` is the total of the cache writes, and `cache_creation` splits it by TTL. An interrupted turn can carry a split with a total of zero, so the total decides.
- A `continued-in` record at the end of the file, which names the session that went on from this one. See "Parked conversations".

A session can own a sidecar directory `<id>/` beside its transcript. It holds:

- `tool-results/`: tool output that the session moved out of its context.
- `subagents/agent-<n>.jsonl`, with `agent-<n>.meta.json`: an agent that the session started. The meta file gives its `description` and its `agentType`.
- `subagents/workflows/<run>/agent-<n>.jsonl`: an agent of a workflow run. The run directory also holds `journal.jsonl`, which is not an agent.
- `workflows/scripts/<name>-<run>.js`: the script of a workflow run. Its file name gives the name of the run.

Two more directories hold parts of a session, keyed by its id: `~/.claude/file-history/<id>` and `~/.claude/session-env/<id>`.

### The process registry

Claude Code writes `~/.claude/sessions/<pid>.json` for each running session, the VS Code extension included. The tool reads `sessionId`, `pid`, `procStart`, `pidDomain`, `cwd`, `name`, `entrypoint`, `kind`, `status` and `parkedJobId`. The `kind` of a background session is `bg`, and that of the others is `interactive`.

A registry file outlives its process. An entry is live only if all of these hold:

- If the entry has a `pidDomain`, it names the pid namespace of the tool. Its form is `linux:<machine id>:pid:[<inode>]`: the content of `/etc/machine-id`, then the target of the link `/proc/self/ns/pid`.
- `/proc/<pid>` exists.
- The start time in `/proc/<pid>/stat` equals `procStart`, so a reused pid does not pass for the session. It is field 22 of that file, in clock ticks, and `procStart` holds it as a string.

From a sandbox or a container, the pids of the registry are not visible. The tool then treats the registry as unreadable. An entry written from the namespace of the tool proves that the registry is readable, and so does a pid that is seen alive. If the registry is unreadable, a transcript changed less than two minutes ago counts as possibly open.

For a live session the tool also finds the program that shows it. If the process reads a `/dev/pts` or `/dev/tty`, the tool walks up its parent processes, past shells, `sudo`, `env`, `login` and `claude`. The first other program is the one that draws the terminal, such as Herdr, tmux or a terminal emulator.

### The status line payload

Claude Code passes a JSON payload on standard input to the status line command. A status line command saves it as `<id>.raw.json` in a state directory, one file per session. The default directory is `$XDG_STATE_HOME/claude-tmux`, else `~/.local/state/claude-tmux`: the status line hook of Icekamonday/herdr saves the payload there. `HERDTOP_PAYLOAD_DIR` moves it.

The tool reads two parts of it:

- `rate_limits.five_hour` and `rate_limits.seven_day`, each with `used_percentage` and `resets_at`. They belong to the account, so the newest file answers for every session. If `resets_at` has passed, the tool does not show that window.
- `prompt_cache`, with `ttl` (`5m` or `1h`), `expires_at` and `recache_tokens_if_cold`. It belongs to the session. If `expires_at` is older than the last call of the transcript, the tool keeps only the TTL.

`resets_at` and `expires_at` are Unix times in seconds, and `used_percentage` is a whole number.

If the status line saves nothing, the tool shows no gauges, and the cache state comes from the transcript alone.

### The account

The tool reads `oauthAccount` in `~/.claude.json`: `userRateLimitTier`, `organizationRateLimitTier` and `hasExtraUsageEnabled`. The `$` screen names the plan, because a figure derived from a gauge holds only under the plan that it was measured under.

### Herdr

If the `herdr` command answers, the tool reads three lists, each as JSON under `result`:

- `herdr agent list`: for each agent, `agent_session.value` (the session id), `workspace_id`, `tab_id` and `agent_status`.
- `herdr workspace list`: the `label` of each workspace.
- `herdr tab list`: the `number` of each tab.

If Herdr does not answer, the tool works without it. It reads Herdr once per run, at the first look at tab 2 or at the first open. `r` does not read Herdr again.

### Its own files

- The tally cache. It holds the counts of each transcript, keyed on the size and the modification time of the file. A transcript only grows, so a run reads again only the transcripts that changed. If the shape of an entry changes, the cache is rebuilt.
- The archive directory, outside `~/.claude`, by default `~/.local/share/herdtop/archive`. The retention sweep of Claude Code deletes old transcripts, sidecars and file history under `~/.claude`, and an archive must not be swept.
- A log of each hand-over to `claude`: the date, the id, `attach` or `resume`, the working directory and the title. After the hand-over no screen is left, so the log is the only record of the session that the tool chose.
- A backup of the transcript before each move, in `~/.claude/backups/`.

Environment variables move the home of the agent, the archive, the state directory and the tally cache. The tests use them to build a store of their own.

## Counting

The tool stores counts, never dollars: rates change, and a count stays true. For each transcript it keeps:

- Per model: the calls, the input, the output, the thinking tokens, the cache writes at 5 minutes and at 1 hour, and the cache reads.
- The restarts. A warm call writes what the turn added and reads the rest back. Only a call after the cache expired writes more than it reads. This rule has no threshold, so it holds for a small session and for a large one.
- The last five calls, to price the next one.
- The time worked: the sum of the gaps between two calls that are shorter than 15 minutes.
- The time of the last call.
- The calls of the last eight days, in 15-minute buckets, per model, to count what a rate-limit window spent.

A call with no tokens at all, such as an interrupted turn, does not count for these figures.

The tool counts the agents of a session the same way, from their own transcripts, apart from the conversation.

## The cost model

### Prices

A table gives the input and output rates of each model, per million tokens, with the date that each row was read. A cache write costs 1.25 times the input rate at 5 minutes and 2 times at 1 hour. A cache read costs 0.1 times the input rate. If a model reads its cache at another multiplier, the table holds that multiplier beside the rate. A model that is not in the table has no price.

Every dollar figure is an estimate. The screens give the dates of the rates that they use.

The price of one call is:

    context      x read price
    + new content x write price
    + output      x output price

The context is sent again on every call. The cache makes each token cheaper, but the call still pays for every token.

### Figures of a session

- `ctx`, the context: the input, the cache writes and the cache reads of the last call. If the payload is fresh, its `recache_tokens_if_cold` replaces it.
- `cost`, the bill: the cost of the conversation plus the cost of its agents.
- The split: what the conversation paid to read, to restart, to write new content and to answer, as shares of its cost.
- `wake`, the price of a restart: the context written once to the cache, at the TTL of the session.
- `$/call`, the price of one more call: the average of the last five calls, restarts left out.
- The reread share: the part of `$/call` that reads the context back.
- The handoff price: a new session that opens on a 30k handoff note. It pays one write of 30k, then each call costs `$/call`, with a reread of 30k in place of the reread of the context.
- `cold%`: the share of the conversation's cost that went on restarts.
- `agt%`: the share of the bill that the agents spent.
- `ran`: the time worked.
- `age`: the time since the last answer. A rename or a hook also writes the file, so the modification time stands in only for a session that never got an answer.

The agents count in the bill, in `agt%` and in the totals only. An agent ends with its cache, so touching the session never pays for it again. For this reason `ctx`, `wake`, `$/call`, `cold%` and the call count stay the conversation's.

### The cache clock

The TTL comes from the payload. Without a payload, it comes from the last cache write of the transcript: 1 hour if that write was at 1 hour, else 5 minutes. Without either, it is 5 minutes, so that an unknown cache reads as cold rather than warm.

The cache ends one TTL after the last call. If the payload gives a later `expires_at`, that time wins.

### The bands

- Under 150k tokens: keep going. The price of a call is flat, and quality holds.
- From 150k to 400k: decide. `/compact` keeps the thread, `/clear` drops it.
- Over 400k: a restart writes back more than the session has produced. Do not restart it cold: write the handoff note in one turn, then `/clear`.

If a session over 400k is still warm, it keeps the colour of its band. It takes the verdict of the middle band, because there is nothing to restart yet.

### The rate-limit windows

The 5-hour and 7-day windows are fixed. `resets_at` gives the end, and the start is 5 hours or 7 days earlier. What a window spent is the sum of the buckets of every session inside it, agents included, at today's rates.

A point of a gauge costs the dollars spent divided by the used percentage. A price as a share of a window is that price divided by the cost of a point. The size of a window is never published, and this ratio does not need it.

The gauge is a whole percent. Under 10%, its rounding is too large to divide by, so the tool gives no share and says why.

## The main screen

Line 1 is the header and line 2 is the tab bar. The list follows, then the session pane and the footer.

### Header

From left to right:

- `cctop` and its version.
- On tab 1: the shown sessions over all sessions, and the size of the store in MiB. On tab 2: the running sessions, and the number of Herdr workspaces that show them. On tab 3: the archived sessions, and the MiB that they hold.
- The filter, the full-text search and the number of ticked sessions, when they are set.
- The gauges, 7d first: the used percentage, then the dollars that the window spent.
- `~$` and the bill of the shown sessions.

On the right: `group:` and `sort:` with their modes, then the clock. `unnamed` comes first when that filter is on. Under 60 columns, the right side keeps only the clock.

### Tab bar

`1.sessions (n)  2.live (n)  3.archive (n)`. Under 70 columns: `1.n  2.n  3.n`.

### Tab 1, sessions

All the sessions, the newest answer first. `b` cycles the grouping:

- by `repo`, the working directory;
- by `[Tag]`, the text in square brackets or parentheses at the start of the title, up to 30 characters, with `(untagged)` for the rest;
- flat.

In a grouped view, a group is a fold row. In the flat view without the cost view, the columns are `age`, the title, `repo`, then the figures.

### Tab 2, live

The sessions that a live process holds. The front end of a parked conversation is left out, because the job stands for it. The sessions that Herdr calls working come first, then the others by last answer.

This tab always shows the cost columns. It holds a dozen rows, so the figures cost nothing to compute.

It adds two columns:

- `owner`: who shows the session. If a Herdr tab shows it: `herdr · <workspace label>`. Else, for a background session: `background · claude attach`. Else, for a client that registered under its own name: that name, such as `vscode`. Else, for a CLI with a terminal: the terminal program. Else `nowhere`, in red: the session runs, and nothing shows it.
- `state`: the status from Herdr if a tab shows the session, else the status from the registry, where `busy` and `shell` read as `working`. `working` is green. `done` is yellow: the session finished and nobody looked at it since, which only Herdr knows.

### Tab 3, archive

The archived sessions, grouped by the working directory they came from, with folds. The columns are the archive date, the title and the directory that the session returns to. `x` restores the session under the cursor.

### Figure columns

In reading order, with the rank that decides which columns stay when the terminal narrows. A lower rank stays longer.

| Column | Width | Rank | View | Meaning |
|---|---:|---:|---|---|
| `sess` | 5 | 3 | both | the sessions of a group, once it holds two |
| `ran` | 5 | 5 | both | the time worked |
| `cost` | 11 | 2 | both | the bill, agents included |
| `agt%` | 5 | 6 | cost | the agents' share of the bill |
| `req` | 5 | 6 | both | the number of calls |
| `size` | 8 | 7 | both | the transcript and its sidecar on disk |
| `ctx` | 6 | 1 | both | the context |
| `cold%` | 5 | 4 | cost | the restarts' share of the conversation's cost |
| `cache` | 5 | 2 | both | the minutes left on the cache, else `cold` |
| `7d` | 5 | 1 | cost | `wake` as a share of the 7-day window |
| `wake` | 6 | 1 | cost | the price of a restart |
| `$/call` | 7 | 5 | cost | the price of one more call |
| `model` | 11 | 6 | both | the model that wrote the most output |

The rules of the columns:

- The columns form three blocks that never mix. First what only a group has (`sess`). Then what both kinds of row sum (`ran`, `cost`, `agt%`, `req`, `size`). Then what belongs to one session (the rest).
- A fold row shows a dash in the third block, because states do not add up. A session row leaves the first block empty, so that the gap reads as an indent.
- `sess` appears only in a grouped view.
- `c` adds the cost view: `agt%`, `cold%`, `7d`, `wake` and `$/call`. Tab 2 always has it.
- `7d` appears only when a gauge can divide.
- The room for the figures is the width, minus the fixed part and the title. Tab 2 also keeps room for `owner` and `state`. The flat view without the cost view also keeps room for `repo`.
- The tool takes the figures by rank while they fit. If one does not fit, the tool skips it, and a narrower column of a lower rank can still take the room.
- A title takes at most 58 columns, so that the figures sit next to the name.
- Each cell is cut to its width, so that the grid never shifts.

### Marks and colours

The marks:

- A green name, or `●`: the session is open in a Claude process, so it cannot move.
- A red name, or `!`: the same id is in two project directories. The session was moved while it was open.
- `*` after the title: no name was set, and the title is generated.
- `✓`: the session is ticked.
- `(n)` after a group: how many of its sessions are open.

What a row is (open, twin, ticked) colours its name only. In the figures, only these cells take a colour:

- `ctx` and `wake`: yellow from 150k, red from 400k.
- `cache`: green while the cache is warm.
- `cold%`: red over 40%, only on a row under 150k, where the context gives no colour.
- `cost`: yellow over $100.
- `$/call`: yellow over $0.50.

### The session pane

The pane follows the cursor. If the terminal has 120 columns or more, it sits beside the list. Else, if the terminal has 19 lines or more, it sits below the list. `p` hides or shows it.

For a session, in this order:

1. The title, then the short id, the working directory and the age. Then, when they apply: "no name set", "open now in <client> · pid <n>", and a warning for an id in two project directories.
2. What touching it costs: the cost of the conversation and its split; the cost of the agents on a line of its own, as already spent; the context, the cache state (warm with the minutes left, or cold since when) and the restarts paid; the restart price, as a share of the 7-day window when a gauge allows, and `$/call`; the handoff price, once and per call; the verdict, in the colour of its band.
3. The first prompt, the last five exchanges with their dates and their count, and the last answer.
4. What it is made of: the output, the cache reads with the hit rate, the calls, the model, the size, and the tool results, agents and workflow runs of its sidecar.

For a group: the directory or the tag, the number of sessions, the size, the sessions with no name set, the running sessions, and the sessions newest first.

For an archived session: the title, the id, the archive date, the size, the directory it restores to, and the parts that the archive holds.

### Footer

The keys of the current screen, and the last message: a count after a reload, the result of an action, or a refusal.

## The other screens

### Exchanges (`⏎`)

The session as the list of its exchanges. The header gives the title, the id, the working directory, the date, the size and the number of lines. Each row gives the date and the prompt of an exchange.

- `/` keeps the exchanges whose prompt or answer contains the text.
- `tab` opens the exchange under the cursor: the prompt, then the answer, wrapped. `j` and `k` scroll. `/` finds a text in it, highlighted, and `n` goes to the next hit.
- `y` copies the answer, and `Y` copies the prompt.
- `Esc` clears the search, then leaves.

### The `$` screen

The cost model, taught on the session under the cursor. It reads one transcript, so it does not need the cost view. Each section names the list column that shows the same figure.

1. The title; the context, the model, the calls and the bill; the verdict.
2. The model: the formula of a call, and the dates of the rates.
3. Where this session went: a bar to scale in four parts (read, restarts, new writes, output), each with its own glyph so that the bar survives `--no-color`. Then the shares, and one sentence that reads the largest part.
4. What its agents cost, if it started some: their number, their cost and share of the bill, their split, then the five dearest, a workflow run on one line. An agent's reads never enter this context, so the agents move none of the prices below.
5. What one more call costs: `$/call`, and the part of it that rereads the context.
6. What an expired cache costs: the restart price, with "in Xmn, if you leave it" or "due now, cold for Y"; the price of a new session from a handoff note, once and per call; the restarts already paid and their share. Then the rule: letting a session sleep costs nothing, and waking it is what costs. A large session that wakes now and then is the worst case, because it pays the full price at every restart.
7. What is left of the allowance, when the payload gives gauges: the plan; for each window, the used percentage, the dollars spent and the time to the reset; what a restart takes from each window, or why the gauge is too low to divide.
8. The three bands as a ladder, with a marker on the band of this session.
9. At 150k or more, what stops it happening again: ask for a handoff note, copy it, `/clear`, and paste it, so that the next session starts near 30k. The note gives the goal, the current state, the decisions and why, the next step and pointers (commit, ticket, files), in one screen, with no file contents. If the work spans days or people, the note goes in a file. Under 150k, this section is one sentence: there is nothing to do.

### Help (`?` or F1)

All the keys, grouped by screen, with the meaning of each column, mark and colour. Any key closes it.

### Rename (`R`)

A popup with a text field that starts on the current title. The arrows, Home and End move in it. Ctrl-U clears it. Ctrl-W deletes a word.

If sessions are ticked, the field is a tag instead, which goes in front of each title. A title that already starts with the tag stays as it is.

A rename appends one complete `custom-title` record to the transcript, in one write. Nothing is erased, and the last record wins.

### Move (`m`)

A picker of destinations:

- Type to filter the known working directories. A text that starts with `~` or `/` completes any directory on disk.
- ↑ and ↓ choose. Space turns the rewrite of the `cwd` fields on or off.
- `⏎` shows a confirmation that spells out the change, with the other working directories that already share the target project directory.
- `y` or `⏎` applies it. `n` or `Esc` goes back.

A move refuses in these cases: the target is the same project directory; the target already holds a transcript with that id; the target is not an existing directory; the session is open. It copies the transcript to a backup first. Then it moves the transcript and its sidecar. The rewrite changes only the `cwd` fields at the top level of each record.

### Archive and restore (`x`)

A confirmation lists the sessions (three at most) and the archive directory. It says that Claude Code and VS Code no longer see them, and that tab 3 lists them, where `x` brings one back.

The archive moves the transcript, the sidecar, the file history and the session environment into `<archive>/<id>/`, with a manifest: the id, the project directory, the working directory, the title, the size, the times and the parts. It refuses a session that is already archived, and a session that is open.

The restore puts each part back where the manifest says. It refuses if a file already holds one of those paths.

## Keys

### List

| Key | Action |
|---|---|
| `j` `k` `↑` `↓` | move row by row |
| `PgUp` `PgDn` | move ten rows |
| `g` `G` | go to the top, to the bottom |
| `l` `→` | open the group |
| `h` `←` | close the group |
| `⏎` | on a group, open or close it; on a session, its exchanges |
| `z` | open or close every group |
| `b` | group by `repo`, by `[Tag]`, or flat (tab 1) |
| `1` `2` `3` | sessions, live, archive |
| `u` | keep only the sessions with no name set |
| `c` | add the cost view |
| `t` | sort by last answer, by title, or by cost |
| `p` | hide or show the session pane |
| `r` | read the store and the gauges again |
| `?` `F1` | help |
| `/` | filter on the title and the working directory, as you type |
| `F` | search the full text of the prompts |
| `Esc` | clear the search; with no search, quit |
| `q` | quit |
| space | tick the session and move down |
| `A` | tick every shown session, or clear the ticks |
| `$` | the `$` screen |
| `R` | rename; on ticked sessions, put a tag in front |
| `m` | move to another working directory |
| `o` | open the session |
| `y` | copy the command that resumes it |
| `x` | archive; on tab 3, restore |

If sessions are ticked, `R`, `m` and `x` act on them, else on the session under the cursor. These keys need a session: on a group row, the tool asks to open the group first.

### Filter and search

- `/` takes words separated by spaces, and each word must match the title or the working directory. The tool tries a substring match first. If no session matches, it tries a subsequence match, so `cfg` finds `config`. The subsequence comes second because it matches too much.
- A filter opens every group.
- `F` reads every transcript and keeps the sessions whose prompts contain every word, without case. Agent prompts that the transcript holds count too. The answers do not count, because an answer repeats the words of its question. A byte test skips a file that cannot match before the tool parses it.

### Mouse

The tool asks for no mouse reports, so the terminal keeps its own selection, and any text on the screen can be copied. A click does not move the cursor.

## Actions

### Open (`o`)

The tool takes the shortest way that works:

1. If the tool runs inside Herdr (`HERDR_ENV` is set) and a Herdr tab shows the session, the tool focuses the workspace, then the tab, and quits. For a parked job, the tab of its front end counts.
2. If an interactive session runs somewhere else, the tool refuses and says where it runs: the client, the pid and the name. A second client would put two writers on one transcript.
3. If the tool runs inside Herdr, it asks Herdr to open the session in a tab of its working directory (see "Herdr"), then quits.
4. Else the tool quits and replaces itself with the agent, in the working directory of the session: `claude attach <id>` for a background session, `claude --resume <id>` for any other. One pane runs one program, and nothing stays behind the session.

If `claude` is not on the PATH, the tool prints the command instead.

### Copy (`y`)

The tool copies `cd <working directory> && claude --resume <id>`, or `claude attach <id>` for a background session, to the clipboard through `wl-copy` or `xclip`. The directory goes with the command, because the clipboard lands in whatever shell is open. If no clipboard tool works, the message line shows the command.

### Other actions

Rename, move, archive and restore are described with their screens above. All of them write in `~/.claude`, so they fail inside a sandbox that protects it.

## Refresh

- The screen redraws every second, for the clock, the cache countdowns and the size of the terminal. The tool reads the size of the terminal at each tick: a Herdr pane grows after the program starts, and curses does not see it before a key.
- The tool reads the store at start, and the counts before the first frame. The first run reads every transcript; later runs read the tally cache.
- `r` reads the store again, with the gauges and the dollars of the windows.
- The gauges and the account are read once until `r`.
- Herdr is read once per run.
- A session that disappears under the list (cleared, archived from another terminal, or swept) reads as empty until the next reload. No row can make the tool fail.

## Parked conversations

Claude Code can park a conversation into a background job under a new id. The transcript of the job starts on a copy of the old transcript. The old transcript ends on a `continued-in` record, whose `continuedInSessionId` names the job.

The registry then holds two entries. The front end is interactive, under the old id, with `parkedJobId` set to the first eight characters of the job id. The job is a background session under its own id.

The tool:

- lists the job once and hides the old transcript, but adds the size of the old transcript to the job. Else the list would show the conversation twice and bill it twice;
- follows a chain of parks to the last job;
- archives and restores the old transcript with the job;
- finds the Herdr tab of the job through the id of the front end, because Herdr follows the process in its pane.

If Claude Code ever parks with a summary instead of a copy, the old transcript holds calls that the job does not hold. Hiding it would then hide that spending. The tool must check again that the job holds the record ids of the old transcript.

## Herdr

### Opening the tool in Herdr

cctop opens from a Herdr key of `type = "pane"`, in `[[keys.command]]`. Herdr opens a temporary zoomed pane, which closes when the command exits. The pane gets `HERDR_ENV`, which the open action needs.

cctop does not use a plugin popup or a plugin pane, for two reasons found on Herdr 0.9.1:

- A popup is not a pane, and only panes have mouse selection. Pull request 2667 of herdrdev/herdr, which added a selection to popups, was closed unmerged. Herdr also opens a popup only once at a time.
- A plugin pane opened with `--placement zoomed` keeps the size of the pane that it was opened from until a click (issue 3799 of herdrdev/herdr, open in 0.9.1).

herdtop is a Herdr plugin, so it must check both limits again on the Herdr version that it targets.

### Opening a session in a tab

cctop calls a helper of the Herdr setup with three arguments: the session id, the working directory and the title. It adds `--attach` for a background session. It shows the last line of the output as its message, reads an exit status other than 0 as a refusal, and stops waiting after 20 seconds.

The helper:

1. Refuses outside Herdr. It also refuses an id that is not made of hex digits and hyphens, because it types the id into a shell.
2. If a Herdr agent already shows the session, by its `agent_session.value`, focuses that tab, starts nothing and says so.
3. Finds the workspace of the directory. The first choice is the workspace whose label is the name that the naming rule of the setup gives the directory. The second choice is a workspace with a pane in that directory. If there is none, the helper creates a workspace with that label, without focus. It labels the first tab of that workspace with the title and uses its first pane.
4. If the workspace existed, creates a tab in it, in that directory, labelled with the first 60 characters of the title, without focus.
5. Types `claude --resume <id>`, or `claude attach <id>`, into the first pane of the tab, then focuses the workspace and the tab.

The helper and the tab opener of the setup must use the same naming rule. Else one directory gets two workspaces.

The Herdr calls that this needs: `workspace create` (cwd, label, focus), `tab create` (workspace, cwd, label, focus), `tab rename`, `pane run`, the pane list (`cwd`, `agent`, `terminal_title_stripped`), `workspace focus` and `tab focus`.

## Session names and Herdr tabs

- The list names a session by its transcript title: the last rename, else the last generated title.
- The tool finds the Herdr tab of a session by the session id in `herdr agent list`. Herdr learns the id when the agent starts, so an agent that Herdr has not placed yet has no id. The tab of a parked job is found through the id of its front end.
- The title labels a tab that the tool opens. The tool never finds a tab by its label or by its terminal title.
- A tab that opens before Herdr knows its session id can be found only by its title. Claude Code sets the terminal title of its pane to the session name, and Herdr reports it as `terminal_title_stripped`; a match ignores case. cctop does not do this. The tab openers of the Herdr setup do.

## Codex

The Claude reader gives the items below. A Codex reader must give each of them too, or say that Codex has none:

- the session id, the working directory and the path of the transcript;
- a name, and whether a person set it;
- the time of the last answer, and the size and modification time of the files;
- the prompts and the answers with their dates, without what the client adds;
- for each call, counted once: the model, the input, the cached input, the output and the reasoning tokens;
- the context of the last call;
- the cache state: a TTL and an expiry, or none;
- the agents that the session started, with their cost;
- whether a process holds the session, its kind, its status and the program that shows it;
- the command that resumes the session, and the one that joins it while it runs;
- the files to move for an archive and a restore;
- the gauges of the account, if a file carries them;
- a price for each of its models;
- a way to rename, or none.

The sources are the rollout files under `~/.codex/sessions/` and the index `~/.codex/session_index.jsonl`. Herdr may not know the session id of a Codex agent that a person started by hand. The Herdr lookup by id then misses that agent.

## What the cctop tests check

herdtop keeps these properties:

- Tests never read the real store. They build their own store, account, payload and registry, and a `herdr` that answers nothing.
- A rename early in a long file wins over the generated title.
- Two working directories with the same slug keep their own directory.
- One id in two project directories gives two rows that act apart, because a session is keyed on its path, never on its id. A lookup by id prefix refuses an id that matches two transcripts.
- The tool never moves or archives an open session.
- A session that disappears under the list breaks nothing.
- A call counts once across resumes and compactions.
- A parked conversation counts once.
- The age is the last answer, not the file time.
- The tool asks for no mouse reports.
- Each colour has a glyph or a word.

## What herdtop leaves out of cctop

- The status line command that saves the payload belongs to the setup that cctop was written for. herdtop needs its own, or documents how to save the payload.
- The helper that opens a tab belongs to a Herdr setup. herdtop opens the tab itself.
- The help and the `$` screen of cctop link to internal pages, and the defaults come with figures measured on an internal store. herdtop keeps the defaults, and drops the links and the figures.
- The rate table of cctop and its dates. herdtop takes its rates from the public price list, with a date per row.
- The wording of the screens. herdtop writes its own.
- The version history of cctop. herdtop keeps a history in the tool, printed by `--changes`, and starts it at its first version.
- The distribution of cctop: one script, run by a script runner, and installed by a shared deployment.

## Proposals

None of these is in cctop:

- A web screen with the same lists in a browser. It was proposed for another session manager, and deferred.
- One verdict for each band and each cache state, warm or cold, in place of one verdict for each band with one exception.
- `R` refuses an open session, as `m` and `x` do: a rename appends to a file that the open session also writes.
- Decide whether a narrower column of a lower rank may take the room that a wider column leaves.
- `r` reads Herdr again.
