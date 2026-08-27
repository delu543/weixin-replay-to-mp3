from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_mp3_studio import jobs


class WindowsAtomicStatusTests(unittest.TestCase):
    def test_replace_retries_a_transient_windows_reader_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / ".status.json.test.tmp"
            target = root / "status.json"
            source.write_text("new", encoding="ascii")
            target.write_text("old", encoding="ascii")
            original_replace = Path.replace
            attempts = 0

            def transient_lock(path: Path, destination: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError(13, "simulated Windows sharing violation")
                return original_replace(path, destination)

            with patch.object(Path, "replace", autospec=True, side_effect=transient_lock), patch(
                "replay_mp3_studio.jobs.time.sleep"
            ) as sleep:
                jobs._replace_with_bounded_retry(source, target)

            self.assertEqual(attempts, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(target.read_text(encoding="ascii"), "new")

    def test_replace_fails_closed_after_the_bounded_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / ".status.json.test.tmp"
            source.write_text("new", encoding="ascii")
            with patch.object(Path, "replace", side_effect=PermissionError("locked")), patch(
                "replay_mp3_studio.jobs.time.sleep"
            ) as sleep:
                with self.assertRaises(PermissionError):
                    jobs._replace_with_bounded_retry(source, Path(temporary) / "status.json")
            self.assertEqual(sleep.call_count, len(jobs.WINDOWS_REPLACE_RETRY_DELAYS))


if __name__ == "__main__":
    unittest.main()
