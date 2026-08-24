---
name: speak
description: Convert text to natural spoken audio. Use this skill when the agent needs to output speech, create voiceovers, give spoken responses, or generate audio files. Supports multiple voices and works locally.
---

# Speak / TTS Skill

## Session controls

- `/speak off` — disable spoken summaries for current chat session. Acknowledge in text; do not run TTS.
- `/speak on` — re-enable spoken summaries for current chat session. Run the script
  with `--enabled`; it prints `Spoken summaries enabled.` and plays bundled
  `reference/speak-summaries-enabled.wav` without TTS synthesis.
- Default is on at each new session. These controls do not persist between sessions.

## Response workflow

When invoked as `/speak` with no arguments (startup greeting): run the script with no text argument — it prints `Captain! I'm ready.` to the terminal first, then plays the pre-generated WAV at `reference/speak-captain-ready.wav` (no TTS synthesis, instant playback). The script itself handles the print, so just show its stdout as the visible response.

When a user requests voice summaries:

1. Output the normal terminal response first.
2. Unless `(speak:silent)` is mentioned in the users request.
3. Unless `/speak off` was requested in current session, generate and play a short voice summary, even when the response is only "Done."
4. Use voice configured in `config.json` unless user requests another voice with `--voice`.

**Do not block the main agent on TTS playback.** Use a headless subagent for all speech (see Subagent pattern below).

Do NOT use a bare `python` command — it won't find the required packages. The venv is self-contained.

The script defaults `HF_HUB_OFFLINE=1` before loading Kokoro, so cached model and voice assets run without Hub metadata checks or network access. Set `HF_HUB_OFFLINE=0` before invocation only when Hub access is intentionally needed.

**One-time setup** (to create a venv):
```powershell
uv venv "$env:USERPROFILE\.copilot\skills\speak\.venv" --python 3.14
uv pip install --python "$env:USERPROFILE\.copilot\skills\speak\.venv" kokoro soundfile numpy sounddevice
uv pip install --python "$env:USERPROFILE\.copilot\skills\speak\.venv" "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

## Subagent pattern

TTS synthesis and playback block the process. To keep the main agent free, always offload speech to a headless subagent. A state file at `%TEMP%\speak-agent-id.txt` tracks the running subagent so a new request can interrupt and replace it.

### Steps for the main agent

1. **Stop any running speak subagent** — read `%TEMP%\speak-agent-id.txt` if it exists. If a session ID is found, call `swarm stop` on it, then delete the file.
2. **Spawn a headless subagent** with `spawn_mode: "headless"` and `label: "speak"`. Pass the text and optional `--voice` flag in the prompt (see template below).
3. **Record the new session ID** — write the spawned session ID to `%TEMP%\speak-agent-id.txt`.
4. **Continue** — the main agent proceeds immediately without waiting.

### Subagent prompt template

```
Run this exact powershell command and report its stdout when done:

$env:PYTHONUTF8='1'; & "$env:USERPROFILE\.copilot\skills\speak\.venv\Scripts\python.exe" "$env:USERPROFILE\.copilot\skills\speak\speak.py" "<TEXT HERE>"

Then delete the file %TEMP%\speak-agent-id.txt if it exists.
```

Replace `<TEXT HERE>` with the summary text (escape double-quotes as `\"`). Append `--voice <name>` after the script path when a specific voice is requested.

### Interrupt semantics

Stopping the old subagent kills the speak script mid-playback, cutting audio immediately. This is intentional — the user hears the latest output rather than a queue of stale ones.

## Usage reference
Direct script invocation (for setup testing or one-off use without a subagent):

```powershell
# Basic usage
$env:PYTHONUTF8='1'; & "$env:USERPROFILE\.copilot\skills\speak\.venv\Scripts\python.exe" "$env:USERPROFILE\.copilot\skills\speak\speak.py" "Your text here"

# With specific voice (overrides config.json for one invocation)
$env:PYTHONUTF8='1'; & "$env:USERPROFILE\.copilot\skills\speak\.venv\Scripts\python.exe" "$env:USERPROFILE\.copilot\skills\speak\speak.py" "Hello, I am Copilot" --voice af_bella

# List available voices
& "$env:USERPROFILE\.copilot\skills\speak\.venv\Scripts\python.exe" "$env:USERPROFILE\.copilot\skills\speak\speak.py" --list-voices

# Play pre-generated "/speak on" confirmation
& "$env:USERPROFILE\.copilot\skills\speak\.venv\Scripts\python.exe" "$env:USERPROFILE\.copilot\skills\speak\speak.py" --enabled
```
