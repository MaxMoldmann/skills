import importlib.util
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch


WATCHER_PATH = Path(__file__).with_name("watcher.py")
SPEC = importlib.util.spec_from_file_location("commander_watcher", WATCHER_PATH)
watcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watcher)


class WatcherQueueAcceptanceTest(unittest.TestCase):
    def test_reads_and_writes_mutable_state_in_commander_profile(self):
        state_dir = Path(__file__).parent / ".watcher-profile-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        (state_dir / "memory").mkdir(parents=True)
        (state_dir / "data").mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_tabs": ["Crew tab"]}),
            encoding="utf-8",
        )
        (state_dir / "memory" / "rules.json").write_text(
            json.dumps({"rules": [{"id": "profile-rule"}]}),
            encoding="utf-8",
        )

        self.assertEqual(os.path.expanduser("~/.commander"), watcher.STATE_DIR)

        with (
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "MEMORY_DIR", str(state_dir / "memory")),
            patch.object(watcher, "DATA_DIR", str(state_dir / "data")),
        ):
            self.assertEqual(["Crew tab"], watcher.load_config()["auto_approve_tabs"])
            self.assertEqual("profile-rule", watcher.load_rules()[0]["id"])
            watcher.log_decision("Crew tab", "profile-rule", "git status", 0.9, True, "approved")

        decision_log = state_dir / "data" / "decisions-log.jsonl"
        self.assertTrue(decision_log.exists())
        shutil.rmtree(state_dir)

    def test_compound_panel_prefix_rule_matches_architecture_diagram(self):
        rule = {
            "id": "architecture-diagram",
            "trigger": "shell_approval",
            "agent": "*",
            "cmd_pattern": "never-match",
            "pane_prefix_pattern": "Render CLI architecture diagram*",
            "allow_compound": True,
            "confidence": 0.9,
        }
        pane_output = (
            "Render CLI architecture diagram\n"
            "@' [{\"id\":\"zone-logic\"}] '@\n"
        )

        match = watcher.find_compound_rule([rule], "*", pane_output)

        self.assertEqual("architecture-diagram", match["id"])

    def test_compound_prefix_rule_does_not_answer_pending_user_question(self):
        rule = {
            "id": "grill-me",
            "trigger": "shell_approval",
            "agent": "*",
            "cmd_prefix_pattern": "$target='C:\\Users\\*\\grill-me-decision-tree.yaml'; *",
            "allow_compound": True,
            "action": "send_enter",
            "confidence": 0.9,
        }
        pane_output = (
            "$target='C:\\Users\\x\\grill-me-decision-tree.yaml'; python -c update\n"
            "Asked user **Q7 (1 left)** Choose a runtime\n"
        )

        with (
            patch.object(watcher, "load_config", return_value={}),
            patch.object(watcher, "load_rules", return_value=[rule]),
            patch.object(watcher, "read_pane", return_value=pane_output),
            patch.object(watcher.subprocess, "run") as run,
        ):
            handled, _, _, _ = watcher.try_auto_handle("herdr", "pane-1", "tab")

        self.assertFalse(handled)
        run.assert_not_called()

    def test_extract_cmd_finds_wrapped_target_after_detection_chrome(self):
        pane_output = (
            "Session Issues Pull requests Gists\n"
            "$target='C:\n"
            "\\Users\\x\\.copilot\\session-state\\s\\files\\grill-me-decision-tree.yaml'; "
            "python -c update\n"
        )

        command = watcher._extract_cmd(pane_output, normalize=False)

        self.assertEqual(
            "$target='C:\\Users\\x\\.copilot\\session-state\\s\\files\\grill-me-decision-tree.yaml'; python -c update",
            command,
        )

    def test_compound_prefix_rule_retries_with_500_lines_and_sends_enter(self):
        rule = {
            "id": "grill-me",
            "trigger": "shell_approval",
            "agent": "*",
            "cmd_pattern": "$target='C:\\Users\\*\\grill-me-decision-tree.yaml'; *",
            "cmd_prefix_pattern": "$target='C:\\Users\\*\\grill-me-decision-tree.yaml'; *",
            "allow_compound": True,
            "action": "send_enter",
            "confidence": 0.9,
        }
        first_read = "Python body\nDo you want to run this command?\n1. Yes"
        retry_read = (
            "$target='C:\\Users\\x\\grill-me-decision-tree.yaml'; python -c update\n"
        )
        command_result = type("Result", (), {"returncode": 0})()

        with (
            patch.object(watcher, "load_config", return_value={}),
            patch.object(watcher, "load_rules", return_value=[rule]),
            patch.object(watcher, "read_pane", side_effect=[first_read, retry_read]) as read,
            patch.object(watcher, "get_pane_info", return_value=("*", "")),
            patch.object(watcher.subprocess, "run", return_value=command_result) as run,
        ):
            handled, rule_id, _, _ = watcher.try_auto_handle("herdr", "pane-1", "tab")

        self.assertTrue(handled)
        self.assertEqual("grill-me", rule_id)
        self.assertEqual(
            [
                unittest.mock.call("herdr", "pane-1"),
                unittest.mock.call("herdr", "pane-1", 500, "detection"),
            ],
            read.call_args_list,
        )
        self.assertEqual(
            ["herdr", "pane", "send-keys", "pane-1", "enter"],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(
            ["herdr", "agent", "wait", "pane-1", "--status", "working", "--timeout", "5000"],
            run.call_args_list[1].args[0],
        )

    def test_self_approve_does_not_answer_commander_question(self):
        state_dir = Path(__file__).parent / ".watcher-self-approve-question-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_commander_pane": True}),
            encoding="utf-8",
        )

        with (
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(
                watcher,
                "read_pane",
                return_value="Should I add an allowlist?\n1. Yes\n2. No",
            ),
            patch.object(watcher, "log_decision"),
            patch.object(watcher.subprocess, "run") as run,
        ):
            watcher._maybe_self_approve("herdr", "commander-pane")

        run.assert_not_called()
        shutil.rmtree(state_dir)

    def test_read_pane_requests_enough_lines_for_large_approval_prompts(self):
        result = type("Result", (), {"stdout": ""})()

        with patch.object(watcher.subprocess, "run", return_value=result) as run:
            watcher.read_pane("herdr", "pane-1")

        run.assert_called_once_with(
            ["herdr", "pane", "read", "pane-1", "--source", "recent", "--lines", "200"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_load_rules_reads_utf8_rule_notes(self):
        state_dir = Path(__file__).parent / ".watcher-utf8-rules-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "rules.json").write_text(
            json.dumps(
                {"rules": [{"id": "utf8-rule", "note": "🦴"}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        original_open = open

        def windows_open(*args, **kwargs):
            kwargs.setdefault("encoding", "cp1252")
            return original_open(*args, **kwargs)

        with (
            patch.object(watcher, "MEMORY_DIR", str(state_dir)),
            patch("builtins.open", windows_open),
        ):
            rules = watcher.load_rules()

        self.assertEqual("🦴", rules[0]["note"])
        shutil.rmtree(state_dir)

    def test_rule_use_increments_count_and_updates_last_used(self):
        state_dir = Path(__file__).parent / ".watcher-rule-usage-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "rules.json").write_text(
            json.dumps({"rules": [{"id": "allow-status"}]}),
            encoding="utf-8",
        )

        with patch.object(watcher, "MEMORY_DIR", str(state_dir)):
            watcher.record_rule_use("allow-status", "2026-07-27T18:00:00Z")
            watcher.record_rule_use("allow-status", "2026-07-27T18:05:00Z")

        rules = json.loads((state_dir / "rules.json").read_text(encoding="utf-8"))["rules"]
        self.assertEqual(2, rules[0]["use_count"])
        self.assertEqual("2026-07-27T18:05:00Z", rules[0]["last_used"])

        shutil.rmtree(state_dir)

    def test_blocked_command_log_counts_per_tab_repo_and_updates_last_seen(self):
        state_dir = Path(__file__).parent / ".watcher-blocked-command-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()

        with patch.object(watcher, "DATA_DIR", str(state_dir)):
            watcher.record_blocked_command(
                "Crew tab",
                r"C:\Repo\crew",
                "git status --short",
                "Do you want to proceed?",
                "2026-07-27T18:00:00Z",
            )
            watcher.record_blocked_command(
                "Crew tab",
                r"C:\Repo\crew",
                "git status --short",
                "Do you want to proceed?",
                "2026-07-27T18:05:00Z",
            )

        log = json.loads((state_dir / "blocked-commands.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(log["records"]))
        self.assertEqual(2, log["records"][0]["count"])
        self.assertEqual("2026-07-27T18:05:00Z", log["records"][0]["last_seen"])

        shutil.rmtree(state_dir)

    def test_pending_queue_recovers_cp1252_records_and_rewrites_utf8(self):
        state_dir = Path(__file__).parent / ".watcher-pending-encoding-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        queue_path = state_dir / "pending-blocks.json"
        queue_path.write_bytes(
            b'{"version":1,"next_id":2,"next_order":2,"records":['
            b'{"id":"block-0001-0001","order":1,"status":"pending",'
            b'"command":"echo \x85","prompt":"Do you want to proceed?"}]}'
        )

        with patch.object(watcher, "DATA_DIR", str(state_dir)):
            queue = watcher._load_pending_blocks(str(queue_path))
            watcher._save_pending_blocks(str(queue_path), queue)

        self.assertEqual("echo \u2026", queue["records"][0]["command"])
        self.assertEqual(queue, json.loads(queue_path.read_text(encoding="utf-8")))
        self.assertEqual(
            queue_path.read_bytes(),
            queue_path.read_bytes().decode("utf-8").encode("utf-8"),
        )

        shutil.rmtree(state_dir)

    def test_ytr_issues_rule_matches_call_operator(self):
        rule = {
            "trigger": "shell_approval",
            "cmd_pattern": r".\Tools\ytr.ps1 issues *",
        }
        pane_output = r"""
$ Shell List issues
& .\Tools\ytr.ps1 issues list --format json
Do you want to run this command?
❯ 1. Yes
"""

        self.assertTrue(watcher.rule_matches(rule, pane_output))

    def test_rule_matching_ignores_configured_environment_assignments(self):
        state_dir = Path(__file__).parent / ".watcher-ignore-segment-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"ignore_segments": ["$env:PYTHONUTF8=*"]}),
            encoding="utf-8",
        )
        rule = {
            "trigger": "shell_approval",
            "cmd_pattern": "tar *",
        }
        pane_output = (
            "$env:PYTHONUTF8='1'; tar -tf archive.zip\n"
            "Do you want to run this command?\n"
            "1. Yes"
        )

        with patch.object(watcher, "STATE_DIR", str(state_dir)):
            self.assertTrue(watcher.rule_matches(rule, pane_output))

        shutil.rmtree(state_dir)

    def test_regex_ignore_segment_filters_local_variable_assignment(self):
        state_dir = Path(__file__).parent / ".watcher-regex-ignore-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps(
                {
                    "ignore_segment_regexes": [
                        r"^\$[A-Za-z_][A-Za-z0-9_]*\s*=\s*'[^']*'$"
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch.object(watcher, "STATE_DIR", str(state_dir)):
            command = watcher._normalize_cmd("$dir='C:\\patches'; tar -tf archive.zip")

        self.assertEqual("tar -tf archive.zip", command)
        shutil.rmtree(state_dir)

    def test_regex_ignore_segment_keeps_command_expression_assignment(self):
        state_dir = Path(__file__).parent / ".watcher-regex-ignore-expression-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps(
                {
                    "ignore_segment_regexes": [
                        r"^\$[A-Za-z_][A-Za-z0-9_]*\s*=\s*'[^']*'$"
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch.object(watcher, "STATE_DIR", str(state_dir)):
            command = watcher._normalize_cmd(
                "$dir=(Get-Location).Path; tar -tf archive.zip"
            )

        self.assertEqual(
            "$dir=(Get-Location).Path && tar -tf archive.zip",
            command,
        )
        shutil.rmtree(state_dir)

    def test_find_best_rule_requires_every_command_segment_to_match(self):
        rules = [
            {
                "trigger": "shell_approval",
                "agent": "*",
                "cmd_pattern": "Get-ChildItem *",
                "confidence": 0.9,
            }
        ]
        pane_output = (
            "Get-ChildItem files; Invoke-WebRequest https://example.test\n"
            "Do you want to run this command?\n"
            "1. Yes"
        )

        self.assertIsNone(watcher.find_best_rule(rules, "*", pane_output))

    def test_compound_prefix_rule_allows_grill_me_tree_updates(self):
        rules = [
            {
                "id": "auto-approve-grill-me-tree-updates",
                "trigger": "shell_approval",
                "agent": "copilot",
                "cmd_prefix_pattern": (
                    "$target='C:\\Users\\*\\.copilot\\session-state\\*"
                    "\\files\\grill-me-decision-tree.yaml'; *"
                ),
                "cmd_pattern": (
                    "$target='C:\\Users\\*\\.copilot\\session-state\\*"
                    "\\files\\grill-me-decision-tree.yaml'; *"
                ),
                "allow_compound": True,
                "confidence": 0.9,
            }
        ]
        pane_output = (
            "$target='C:\\Users\\E1429967\\.copilot\\session-state\\session-1"
            "\\files\\grill-me-decision-tree.yaml'; $patchDir='C:\\patches'; "
            "python -c \"replace tree\"\n"
            "Do you want to run this command?\n"
            "1. Yes"
        )

        match = watcher.find_best_rule(rules, "copilot", pane_output)

        self.assertEqual("auto-approve-grill-me-tree-updates", match["id"])

    def test_compound_prefix_rule_allows_grill_me_join_path_updates(self):
        rule = {
            "id": "grill-me-join-path",
            "trigger": "shell_approval",
            "agent": "*",
            "cmd_prefix_pattern": (
                "$root='C:\\Users\\*\\.copilot\\session-state\\*\\files'; "
                "$target=Join-Path $root 'grill-me-decision-tree.yaml'; *"
            ),
            "allow_compound": True,
            "confidence": 0.9,
        }
        pane_output = (
            "$root='C:\\Users\\E1429967\\.copilot\\session-state\\session-1\\files'; "
            "$target=Join-Path $root 'grill-me-decision-tree.yaml'; python -c update\n"
        )

        match = watcher.find_compound_rule([rule], "*", pane_output)

        self.assertEqual("grill-me-join-path", match["id"])

    def test_extract_cmd_prefers_shell_box_command_over_prior_status_prose(self):
        pane_output = r"""
● 🦴 Default ytr works now. Starting requested 100-root scan without NO_PROXY.
$ Shell Scan requirement roots without proxy override
  & .\Tools\add-subtask-links-from-stream.ps1 -Project VL -RootLimit 100 -LeafLimit 1 -WhatIf
Do you want to run this command?
❯ 1. Yes
"""

        command = watcher._extract_cmd(pane_output)

        self.assertEqual(
            r"& .\Tools\add-subtask-links-from-stream.ps1 -Project VL -RootLimit 100 -LeafLimit 1 -WhatIf",
            command,
        )

    def test_unknown_external_block_is_enqueued_with_review_metadata(self):
        state_dir = Path(__file__).parent / ".watcher-queue-acceptance-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_commander_pane": True, "auto_approve_tabs": []}),
            encoding="utf-8",
        )
        event = {"data": {"pane_id": "crew-pane-7", "agent_status": "blocked"}}

        with (
            patch.object(watcher, "MEMORY_DIR", str(state_dir)),
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "DATA_DIR", str(state_dir)),
            patch.dict(
                os.environ,
                {
                    "HERDR_BIN_PATH": "herdr",
                    "HERDR_PLUGIN_EVENT_JSON": json.dumps(event),
                },
                clear=False,
            ),
            patch.object(watcher, "read_commander_pane", return_value="commander-pane"),
            patch.object(watcher, "speak_fleet_update") as speak,
            patch.object(watcher, "get_tab_label", return_value="Crew tab"),
            patch.object(watcher, "try_auto_handle", return_value=(False, "none", "", 0)),
            patch.object(
                watcher,
                "read_pane",
                return_value="$ Shell Inspect repository state\ngit status --short\nDo you want to proceed?\n1. Yes",
            ),
            patch.object(watcher, "get_pane_info", return_value=("copilot", r"C:\Repo\crew")),
            patch.object(watcher, "wake_commander") as wake,
        ):
            watcher._main()
            watcher._main()

            speak.assert_called_once_with("herdr", "crew-pane-7", "blocked")
            wake.assert_called_once_with("herdr", "commander-pane", "crew-pane-7", "blocked")

        queue_path = state_dir / "pending-blocks.json"
        self.assertTrue(queue_path.exists())
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(queue["records"]))
        record = queue["records"][0]
        self.assertEqual(1, record["order"])
        self.assertEqual("pending", record["status"])
        self.assertEqual("Crew tab", record["tab"])
        self.assertEqual("crew-pane-7", record["pane_id"])
        self.assertEqual("copilot", record["agent"])
        self.assertEqual(r"C:\Repo\crew", record["cwd"])
        self.assertEqual("git status --short", record["command"])
        self.assertEqual("Do you want to proceed?", record["prompt"])
        self.assertRegex(record["id"], r"^block-\d{4}-\d{4}$")
        self.assertRegex(record["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        blocked_commands = json.loads((state_dir / "blocked-commands.json").read_text(encoding="utf-8"))
        self.assertEqual(1, blocked_commands["records"][0]["count"])
        self.assertEqual("Crew tab", blocked_commands["records"][0]["tab"])
        self.assertEqual(r"C:\Repo\crew", blocked_commands["records"][0]["cwd"])
        self.assertEqual("git status --short", blocked_commands["records"][0]["command"])

        shutil.rmtree(state_dir)

    def test_auto_handled_block_does_not_speak_or_wake_commander(self):
        state_dir = Path(__file__).parent / ".watcher-auto-handled-speak-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_commander_pane": True, "auto_approve_tabs": []}),
            encoding="utf-8",
        )
        event = {"data": {"pane_id": "crew-pane-7", "agent_status": "blocked"}}

        with (
            patch.object(watcher, "MEMORY_DIR", str(state_dir)),
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "DATA_DIR", str(state_dir)),
            patch.dict(os.environ, {"HERDR_PLUGIN_EVENT_JSON": json.dumps(event)}, clear=False),
            patch.object(watcher, "read_commander_pane", return_value="commander-pane"),
            patch.object(watcher, "speak_fleet_update") as speak,
            patch.object(watcher, "get_tab_label", return_value="Crew tab"),
            patch.object(watcher, "try_auto_handle", return_value=(True, "rule-1", "git log", 0.9)),
            patch.object(watcher, "read_pane", return_value=""),
            patch.object(watcher, "log_decision"),
            patch.object(watcher, "wake_commander") as wake,
        ):
            watcher._main()

        speak.assert_not_called()
        wake.assert_not_called()
        shutil.rmtree(state_dir)

    def test_generic_blocked_user_question_is_not_enqueued(self):
        state_dir = Path(__file__).parent / ".watcher-generic-block-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_commander_pane": True, "auto_approve_tabs": []}),
            encoding="utf-8",
        )
        event = {"data": {"pane_id": "crew-pane-7", "agent_status": "blocked"}}

        with (
            patch.object(watcher, "MEMORY_DIR", str(state_dir)),
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "DATA_DIR", str(state_dir)),
            patch.dict(
                os.environ,
                {
                    "HERDR_BIN_PATH": "herdr",
                    "HERDR_PLUGIN_EVENT_JSON": json.dumps(event),
                },
                clear=False,
            ),
            patch.object(watcher, "read_commander_pane", return_value="commander-pane"),
            patch.object(watcher, "speak_fleet_update"),
            patch.object(watcher, "get_tab_label", return_value="Crew tab"),
            patch.object(watcher, "try_auto_handle", return_value=(False, "none", "", 0)),
            patch.object(
                watcher,
                "read_pane",
                return_value="What should I implement next?\n1. Add tests\n2. Stop",
            ),
            patch.object(watcher, "get_pane_info", return_value=("copilot", r"C:\Repo\crew")),
            patch.object(watcher, "wake_commander"),
        ):
            watcher._main()

        self.assertFalse((state_dir / "pending-blocks.json").exists())
        self.assertFalse((state_dir / "blocked-commands.json").exists())
        self.assertFalse((state_dir / "decisions-log.jsonl").exists())
        shutil.rmtree(state_dir)

    def test_auto_approve_tab_does_not_answer_generic_user_question(self):
        state_dir = Path(__file__).parent / ".watcher-auto-approve-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_tabs": ["Crew tab"]}),
            encoding="utf-8",
        )

        with (
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(
                watcher,
                "read_pane",
                return_value="What should I implement next?\n1. Add tests\n2. Stop",
            ),
            patch.object(watcher.subprocess, "run") as run,
        ):
            handled, rule_id, _, _ = watcher.try_auto_handle(
                "herdr", "crew-pane-7", "Crew tab"
            )

        self.assertFalse(handled)
        self.assertEqual("none", rule_id)
        run.assert_not_called()
        shutil.rmtree(state_dir)

    def test_self_approve_also_handles_blocked_review_tab(self):
        state_dir = Path(__file__).parent / ".watcher-blocked-review-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_commander_pane": True}),
            encoding="utf-8",
        )
        event = {"data": {"pane_id": "review-pane-2", "agent_status": "blocked"}}

        with (
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "DATA_DIR", str(state_dir)),
            patch.dict(
                os.environ,
                {
                    "HERDR_BIN_PATH": "herdr",
                    "HERDR_PLUGIN_EVENT_JSON": json.dumps(event),
                },
                clear=False,
            ),
            patch.object(watcher, "read_commander_pane", return_value="commander-pane"),
            patch.object(watcher, "get_tab_label", return_value="Blocked Review"),
            patch.object(
                watcher,
                "read_pane",
                return_value=(
                    "$ Shell Inspect state\n"
                    "git status --short\n"
                    "Do you want to run this command?\n"
                    "1. Yes"
                ),
            ),
            patch.object(watcher, "log_decision"),
            patch.object(watcher, "speak_fleet_update") as speak,
            patch.object(watcher, "try_auto_handle") as auto_handle,
            patch.object(watcher.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            watcher._main()

        self.assertEqual(
            ["herdr", "pane", "send-keys", "review-pane-2", "enter"],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(
            ["herdr", "agent", "wait", "review-pane-2", "--status", "working", "--timeout", "5000"],
            run.call_args_list[1].args[0],
        )
        speak.assert_not_called()
        auto_handle.assert_not_called()
        shutil.rmtree(state_dir)

    def test_get_pane_info_prefers_foreground_cwd(self):
        result = type("Result", (), {
            "stdout": json.dumps({
                "result": {
                    "pane": {
                        "agent": "copilot",
                        "cwd": r"C:\frozen",
                        "foreground_cwd": r"C:\live",
                    }
                }
            })
        })()

        with patch.object(watcher.subprocess, "run", return_value=result):
            agent, cwd = watcher.get_pane_info("herdr", "pane-1")

        self.assertEqual("copilot", agent)
        self.assertEqual(r"C:\live", cwd)

    def test_auto_approve_skips_duplicate_tab_labels(self):
        state_dir = Path(__file__).parent / ".watcher-dup-tab-state"
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir()
        (state_dir / "config.json").write_text(
            json.dumps({"auto_approve_tabs": ["Crew tab"]}),
            encoding="utf-8",
        )
        pane_output = (
            "$ Shell Inspect state\n"
            "git status --short\n"
            "Do you want to run this command?\n"
            "1. Yes"
        )

        with (
            patch.object(watcher, "STATE_DIR", str(state_dir)),
            patch.object(watcher, "load_rules", return_value=[]),
            patch.object(watcher, "read_pane", return_value=pane_output),
            patch.object(watcher, "tab_label_is_unique", return_value=False),
            patch.object(watcher, "get_pane_info", return_value=("*", "")),
            patch.object(watcher.subprocess, "run") as run,
        ):
            handled, rule_id, _, _ = watcher.try_auto_handle(
                "herdr", "crew-pane-7", "Crew tab"
            )

        self.assertFalse(handled)
        self.assertEqual("none", rule_id)
        run.assert_not_called()
        shutil.rmtree(state_dir)

    def test_shell_header_makes_marked_yes_prompt_actionable(self):
        pane_output = (
            "$ Shell Inspect repository state\n"
            "git status --short\n"
            "? 1. Yes"
        )

        self.assertTrue(watcher._is_shell_approval_block(pane_output))


if __name__ == "__main__":
    unittest.main()
