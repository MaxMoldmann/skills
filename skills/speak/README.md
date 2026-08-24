# Speak Skill

Local Kokoro text-to-speech for agent responses.

## Default Voice Configuration

`config.json` selects voice used when `--voice` is omitted:

```json
{
  "voice": "af_bella"
}
```

Set `voice` to any ID in Supported Voices. A `--voice` argument overrides this
setting for one invocation.

## Supported Voices

`speak.py` accepts these voice IDs. Any other ID falls back to `af_bella`.

| Voice ID | Accent | Voice |
| --- | --- | --- |
| `af_bella` | American English | Female, warm. Default. |
| `af_sarah` | American English | Female, clear. |
| `am_adam` | American English | Male, deep. |
| `am_michael` | American English | Male, friendly. |
| `bf_emma` | British English | Female. |
| `bm_george` | British English | Male. |

## Usage

```powershell
$env:PYTHONUTF8='1'
& "$env:USERPROFILE\.claude\skills\speak\.venv\Scripts\python.exe" `
  "$env:USERPROFILE\.claude\skills\speak\speak.py" `
  "Hello, Captain." --voice af_bella
```

List configured voices:

```powershell
& "$env:USERPROFILE\.claude\skills\speak\.venv\Scripts\python.exe" `
  "$env:USERPROFILE\.claude\skills\speak\speak.py" --list-voices
```
