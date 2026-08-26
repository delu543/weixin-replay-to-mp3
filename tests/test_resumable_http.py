from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from replay_mp3_studio import resumable_http
from replay_mp3_studio.resumable_http import (
    RangeUnsupportedError,
    download_by_ranges,
)


class ResumableHttpTests(unittest.TestCase):
    def test_parallel_ranges_reassemble_capped_responses_without_leaking_url(self) -> None:
        payload = bytes(range(256)) * 4
        lock = threading.Lock()
        active = 0
        max_active = 0

        def reader(_url: str, start: int, end: int, _timeout: int):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.004)
            with lock:
                active -= 1
            actual_end = min(end, start + 23)
            return payload[start : actual_end + 1], 206, len(payload)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "video.mp4"
            result = download_by_ranges(
                "https://example.test/video?token=secret",
                target,
                expected_size=len(payload),
                range_reader=reader,
                workers=4,
                chunk_size=128,
            )
            state = json.loads(
                target.with_name(f"{target.name}.ranges.json").read_text(encoding="utf-8")
            )
            downloaded = target.read_bytes()

        self.assertEqual(downloaded, payload)
        self.assertGreater(max_active, 1)
        self.assertEqual(result["downloaded_bytes"], len(payload))
        self.assertNotIn("token", json.dumps(state))
        self.assertNotIn("secret", json.dumps(state))

    def test_legacy_part_is_validated_and_reused(self) -> None:
        payload = b"abcdefghijklmnopqrstuvwxyz" * 20

        def reader(_url: str, start: int, end: int, _timeout: int):
            return payload[start : end + 1], 206, len(payload)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "video.mp4"
            prefix = target.with_name(f"{target.name}.part")
            prefix.write_bytes(payload[:180])
            result = download_by_ranges(
                "https://example.test/video",
                target,
                expected_size=len(payload),
                range_reader=reader,
                workers=2,
                chunk_size=100,
            )
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(result["reused_bytes"], 180)
            self.assertEqual(result["downloaded_bytes"], len(payload) - 180)
            self.assertEqual(prefix.read_bytes(), payload[:180])

    def test_windows_seek_write_fallback_reassembles_parallel_ranges(self) -> None:
        payload = bytes(range(251)) * 8

        def reader(_url: str, start: int, end: int, _timeout: int):
            actual_end = min(end, start + 37)
            return payload[start : actual_end + 1], 206, len(payload)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "video.mp4"
            with mock.patch.object(resumable_http, "_PWRITE", None):
                result = download_by_ranges(
                    "https://example.test/video",
                    target,
                    expected_size=len(payload),
                    range_reader=reader,
                    workers=4,
                    chunk_size=128,
                )
            downloaded = target.read_bytes()

        self.assertEqual(downloaded, payload)
        self.assertEqual(result["downloaded_bytes"], len(payload))

    def test_failed_range_keeps_completed_chunks_for_next_run(self) -> None:
        payload = bytes(range(128))

        def flaky_reader(_url: str, start: int, end: int, _timeout: int):
            if start == 64:
                raise TimeoutError("synthetic timeout")
            return payload[start : end + 1], 206, len(payload)

        def good_reader(_url: str, start: int, end: int, _timeout: int):
            return payload[start : end + 1], 206, len(payload)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "video.mp4"
            with self.assertRaisesRegex(RuntimeError, "failed after"):
                download_by_ranges(
                    "https://example.test/video",
                    target,
                    expected_size=len(payload),
                    range_reader=flaky_reader,
                    workers=1,
                    chunk_size=32,
                    max_retries=2,
                )
            result = download_by_ranges(
                "https://example.test/video",
                target,
                expected_size=len(payload),
                range_reader=good_reader,
                workers=1,
                chunk_size=32,
            )
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(result["reused_bytes"], 96)
            self.assertEqual(result["downloaded_bytes"], 32)

    def test_range_unsupported_fails_closed_for_stream_fallback(self) -> None:
        def reader(_url: str, _start: int, _end: int, _timeout: int):
            return b"all", 200, 3

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RangeUnsupportedError):
                download_by_ranges(
                    "https://example.test/video",
                    Path(tmp) / "video.mp4",
                    expected_size=16,
                    range_reader=reader,
                    workers=1,
                    chunk_size=8,
                )


if __name__ == "__main__":
    unittest.main()
