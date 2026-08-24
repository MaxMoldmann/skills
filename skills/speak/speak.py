#!/usr/bin/env python3
"""
Speak Skill - Local TTS for AI Agents
"""

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

# Cached TTS assets are sufficient; callers can set this to "0" to permit Hub access.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

try:
    from kokoro import KPipeline
    import soundfile as sf
    import numpy as np
except ImportError:
    print("❌ Missing dependencies. Run:")
    print("   pip install kokoro soundfile numpy")
    sys.exit(1)

@contextlib.contextmanager
def _silence():
    devnull = open(os.devnull, "w")
    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        yield
    devnull.close()

# Common voice presets (you can add more)
VOICES = {
    "af_bella": "af_bella",      # Warm female
    "af_sarah": "af_sarah",      # Clear female
    "am_adam": "am_adam",        # Deep male
    "am_michael": "am_michael",  # Friendly male
    "bf_emma": "bf_emma",
    "bm_george": "bm_george",
    # Add more from Kokoro as needed
}
CONFIG_PATH = Path(__file__).with_name("config.json")

def configured_voice():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["voice"]

def list_voices():
    print("Available voices:")
    for name in sorted(VOICES.keys()):
        print(f"  • {name}")

def speak(text: str, voice: str = "af_bella", output: str = None, play: bool = True):
    if voice not in VOICES:
        print(f"⚠️ Voice '{voice}' not found. Using af_bella instead.")
        voice = "af_bella"

    with _silence():
        pipeline = KPipeline(lang_code=voice[0])  # 'a' for American, 'b' for British

    audio_segments = []
    with _silence():
        for i, (gs, ps, audio) in enumerate(pipeline(text, voice=VOICES[voice], speed=1.0)):
            audio_segments.append(audio)

    full_audio = np.concatenate(audio_segments)

    # Save file only if explicitly requested
    if output is not None:
        if not output.endswith(('.wav', '.mp3')):
            output += ".wav"
        sf.write(output, full_audio, 24000)
        print(f"Saved: {output}")

    # Simple playback
    if play:
        try:
            import sounddevice as sd
            sd.play(full_audio, 24000)
            sd.wait()
        except ImportError:
            print("   (Install sounddevice for auto-playback: pip install sounddevice)")

    return output


REFERENCE_DIRECTORY = Path(__file__).parent / "reference"
GREETING_WAV = REFERENCE_DIRECTORY / "speak-captain-ready.wav"
ENABLED_WAV = REFERENCE_DIRECTORY / "speak-summaries-enabled.wav"

def play_wav(path: Path):
    try:
        import sounddevice as sd
        data, samplerate = sf.read(str(path))
        sd.play(data, samplerate)
        sd.wait()
    except ImportError:
        print("   (Install sounddevice for auto-playback: pip install sounddevice)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Speak Skill - Local TTS")
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("--voice", "-v", help="Voice to use")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--list-voices", "-l", action="store_true", help="List available voices")
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="Play the pre-generated spoken-summaries-enabled confirmation",
    )

    args = parser.parse_args(argv)

    if args.list_voices:
        list_voices()
    elif args.enabled:
        print("Spoken summaries enabled.")
        play_wav(ENABLED_WAV)
    elif args.text:
        speak(args.text, args.voice or configured_voice(), args.output)
    else:
        print("Captain! I'm ready.")
        if GREETING_WAV.exists():
            play_wav(GREETING_WAV)
        else:
            speak("Captain! I'm ready.", args.voice or configured_voice(), args.output)


if __name__ == "__main__":
    main()