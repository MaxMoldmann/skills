import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIRECTORY = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("speak", SKILL_DIRECTORY / "speak.py")
speak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(speak)


class SpeakEnabledConfirmationTests(unittest.TestCase):
    def test_enabled_mode_plays_bundled_confirmation_without_synthesis(self):
        self.assertTrue(speak.ENABLED_WAV.is_file())

        with (
            patch.object(speak, "play_wav") as play_wav,
            patch.object(speak, "speak") as synthesize,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            speak.main(["--enabled"])

        self.assertEqual("Spoken summaries enabled.\n", output.getvalue())
        play_wav.assert_called_once_with(speak.ENABLED_WAV)
        synthesize.assert_not_called()


class VoiceConfigurationTests(unittest.TestCase):
    def test_uses_configured_voice_when_voice_flag_is_omitted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(json.dumps({"voice": "af_sarah"}), encoding="utf-8")

            with (
                patch.object(speak, "CONFIG_PATH", config_path),
                patch.object(speak, "speak") as synthesize,
            ):
                speak.main(["Hello"])

        synthesize.assert_called_once_with("Hello", "af_sarah", None)

    def test_voice_flag_overrides_configured_voice(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(json.dumps({"voice": "af_sarah"}), encoding="utf-8")

            with (
                patch.object(speak, "CONFIG_PATH", config_path),
                patch.object(speak, "speak") as synthesize,
            ):
                speak.main(["Hello", "--voice", "am_adam"])

        synthesize.assert_called_once_with("Hello", "am_adam", None)


if __name__ == "__main__":
    unittest.main()
