# Herdr CLI Reference for Commander

Installed `herdr` is the authority. Print a group when flags are uncertain:

```powershell
herdr --help
herdr agent
herdr pane
herdr tab
herdr workspace
```

Do not run bare `herdr` — it launches the TUI.

## Discovery

```powershell
herdr workspace list
herdr tab list --workspace $env:HERDR_WORKSPACE_ID
herdr pane list --workspace $env:HERDR_WORKSPACE_ID
herdr pane current --current
herdr agent list
```

Public IDs: workspace `w1`, tab `w1:t1`, pane `w1:p1`. Closed IDs are not reused. Re-read from list/create JSON — never cache, never derive from sidebar order.

## Reading panes

`--lines N` returns **empty** when N is smaller than the viewport. Request at least 200, then trim locally.

```powershell
herdr pane read <pane_id> --source recent-unwrapped --lines 200
herdr pane read <pane_id> --source visible --lines 200
herdr pane read <pane_id> --source recent --lines 200
herdr pane read <pane_id> --source detection --lines 200
```

- `recent-unwrapped` — logs and transcripts (preferred)
- `visible` — current viewport
- `recent` — rendered output with soft wraps
- `detection` — bottom-buffer snapshot used for agent detection

`--format ansi` only when styling is evidence (ghost composer text is dim).

`herdr pane get <pane_id>`: `.cwd` is frozen at create. Use `.foreground_cwd` for the live working directory.

If raising `--lines` does not reveal more of a finished reply, the agent is likely on the alternate screen. Ask it to write Markdown to a temp file and return the path.

## Sending input

Use the **agent** surface for recognized coding agents:

```powershell
herdr agent prompt <name-or-pane> "Review the diff." --wait --timeout 120000
herdr agent send-keys <name-or-pane> enter
herdr agent send-keys <name-or-pane> esc
herdr agent send-keys <name-or-pane> ctrl+c
```

`agent prompt` submits text + Enter while honoring bracketed paste. After a prompt that should start work, wait until status is `working` (or `blocked`). Do not treat "pane text changed" as proof of submit.

Use the **pane** surface for raw terminals and shells:

```powershell
herdr pane send-keys <pane_id> enter
herdr pane send-keys <pane_id> ctrl+c
herdr pane send-text <pane_id> "text"          # type only, no Enter
herdr pane run <pane_id> "just test"           # text + Enter; shells only
```

Do **not** `pane run` into TUI agent composers (Copilot, Claude, Cursor). They treat the burst as a paste and swallow Enter. Fallback: `send-text`, sleep ~1s, then `send-keys enter`.

Slash commands may open autocomplete; first Enter closes the popup. Send `esc` then Enter, or use `agent prompt`.

## Waiting

```powershell
herdr agent wait <name-or-pane> --timeout 600000
herdr agent wait <name-or-pane> --until blocked --timeout 120000
herdr pane wait-output <pane_id> --match "test result" --timeout 120000
```

Without `--until`, `agent wait` and `agent prompt --wait` settle on `idle`, `done`, or `blocked`.

`idle` means ready for input and seen in the focused UI. `done` is the same idle state after unseen background work. CLI reads do not mark seen. `blocked` = approval or question UI. `unknown` ≠ complete.

If status is `idle`/`done` but pane text shows `esc to interrupt`, a foreground tool is still running.

`agent get` returning `agent_not_found` after a server restart means a husk pane (fresh shell, dead registration). Close and replace. Do not treat as a live crewmate.

## Spawning crewmates

Need an existing available shell pane. `agent start` never splits layout.

```powershell
herdr tab list   # abort if the new label already exists
$RESULT = herdr tab create --workspace $env:HERDR_WORKSPACE_ID --label "fm-<id>" --no-focus | ConvertFrom-Json
$NEW_PANE = $RESULT.result.root_pane.pane_id
herdr agent start crewmate-<id> --kind copilot --pane $NEW_PANE
herdr agent prompt crewmate-<id> "<brief>" --wait
herdr agent wait crewmate-<id> --until done --timeout 600000
```

Names: `[a-z][a-z0-9_-]{0,31}`, unique among live agents. Pass native agent args only after `--`. Do not add `--yolo` or `--dangerously-skip-permissions`.

## Notifications and plugins

```powershell
herdr notification show "title" --body "body" --sound request
herdr plugin list
herdr plugin link <path>
herdr plugin unlink <plugin_id>
```

Never `herdr server stop` from a live session unless the Captain explicitly intends to kill the server.

## Current pane (self)

```powershell
$env:HERDR_ENV            # must be 1
$env:HERDR_PANE_ID
$env:HERDR_TAB_ID
$env:HERDR_WORKSPACE_ID
```
