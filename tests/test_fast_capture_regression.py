import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hour_fast_capture_regression.py"
spec = importlib.util.spec_from_file_location("hour_fast_capture_regression", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class HourFastCaptureRegressionTests(unittest.TestCase):
    def test_time_model_shows_8x_shortens_one_hour_capture(self) -> None:
        model = module.build_time_model(source_duration_seconds=3600, speed=8)

        self.assertEqual(model["source_duration_seconds"], 3600)
        self.assertEqual(model["requested_speed"], 8)
        self.assertEqual(model["expected_record_wall_seconds"], 450)
        self.assertEqual(model["official_3x_wall_seconds"], 1200)
        self.assertEqual(model["expected_saved_vs_3x_seconds"], 750)

    def test_page_html_uses_only_local_audio_source(self) -> None:
        html = module.local_audio_page_html("source.mp3")

        self.assertIn("<audio", html)
        self.assertIn("source.mp3", html)
        self.assertIn("controls", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_capture_command_uses_existing_web_fast_capture_and_restart(self) -> None:
        command = module.build_capture_command(
            python_exe="/tmp/python",
            url="file:///tmp/page.html",
            output=Path("/tmp/out.mp3"),
            raw_output=Path("/tmp/out.fast.webm"),
            profile_dir=Path("/tmp/profile"),
            speed=8,
            max_wall_seconds=480,
        )

        self.assertEqual(command[0], "/tmp/python")
        self.assertIn("web_fast_capture.py", command[1])
        self.assertIn("--rate", command)
        self.assertEqual(command[command.index("--rate") + 1], "8")
        self.assertIn("--restart-media", command)
        self.assertIn("--headless", command)
        self.assertIn("--max-wall-seconds", command)
        self.assertEqual(command[command.index("--max-wall-seconds") + 1], "480")


if __name__ == "__main__":
    unittest.main()
