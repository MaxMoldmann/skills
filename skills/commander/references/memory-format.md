# Commander Memory Format

All mutable files live at: `~/.commander/`. The installed skill directory contains only Commander code and plugin files.

```
config.json              — Commander preferences and approval settings
memory/
  commander-pane.txt   — current Commander pane ID (written on startup)
  rules.json           — sorted patterns for auto-handling (maintained by Commander)

data/
  decisions-log.jsonl — append-only decision history
  backlog.md           — Backlog / In Progress / Done
  pending-blocks.json  — durable newest-first review queue of unresolved external blocks
  blocked-commands.json — aggregate blocked-command usage by tab and repository
```

---

## commander-pane.txt

Plain text, one line. Written on startup:
```bash
echo "$HERDR_PANE_ID" > ~/.commander/memory/commander-pane.txt
```

---

## rules.json

Array sorted by specificity descending (most specific first).

**Fields:**
- `trigger` — event class: `shell_approval`, `confirmation`, `done`
- `agent` — agent label or `*` for any: `claude`, `copilot`, `*`
- `cmd_pattern` — fnmatch glob matched against cleaned command lines in pane output (e.g. `git log *`, `git *`). Takes precedence over `pattern` when present.
- `cwd` — optional path prefix for repo-scoped rules; matched case-insensitively against pane `.foreground_cwd` (live cwd; `.cwd` is frozen at create) startswith
- `pattern` — legacy substring match in raw pane output, or `*` for any. Use `cmd_pattern` for new rules.
- `action` — `send_enter` · `notify_only` · `send_text:<literal>` · `send_text_enter:<literal>` (types text then presses enter — use for numbered menu selections)
- `confidence` — float 0.0–1.0. Auto-execute silently when ≥ 0.8; below that, propose to Captain.
- `added` — ISO date
- `use_count` — successful approval actions executed by this rule
- `last_used` — ISO UTC timestamp of its latest successful action, or `null`

**Matching:** most specific rule wins. Specificity = (agent != `*`) + bool(cwd) + (cmd_pattern has no wildcards). Auto-execute only when `confidence ≥ 0.8`.

**Example:**
```json
[
  {
    "trigger": "shell_approval",
    "agent": "*",
    "cmd_pattern": "git log *",
    "cwd": "C:\\Workspace\\Repo\\maximum-skills",
    "action": "send_enter",
    "confidence": 0.9,
    "added": "2026-07-14",
    "use_count": 0,
    "last_used": null
  },
  {
    "trigger": "shell_approval",
    "agent": "*",
    "cmd_pattern": "git log *",
    "action": "send_enter",
    "confidence": 0.9,
    "added": "2026-07-14"
  },
  {
    "trigger": "shell_approval",
    "agent": "claude",
    "cmd_pattern": "rm *",
    "action": "notify_only",
    "confidence": 0.9,
    "added": "2026-07-14"
  }
]
```

The cwd-scoped rule wins over the global one for panes inside `maximum-skills`. The `rm *` rule escalates to Captain instead of auto-approving.

---

## pending-blocks.json

Watcher-owned queue. Do not delete pending records manually. Commander joins pending records to `blocked-commands.json`, reviewing highest aggregate count first and newest `last_seen` first.

```json
{
  "version": 1,
  "next_id": 2,
  "next_order": 2,
  "records": [
    {
      "id": "block-0001-0001",
      "order": 1,
      "ts": "2026-07-24T06:27:20Z",
      "status": "pending",
      "tab": "skill-factory",
      "tab_label": "skill-factory",
      "pane_id": "w1:p7",
      "agent": "copilot",
      "cwd": "C:\\Workspace\\Repo\\skill-factory",
      "command": "git status --short",
      "prompt": "Do you want to proceed?",
      "fingerprint": "normalized opaque duplicate key"
    }
  ]
}
```

`pending` is unresolved. Captain resolution changes status to `approved_once`, `rejected`, `rule_created`, or `dropped` and adds `resolved_at` plus `resolution`; it does not remove the record. A valid rule selected from a stale record is saved for future matching and retired as `rule_created` with `resolution.executed: false`. During `/review-blocks`, a record without enough command/prompt data for a safe complete rule is automatically marked `unreviewable` with `resolution: {"choice":"no_rule_candidate"}` and is never shown to Captain. Skipping the current record or all remaining records leaves them `pending` for a later `/review-blocks` session. Watcher atomically writes under a lock and skips only a duplicate fingerprint on another pending record.

---

## blocked-commands.json

Watcher-owned aggregate log. Keyed by normalized `tab`, `cwd`, `command`, and `prompt`, so matching commands in different tabs or repositories remain separate.

```json
{
  "version": 1,
  "records": [
    {
      "key": "normalized opaque aggregate key",
      "tab": "skill-factory",
      "cwd": "C:\\Workspace\\Repo\\skill-factory",
      "command": "git status --short",
      "prompt": "Do you want to proceed?",
      "count": 4,
      "first_seen": "2026-07-24T06:27:20Z",
      "last_seen": "2026-07-27T18:05:00Z"
    }
  ]
}
```

Increment `count` and update `last_seen` whenever watcher queues a new blocked command. `/review-blocks` sorts candidates by `count` descending, then `last_seen` descending.

---

## decisions-log.json

Append-only. Never edit existing entries.

**Fields:**
- `ts` — ISO timestamp
- `pane` — pane ID at decision time
- `agent` — agent label
- `trigger` — what triggered the decision
- `pattern` — matched substring (or snippet of pane output)
- `action` — action taken
- `source` — `captain` · `rule` · `afk`

**Example:**
```json
[
  {
    "ts": "2026-07-09T19:18:00",
    "pane": "w1:p1",
    "agent": "claude",
    "trigger": "shell_approval",
    "pattern": "Set-ExecutionPolicy",
    "action": "send_enter",
    "source": "captain"
  }
]
```

---

## backlog.md

```markdown
## Backlog
- [ ] investigate login test flakiness (explore)
- [ ] add dark mode to settings page (execute)

## In Progress
- [ ] fix auth token expiry bug (execute) (crewmate: w1:p3)

## Done
- [x] audit API rate limiting (explore) — report: data/audit-rate-limiting/report.md
```
