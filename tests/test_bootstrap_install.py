from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import bootstrap


class BootstrapInstallTests(unittest.TestCase):
    def test_pip_cache_is_bound_to_the_current_user_app_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp) / "current-user-app"
            runtime_root = app_root / "runtime"
            with (
                mock.patch.object(bootstrap, "APP_ROOT", app_root),
                mock.patch.object(bootstrap, "RUNTIME_ROOT", runtime_root),
                mock.patch.object(bootstrap, "installed_ffmpeg", side_effect=["", "private-ffmpeg"]),
                mock.patch.object(
                    bootstrap,
                    "installed_web_tools",
                    side_effect=[
                        {"yt_dlp": "", "deno": ""},
                        {"yt_dlp": "private-yt-dlp", "deno": "private-deno"},
                    ],
                ),
                mock.patch.object(bootstrap.shutil, "which", return_value=None),
                mock.patch.object(bootstrap.subprocess, "run") as run,
                mock.patch.dict(os.environ, {"FFMPEG": ""}, clear=False),
            ):
                result = bootstrap.ensure_ffmpeg(skip_deps=False)

            self.assertEqual(result, "private-ffmpeg")
            self.assertEqual(run.call_count, 2)
            pip_env = run.call_args_list[1].kwargs["env"]
            expected = app_root / "cache" / "pip"
            self.assertEqual(Path(pip_env["PIP_CACHE_DIR"]), expected)
            self.assertTrue(expected.is_dir())


if __name__ == "__main__":
    unittest.main()
