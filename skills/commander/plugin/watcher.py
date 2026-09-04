#!/usr/bin/env python3
"""
Commander watcher — Herdr event hook for pane.agent_status_changed.

On blocked: checks rules.json for a high-confidence match and auto-handles.
Each unresolved non-Commander block is atomically queued before Commander is woken.
Repeated stale events do not duplicate an unresolved queue record.
"""
from contextlib import contextmanager
import datetime
import fnmatch
import json
import os
import re
import subprocess
import time
import traceback


STATE_DIR = os.path.expanduser("~/.commander")
MEMORY_DIR = os.path.join(STATE_DIR, "memory")
DATA_DIR = os.path.join(STATE_DIR, "data")
DEBUG_LOG  = os.path.join(DATA_DIR, "watcher-debug.log")
PENDING_BLOCKS_FILE = "pending-blocks.json"
BLOCKED_COMMANDS_FILE = "blocked-commands.json"
READ_LINES = 200
SUBMIT_CONFIRM_TIMEOUT_MS = 5000


def dlog(msg):
    os.makedirs(DATA_DIR, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

TRIGGER_PHRASES = {
    "shell_approval": [
        "Do you want to proceed?",
        "Proceed?",
        "1. Yes",
        "❯ 1. Yes",
        "Do you want to run this command?",
    ],
    "confirmation": [
        "Are you sure?",
        "Confirm?",
        "y/n",
        "(y/N)",
    ],
    "accept_edits": [
        "⏵⏵ accept edits",
        "accept edits on",
    ],
}


def main():
    try:
        _main()
    except Exception:
        dlog(f"CRASH: {traceback.format_exc()}")


def _main():
    event = parse_event()
    dlog(f"event={json.dumps(event)[:200]}")
    if not event:
        return

    data = event.get("data", event)
    pane_id = data.get("pane_id", "")
    new_status = data.get("agent_status", "")
    dlog(f"pane_id={pane_id} status={new_status}")

    if new_status not in ("blocked", "done"):
        return

    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    commander_pane = read_commander_pane()
    dlog(f"herdr={herdr} commander_pane={commander_pane}")

    if not commander_pane:
        dlog("no commander_pane, abort")
        return
    tab_label = get_tab_label(herdr, pane_id)
    dlog(f"tab_label={tab_label}")

    if _is_commander_approval_pane(commander_pane, pane_id, tab_label):
        # Self approval covers Commander's pane and its dedicated blocked-review pane.
        dlog("commander approval path")
        if new_status == "blocked":
            _maybe_self_approve(herdr, pane_id)
        return

    if new_status == "blocked":
        pane_output = read_pane(herdr, pane_id)
        if _matches_ignore_blocked_patterns(pane_output):
            dlog(f"ignore_blocked_patterns matched, suppressing event pane_id={pane_id}")
            return

        handled, rule_id, cmd, confidence = try_auto_handle(herdr, pane_id, tab_label)
        dlog(f"auto_handle: handled={handled} rule={rule_id}")
        if handled:
            log_decision(tab_label, rule_id, cmd, confidence, auto=True, outcome="approved")
            return

        pane_output = read_pane(herdr, pane_id)
        if _is_shell_approval_block(pane_output):
            record = enqueue_pending_block(herdr, pane_id, tab_label)
            if not record:
                dlog(f"pending block duplicate suppressed pane_id={pane_id}")
                return
            log_decision(tab_label, "none", cmd, 0, auto=False, outcome="escalated")
        else:
            dlog(f"non-approval blocked pane ignored pane_id={pane_id}")

    if new_status == "done":
        pane_output = read_pane(herdr, pane_id)
        if any(hint in pane_output for hint in ("Waiting for background agents", "esc stop agents", "esc to interrupt", "esc interrupt")):
            dlog(f"suppressing false done event for active pane pane_id={pane_id}")
            return

    speak_fleet_update(herdr, pane_id, new_status)
    wake_commander(herdr, commander_pane, pane_id, new_status)


def parse_event():
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def read_commander_pane():
    # Live tab lookup first — file can be stale across sessions
    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    live = _find_commander_pane_by_tab(herdr)
    if live:
        return live
    path = os.path.join(MEMORY_DIR, "commander-pane.txt")
    try:
        with open(path) as f:
            value = f.read().strip()
            if value:
                return value
    except IOError:
        pass
    return None


def _find_commander_pane_by_tab(herdr):
    try:
        tabs_result = subprocess.run([herdr, "tab", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        tabs_data = json.loads(tabs_result.stdout)
        commander_tab_ids = {
            t["tab_id"]
            for t in tabs_data["result"]["tabs"]
            if t.get("label", "").lower() == "commander"
        }
        if not commander_tab_ids:
            return None

        panes_result = subprocess.run([herdr, "pane", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        panes_data = json.loads(panes_result.stdout)
        for pane in panes_data["result"]["panes"]:
            if pane.get("tab_id") in commander_tab_ids:
                return pane["pane_id"]
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def _maybe_self_approve(herdr, pane_id):
    config = load_config()
    pane_output = read_pane(herdr, pane_id)
    if config.get("auto_approve_commander_pane", False) and _is_shell_approval_block(pane_output):
        log_decision("Commander", "self-approve-attempt", "", 1.0, auto=True, outcome="approved")
        send_enter(herdr, pane_id)
        log_decision("Commander", "self-approve-sent", "", 1.0, auto=True, outcome="approved")


def _is_commander_approval_pane(commander_pane, pane_id, tab_label):
    return (
        bool(commander_pane and pane_id.casefold() == commander_pane.casefold())
        or tab_label.casefold() in ("commander", "blocked review")
    )


def try_auto_handle(herdr, pane_id, tab_label):
    """Return (handled, rule_id, cmd, confidence)."""
    config = load_config()
    pane_output = read_pane(herdr, pane_id)
    cmd = _extract_cmd(pane_output)
    rules = load_rules()
    compound_rules = [rule for rule in rules if rule.get("allow_compound", False)]

    if compound_rules and not _has_pending_user_question(pane_output):
        compound_rule = find_compound_rule(compound_rules, "*", pane_output)
        if compound_rule:
            handled = execute_action(herdr, pane_id, compound_rule)
            if handled:
                record_rule_use(compound_rule.get("id", "unknown"))
                return True, compound_rule.get("id", "unknown"), compound_rule.get("cmd_pattern", cmd), compound_rule.get("confidence", 0)

    if _is_shell_approval_block(pane_output):
        # Per-tab approval is independent of Commander self approval and only runs for non-Commander panes.
        auto_approve_tabs = config.get("auto_approve_tabs", [])
        if auto_approve_tabs and tab_label in auto_approve_tabs:
            if not tab_label_is_unique(herdr, tab_label):
                dlog(f"duplicate tab label, skip auto-approve tab={tab_label}")
            else:
                subprocess.run([herdr, "pane", "send-text", pane_id, "1"], capture_output=True)
                if send_enter(herdr, pane_id):
                    return True, "auto-approve-tab", cmd, 1.0

        agent, pane_cwd = get_pane_info(herdr, pane_id)
        best = find_best_rule(rules, agent, pane_output, pane_cwd)
        if best:
            handled = execute_action(herdr, pane_id, best)
            if handled:
                record_rule_use(best.get("id", "unknown"))
                return True, best.get("id", "unknown"), best.get("cmd_pattern", cmd), best.get("confidence", 0)

    if compound_rules:
        pane_output = read_pane(herdr, pane_id, 500, "detection")
        cmd = _extract_cmd(pane_output)
        compound_rule = (
            find_compound_rule(compound_rules, "*", pane_output)
            if not _has_pending_user_question(pane_output)
            else None
        )
        if compound_rule:
            handled = execute_action(herdr, pane_id, compound_rule)
            if handled:
                record_rule_use(compound_rule.get("id", "unknown"))
                return True, compound_rule.get("id", "unknown"), compound_rule.get("cmd_pattern", cmd), compound_rule.get("confidence", 0)
    return False, "none", cmd, 0


def load_rules():
    path = _rules_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", data) if isinstance(data, dict) else data
    except (IOError, json.JSONDecodeError):
        return []


def _rules_path():
    return os.path.join(MEMORY_DIR, "rules.json")


def record_rule_use(rule_id, timestamp=None):
    """Increment use metadata for a rule that completed its approval action."""
    path = _rules_path()
    with _pending_blocks_lock(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (IOError, json.JSONDecodeError):
            return False

        rules = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(rules, list):
            return False

        for rule in rules:
            if rule.get("id") == rule_id:
                rule["use_count"] = int(rule.get("use_count", 0)) + 1
                rule["last_used"] = timestamp or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                tmp_path = f"{path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, path)
                return True
    return False


def log_decision(tab, rule_id, cmd, confidence, auto, outcome):
    os.makedirs(DATA_DIR, exist_ok=True)
    record = {
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rule_id": rule_id,
        "tab": tab,
        "cmd": cmd[:120] if cmd else "",
        "confidence": confidence,
        "auto": auto,
        "outcome": outcome,
    }
    log_path = os.path.join(DATA_DIR, "decisions-log.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _empty_pending_blocks():
    return {"version": 1, "next_id": 1, "next_order": 1, "records": []}


def _pending_blocks_path():
    return os.path.join(DATA_DIR, PENDING_BLOCKS_FILE)


def _blocked_commands_path():
    return os.path.join(DATA_DIR, BLOCKED_COMMANDS_FILE)


def _load_pending_blocks(path):
    try:
        with open(path, "rb") as f:
            contents = f.read()
    except IOError:
        return _empty_pending_blocks()

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            queue = json.loads(contents.decode(encoding))
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError:
            return _empty_pending_blocks()

        if not isinstance(queue, dict) or not isinstance(queue.get("records"), list):
            return _empty_pending_blocks()
        queue.setdefault("version", 1)
        queue.setdefault("next_id", len(queue["records"]) + 1)
        queue.setdefault("next_order", len(queue["records"]) + 1)
        if encoding != "utf-8-sig":
            dlog(f"pending blocks recovered encoding={encoding}")
        return queue

    return _empty_pending_blocks()


def _empty_blocked_commands():
    return {"version": 1, "records": []}


def _load_blocked_commands(path):
    try:
        with open(path, encoding="utf-8") as f:
            log = json.load(f)
        if not isinstance(log, dict) or not isinstance(log.get("records"), list):
            return _empty_blocked_commands()
        log.setdefault("version", 1)
        return log
    except (IOError, json.JSONDecodeError):
        return _empty_blocked_commands()


def _save_pending_blocks(path, queue):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _save_blocked_commands(path, log):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


@contextmanager
def _pending_blocks_lock(path):
    """Serialize watcher processes so simultaneous blocks cannot be lost or duplicated."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(f"{path}.lock", "a+", encoding="utf-8") as lock:
        lock.write("0")
        lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _queue_text(value):
    return " ".join((value or "").split()).casefold()


def _pending_block_fingerprint(pane_id, command, prompt):
    return "\x1f".join(
        (_queue_text(pane_id), "blocked", _queue_text(command), _queue_text(prompt))
    )


def _blocked_command_key(tab_label, cwd, command, prompt):
    return "\x1f".join(
        (_queue_text(tab_label), _queue_text(cwd), _queue_text(command), _queue_text(prompt))
    )


def record_blocked_command(tab_label, cwd, command, prompt, timestamp):
    """Increment aggregate blocked-command usage for one tab and repository."""
    path = _blocked_commands_path()
    os.makedirs(DATA_DIR, exist_ok=True)
    with _pending_blocks_lock(path):
        log = _load_blocked_commands(path)
        key = _blocked_command_key(tab_label, cwd, command, prompt)

        for record in log["records"]:
            if record.get("key") == key:
                record["count"] = int(record.get("count", 0)) + 1
                record["last_seen"] = timestamp
                _save_blocked_commands(path, log)
                return record

        record = {
            "key": key,
            "tab": tab_label,
            "cwd": cwd,
            "command": command,
            "prompt": prompt,
            "count": 1,
            "first_seen": timestamp,
            "last_seen": timestamp,
        }
        log["records"].append(record)
        _save_blocked_commands(path, log)
        return record


def _extract_prompt(pane_output):
    for line in _clean_pane_lines(pane_output):
        normalized = line.lstrip("?❯ ").strip()
        if normalized in TRIGGER_PHRASES["shell_approval"]:
            return line
    return ""


def _is_shell_approval_block(pane_output):
    """Return true only for a shell command approval, never a generic agent question."""
    lines = _clean_pane_lines(pane_output)
    prompt = _extract_prompt(pane_output)
    if not prompt:
        return False

    if prompt in {"Do you want to run this command?", "Do you want to allow this?"}:
        return bool(_extract_cmd(pane_output))

    prompt_index = lines.index(prompt)
    return any(line.startswith("$ Shell ") for line in lines[:prompt_index])


def _has_pending_user_question(pane_output):
    """Return true when the newest agent question lacks a recorded selection."""
    lines = _clean_pane_lines(pane_output)
    question_indexes = [
        index for index, line in enumerate(lines) if "Asked user" in line or "Asking user" in line
    ]
    if not question_indexes:
        return False
    return not any("User selected:" in line for line in lines[question_indexes[-1] + 1:])


def enqueue_pending_block(herdr, pane_id, tab_label):
    """Persist one unknown blocked pane, unless its unresolved event is already queued."""
    pane_output = read_pane(herdr, pane_id)
    if not _is_shell_approval_block(pane_output):
        dlog(f"non-approval blocked pane ignored pane_id={pane_id}")
        return None

    agent, cwd = get_pane_info(herdr, pane_id)
    command = _extract_cmd(pane_output)
    prompt = _extract_prompt(pane_output)
    fingerprint = _pending_block_fingerprint(pane_id, command, prompt)
    path = _pending_blocks_path()

    with _pending_blocks_lock(path):
        queue = _load_pending_blocks(path)
        if any(
            record.get("status") == "pending"
            and record.get("fingerprint") == fingerprint
            for record in queue["records"]
        ):
            dlog(f"pending block duplicate pane_id={pane_id}")
            return None

        sequence = int(queue["next_id"])
        order = int(queue["next_order"])
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "id": f"block-{sequence:04d}-{order:04d}",
            "order": order,
            "ts": timestamp,
            "status": "pending",
            "tab": tab_label,
            "tab_label": tab_label,
            "pane_id": pane_id,
            "agent": agent or "",
            "cwd": cwd or "",
            "command": command,
            "prompt": prompt,
            "fingerprint": fingerprint,
        }
        queue["records"].append(record)
        queue["next_id"] = sequence + 1
        queue["next_order"] = order + 1
        _save_pending_blocks(path, queue)
        record_blocked_command(tab_label, cwd or "", command, prompt, timestamp)
        dlog(f"pending block enqueued id={record['id']} pane_id={pane_id}")
        return record


def load_ignore_segments():
    return load_config().get("ignore_segments", [])


def load_ignore_segment_regexes():
    return load_config().get("ignore_segment_regexes", [])


def _matches_ignore_blocked_patterns(pane_output):
    """Return True if pane content matches any ignore_blocked_patterns from config."""
    patterns = load_config().get("ignore_blocked_patterns", [])
    if not patterns:
        return False
    return any(p in pane_output for p in patterns)


def _split_cmd_segments(cmd):
    """Split command on ; && || |, drop pure cd steps."""
    parts = re.split(r'\s*(?:&&|\|\||[;|])\s*', cmd)
    result = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        if re.match(r'^cd\s+\S+$', s, re.IGNORECASE):
            continue
        result.append(s)
    return result


def _filter_ignored_segments(segments):
    """Remove segments matching any ignore_segments pattern from config."""
    patterns = load_ignore_segments()
    regexes = load_ignore_segment_regexes()
    if not patterns and not regexes:
        return segments
    return [
        s
        for s in segments
        if not any(fnmatch.fnmatch(s, pattern) for pattern in patterns)
        and not any(re.fullmatch(pattern, s) for pattern in regexes)
    ]


def _extract_cmd(pane_output, normalize=True):
    """Extract the command inside the shell approval box when present."""
    skip = {"Do you want to run this command?", "Do you want to allow this?",
            "Do you want to proceed?", "1. Yes", "❯ 1. Yes"}
    lines = _clean_pane_lines(pane_output)
    prompt = _extract_prompt(pane_output)
    if prompt:
        skip.add(prompt)
    prompt_index = lines.index(prompt) if prompt else None

    if prompt_index is not None:
        shell_header_index = next(
            (i for i in range(prompt_index - 1, -1, -1) if lines[i].startswith("$ Shell ")),
            None,
        )
        if shell_header_index is not None:
            command_lines = lines[shell_header_index + 1:prompt_index]
            if command_lines:
                return _normalize_cmd(command_lines[0]) if normalize else command_lines[0]

    for index, line in enumerate(lines):
        if line.startswith("$target="):
            command = line
            if index + 1 < len(lines) and lines[index + 1].startswith("\\"):
                command += lines[index + 1]
            return _normalize_cmd(command) if normalize else command

    for line in lines:
        if len(line) > 3 and line not in skip:
            return _normalize_cmd(line) if normalize else line
    return ""


def _normalize_cmd(line):
    segs = _filter_ignored_segments(_split_cmd_segments(line))
    return " && ".join(segs) if segs else line


def read_pane(herdr, pane_id, lines=READ_LINES, source="recent"):
    result = subprocess.run(
        [herdr, "pane", "read", pane_id, "--source", source, "--lines", str(lines)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def get_pane_info(herdr, pane_id):
    """Return (agent_label, live cwd) for the pane."""
    result = subprocess.run(
        [herdr, "pane", "get", pane_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        data = json.loads(result.stdout)
        pane = data["result"]["pane"]
        cwd = pane.get("foreground_cwd") or pane.get("cwd") or ""
        return pane.get("agent", "*"), cwd
    except (TypeError, json.JSONDecodeError, KeyError):
        return "*", ""


def tab_label_is_unique(herdr, tab_label):
    if not tab_label:
        return False
    try:
        tabs_result = subprocess.run(
            [herdr, "tab", "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        tabs_data = json.loads(tabs_result.stdout)
        labels = [t.get("label", "") for t in tabs_data["result"]["tabs"]]
        return labels.count(tab_label) == 1
    except (json.JSONDecodeError, KeyError, OSError, TypeError):
        return False


def confirm_submit(herdr, pane_id):
    """True when the pane leaves the approval prompt for working."""
    r = subprocess.run(
        [herdr, "agent", "wait", pane_id, "--status", "working",
         "--timeout", str(SUBMIT_CONFIRM_TIMEOUT_MS)],
        capture_output=True,
    )
    if r.returncode != 0:
        dlog(f"submit not confirmed pane_id={pane_id}")
        return False
    return True


def send_enter(herdr, pane_id):
    r = subprocess.run(
        [herdr, "pane", "send-keys", pane_id, "enter"],
        capture_output=True,
    )
    return r.returncode == 0 and confirm_submit(herdr, pane_id)


def find_best_rule(rules, agent, pane_output, pane_cwd=""):
    """Return the most specific high-confidence matching rule, or None."""
    compound_rule = find_compound_rule(rules, agent, pane_output, pane_cwd)
    if compound_rule:
        return compound_rule

    raw_command = _extract_cmd(pane_output, normalize=False)
    command = _normalize_cmd(raw_command)
    segments = _filter_ignored_segments(_split_cmd_segments(command))
    if segments:
        matching_rules = [
            _find_best_rule_for_command(rules, agent, segment, pane_output, pane_cwd)
            for segment in segments
        ]
        if any(rule is None for rule in matching_rules):
            return None
        return matching_rules[0]

    return _find_best_rule_for_command(rules, agent, "", pane_output, pane_cwd)


def find_compound_rule(rules, agent, pane_output, pane_cwd=""):
    raw_command = _extract_cmd(pane_output, normalize=False)
    return _find_best_rule_for_command(
        rules, agent, raw_command, pane_output, pane_cwd, compound_only=True
    )


def _find_best_rule_for_command(
    rules, agent, command, pane_output, pane_cwd, compound_only=False
):
    best_specificity = -1
    best_rule = None

    for rule in rules:
        if rule.get("confidence", 0) < 0.8:
            continue
        if compound_only and not rule.get("allow_compound", False):
            continue

        rule_agent = rule.get("agent", "*")
        if rule_agent != "*" and rule_agent != agent:
            continue

        if not _rule_matches_command(rule, command, pane_output, pane_cwd):
            continue

        # More constrained = higher specificity: agent-scoped, cwd-scoped, fewer wildcards
        cmd_pattern = rule.get("cmd_pattern", "")
        specificity = (
            (rule_agent != "*")
            + bool(rule.get("cwd"))
            + (bool(cmd_pattern) and cmd_pattern.count("*") == 0)
        )
        if specificity > best_specificity:
            best_specificity = specificity
            best_rule = rule

    return best_rule


def rule_matches(rule, pane_output, pane_cwd=""):
    """Return True if the rule matches the current pane state."""
    return any(
        _rule_matches_command(rule, line, pane_output, pane_cwd)
        for line in _clean_pane_lines(pane_output)
    )


def _rule_matches_command(rule, command, pane_output, pane_cwd=""):
    trigger = rule.get("trigger", "")
    cmd_pattern = rule.get("cmd_pattern", "")
    cmd_prefix_pattern = rule.get("cmd_prefix_pattern", "")
    pane_prefix_pattern = rule.get("pane_prefix_pattern", "")
    rule_cwd = rule.get("cwd", "")

    # Trigger phrase must appear in pane output.
    # Unknown trigger type (not in TRIGGER_PHRASES) fails safe — prevents loose cmd_pattern
    # matches from firing on unrelated pane output.
    phrases = TRIGGER_PHRASES.get(trigger, None)
    if trigger and phrases is None:
        return False
    if phrases and not rule.get("allow_compound", False) and not any(p in pane_output for p in phrases):
        return False

    # cwd scope: pane cwd must start with rule cwd (case-insensitive)
    if rule_cwd and not pane_cwd.lower().startswith(rule_cwd.lower()):
        return False

    if cmd_prefix_pattern:
        return fnmatch.fnmatch(command, cmd_prefix_pattern)

    if pane_prefix_pattern:
        return any(
            fnmatch.fnmatch(line, pane_prefix_pattern)
            for line in _clean_pane_lines(pane_output)
        )

    # cmd_pattern: fnmatch against cleaned lines from the pane
    if cmd_pattern:
        return any(
            fnmatch.fnmatch(candidate, cmd_pattern)
            for raw_candidate in (command, command[2:] if command.startswith("& ") else command)
            for candidate in (raw_candidate, _normalize_cmd(raw_candidate))
        )

    # Legacy pattern field (substring match)
    pattern = rule.get("pattern", "*")
    if pattern != "*" and pattern not in command:
        return False

    return bool(phrases) or pattern != "*"


def _clean_pane_lines(pane_output):
    """Strip box-drawing UI chrome from pane lines for command matching."""
    strip_chars = "│╭╰╸╺┃╮╯─ \t"
    lines = []
    for line in pane_output.splitlines():
        cleaned = line.strip().strip(strip_chars).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def execute_action(herdr, pane_id, rule):
    action = rule.get("action", "")

    if action == "send_enter":
        return send_enter(herdr, pane_id)

    if action == "send":
        value = rule.get("value", "")
        r = subprocess.run([herdr, "agent", "send", pane_id, value],
                           capture_output=True)
        return r.returncode == 0

    if action == "notify_only":
        return False

    if action.startswith("send_text_enter:"):
        text = action[len("send_text_enter:"):]
        subprocess.run([herdr, "pane", "send-text", pane_id, text],
                       capture_output=True)
        return send_enter(herdr, pane_id)

    if action.startswith("send_text:"):
        text = action[len("send_text:"):]
        r = subprocess.run([herdr, "pane", "send-text", pane_id, text],
                           capture_output=True)
        return r.returncode == 0

    return False


def load_config():
    path = os.path.join(STATE_DIR, "config.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def get_tab_label(herdr, pane_id):
    try:
        tabs_result = subprocess.run([herdr, "tab", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        tabs_data = json.loads(tabs_result.stdout)
        tab_map = {t["tab_id"]: t.get("label", "") for t in tabs_data["result"]["tabs"]}

        panes_result = subprocess.run([herdr, "pane", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        panes_data = json.loads(panes_result.stdout)
        for pane in panes_data["result"]["panes"]:
            if pane["pane_id"] == pane_id:
                return tab_map.get(pane["tab_id"], "")
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return pane_id


def speak_fleet_update(herdr, pane_id, status):
    config = load_config()
    speak_cfg = config.get("speak", {})
    if not speak_cfg.get("enabled", False):
        return

    label = get_tab_label(herdr, pane_id)
    voice = speak_cfg.get("voice", "am_adam")

    speak_py = os.path.expanduser("~/.claude/skills/speak/speak.py")
    if os.path.exists(speak_py):
        text = f"Captain! Tab {label} is {status}."
        r = subprocess.run(
            ["python", speak_py, text, "--voice", voice],
            capture_output=True,
        )
        if r.returncode == 0:
            return

    # SAPI fallback
    sapi_text = f"Captain - Tab {label} is {status}."
    subprocess.run(
        ["powershell", "-Command",
         f"Add-Type -AssemblyName System.Speech; "
         f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
         f"$s.Speak('{sapi_text}')"],
        capture_output=True,
    )


def wake_commander(herdr, commander_pane, pane_id, status):
    tab_label = get_tab_label(herdr, pane_id)
    msg = f"[FLEET UPDATE] {tab_label} ({pane_id}) → {status}"
    subprocess.run(
        [herdr, "notification", "show", f"Fleet: {tab_label} — {status}", "--body", pane_id,
         "--position", "top-right", "--sound", "request"],
        capture_output=True,
    )
    # Wait for Commander to be idle before delivering — agent send to a working pane
    # writes to the input buffer but the follow-up Enter is lost mid-response.
    # Skip delivery if Commander stays blocked/working beyond 5 min to avoid
    # injecting Enter into an unrelated shell approval dialog on timeout.
    # TUI composers swallow pane-run's atomic Enter. Type, pause, then submit.
    log_decision("Commander", "wake-attempt", msg, 0, auto=True, outcome="escalated")
    r = subprocess.run(
        [herdr, "agent", "wait", commander_pane, "--status", "idle", "--timeout", "300000"],
        capture_output=True,
    )
    if r.returncode != 0:
        log_decision("Commander", "wake-wait-timeout", msg, 0, auto=True, outcome="escalated")
        return
    log_decision("Commander", "wake-sending", msg, 0, auto=True, outcome="escalated")
    subprocess.run(
        [herdr, "pane", "send-text", commander_pane, msg],
        capture_output=True,
    )
    time.sleep(1)
    subprocess.run(
        [herdr, "pane", "send-keys", commander_pane, "enter"],
        capture_output=True,
    )
    log_decision("Commander", "wake-sent", msg, 0, auto=True, outcome="approved")


if __name__ == "__main__":
    main()
