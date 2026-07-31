from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_mp3_studio.extractors import (
    capture_weixin_causal_playback_delta,
    changed_weixin_recent_source_files,
    convert_weixin_frozen_playback_delta,
    filter_weixin_marker_report_to_baseline,
    run_weixin_link,
    run_weixin_causal_playback_capture,
    run_weixin_manual_playback_capture,
    snapshot_weixin_recent_source_state,
)
from replay_mp3_studio.weixin_pipeline_state import (
    load_or_create_pipeline_state,
    mark_pipeline_phase_complete,
)


class WeixinCausalCaptureTests(unittest.TestCase):
    def test_runtime_snapshot_excludes_sensitive_paths_and_detects_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "profiles" / "multitab" / "Local Storage" / "leveldb" / "001.log"
            safe.parent.mkdir(parents=True)
            safe.write_text("before", encoding="utf-8")
            sensitive = root / "profiles" / "multitab" / "History"
            sensitive.write_text("private", encoding="utf-8")

            baseline = snapshot_weixin_recent_source_state(runtime_roots=(root,))
            self.assertIn(str(safe.resolve()), baseline)
            self.assertNotIn(str(sensitive.resolve()), baseline)

            time.sleep(0.002)
            safe.write_text("after-change", encoding="utf-8")
            created = root / "net" / "kvcomm" / "fresh.statistic"
            created.parent.mkdir(parents=True)
            created.write_text("fresh", encoding="utf-8")
            changed = changed_weixin_recent_source_files(baseline, runtime_roots=(root,))

            self.assertEqual({path.resolve() for path in changed}, {safe.resolve(), created.resolve()})

    def test_marker_report_is_reduced_to_files_changed_after_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.log"
            old.write_text("old", encoding="utf-8")
            fresh = root / "Share Data"
            fresh.write_text("fresh", encoding="utf-8")
            old_stat = old.stat()
            baseline = {str(old.resolve()): (old_stat.st_size, old_stat.st_mtime_ns)}
            report = root / "marker.json"
            report.write_text(
                json.dumps(
                    {
                        "files_with_hits": [
                            {
                                "path": str(old),
                                "mtime": old_stat.st_mtime,
                                "urls": ["https://finder.video.qq.com/old/stodownload?a=1"],
                                "redacted_urls": ["https://finder.video.qq.com/old/stodownload?<redacted>"],
                            },
                            {
                                "path": str(fresh),
                                "mtime": fresh.stat().st_mtime,
                                "urls": ["https://finder.video.qq.com/fresh/stodownload?a=2"],
                                "redacted_urls": ["https://finder.video.qq.com/fresh/stodownload?<redacted>"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            summary = filter_weixin_marker_report_to_baseline(report, baseline, started_at=time.time() - 1)
            payload = json.loads(report.read_text(encoding="utf-8"))

            self.assertEqual(summary["fresh_file_with_hits_count"], 1)
            self.assertEqual(summary["fresh_candidate_url_count"], 1)
            self.assertTrue(summary["share_data_changed"])
            self.assertIn("/fresh/", payload["candidate_urls"][0])

    def test_capture_phase_freezes_increment_without_network_probe_or_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            changed = root / "fresh.statistic"
            changed.write_text("fresh", encoding="utf-8")
            frozen = root / "frozen.statistic"
            frozen.write_text("frozen", encoding="utf-8")

            with patch(
                "replay_mp3_studio.extractors.changed_weixin_recent_source_files",
                return_value=[changed],
            ), patch(
                "replay_mp3_studio.extractors.snapshot_weixin_probe_sources",
                return_value=[frozen],
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_encrypted_candidate_probe_for_sources",
                side_effect=AssertionError("capture phase must not probe the network"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=AssertionError("capture phase must not download or convert"),
            ):
                stage = capture_weixin_causal_playback_delta(
                    artifacts,
                    lambda _message: None,
                    baseline={},
                    started_at=time.time(),
                    wait_seconds=1,
                    playback_assertions={"playback_verified": True},
                )

            self.assertTrue(stage["success"])
            self.assertEqual(stage["phase"], "capture_increment_only")
            self.assertFalse(stage["network_probe_started"])
            self.assertFalse(stage["download_started"])
            self.assertEqual(stage["snapshot_paths"], [str(frozen)])

    def test_conversion_phase_uses_only_frozen_snapshots_and_propagates_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            frozen = root / "frozen.statistic"
            frozen.write_text("frozen", encoding="utf-8")
            numeric = root / "numeric.json"
            numeric.write_text('{"pairs":[]}', encoding="utf-8")
            output = root / "output.mp3"
            captured: dict[str, object] = {}

            def fake_probe(paths, _artifacts, _log, **_kwargs):
                captured["probe_paths"] = list(paths)
                return {
                    "result": "mp4_header_decrypted",
                    "candidate_url_count": 3,
                    "successful_numeric_pair_count": 1,
                    "numeric_key_pair_artifact": str(numeric),
                }

            def fake_vendor(source, output_path, _artifacts, _log, **kwargs):
                captured["vendor_source"] = Path(source)
                captured["min_duration"] = kwargs.get("min_duration")
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_encrypted_candidate_probe_for_sources",
                side_effect=fake_probe,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ):
                stage = convert_weixin_frozen_playback_delta(
                    output,
                    artifacts,
                    lambda _message: None,
                    capture_stage={
                        "success": True,
                        "snapshot_file_count": 1,
                        "snapshot_paths": [str(frozen)],
                    },
                    min_duration=0,
                )

            self.assertTrue(stage["success"])
            self.assertEqual(captured["probe_paths"], [frozen])
            self.assertEqual(captured["vendor_source"], numeric)
            self.assertEqual(captured["min_duration"], 0)
            self.assertTrue(output.exists())

    def test_causal_orchestrator_checkpoints_and_reuses_frozen_increment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "output.mp3"
            frozen = root / "frozen.statistic"
            frozen.write_text("frozen", encoding="utf-8")
            capture_calls = []

            def capture(*_args, **_kwargs):
                capture_calls.append("capture")
                return {
                    "success": True,
                    "playback_evidence": True,
                    "share_data_changed": False,
                    "fresh_changed_file_count": 1,
                    "snapshot_file_count": 1,
                    "snapshot_paths": [str(frozen)],
                }

            with patch(
                "replay_mp3_studio.extractors.capture_weixin_causal_playback_delta",
                side_effect=capture,
            ), patch(
                "replay_mp3_studio.extractors.convert_weixin_frozen_playback_delta",
                return_value={"success": False, "error": "interrupted_after_capture"},
            ):
                first = run_weixin_causal_playback_capture(
                    output,
                    artifacts,
                    lambda _message: None,
                    baseline={},
                    started_at=time.time(),
                    wait_seconds=1,
                    min_duration=0,
                    playback_assertions={"playback_verified": True},
                    target_short_uri="A1TN6kx8js",
                )
                second = run_weixin_causal_playback_capture(
                    output,
                    artifacts,
                    lambda _message: None,
                    baseline={},
                    started_at=time.time(),
                    wait_seconds=1,
                    min_duration=0,
                    playback_assertions={"playback_verified": True},
                    target_short_uri="A1TN6kx8js",
                )

            self.assertFalse(first["checkpoint_reused"])
            self.assertTrue(second["checkpoint_reused"])
            self.assertTrue(second["capture_phase"]["resumed_from_checkpoint"])
            self.assertEqual(capture_calls, ["capture"])

    def test_causal_checkpoint_is_not_reused_for_a_different_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "output.mp3"
            frozen = root / "frozen.statistic"
            frozen.write_text("frozen", encoding="utf-8")
            calls = []

            def capture(*_args, **_kwargs):
                calls.append("capture")
                return {
                    "success": True,
                    "playback_evidence": True,
                    "snapshot_file_count": 1,
                    "snapshot_paths": [str(frozen)],
                }

            with patch(
                "replay_mp3_studio.extractors.capture_weixin_causal_playback_delta",
                side_effect=capture,
            ), patch(
                "replay_mp3_studio.extractors.convert_weixin_frozen_playback_delta",
                return_value={"success": False},
            ):
                for short_uri in ("first", "second"):
                    run_weixin_causal_playback_capture(
                        output,
                        artifacts,
                        lambda _message: None,
                        baseline={},
                        started_at=time.time(),
                        wait_seconds=1,
                        min_duration=0,
                        target_short_uri=short_uri,
                    )

            self.assertEqual(calls, ["capture", "capture"])

    def test_manual_capture_probes_the_marker_report_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            artifacts.mkdir()
            marker = artifacts / "marker.json"
            marker.write_text(
                json.dumps({"candidate_url_count": 1, "files_with_hits": []}),
                encoding="utf-8",
            )
            numeric = root / "numeric.json"
            numeric.write_text('{"pairs":[]}', encoding="utf-8")
            captured: dict[str, object] = {}

            def fake_probe(paths, _artifacts, _log, **_kwargs):
                captured["paths"] = list(paths)
                return {
                    "result": "mp4_header_decrypted",
                    "successful_numeric_pair_count": 1,
                    "numeric_key_pair_artifact": str(numeric),
                }

            def fake_vendor(_source, output_path, _artifacts, _log, **_kwargs):
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_recent_marker_scan",
                return_value=marker,
            ), patch(
                "replay_mp3_studio.extractors.build_weixin_recent_source_file_list",
                return_value=[],
            ), patch(
                "replay_mp3_studio.extractors.snapshot_weixin_probe_sources",
                side_effect=lambda paths, **_kwargs: list(paths),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_encrypted_candidate_probe_for_sources",
                side_effect=fake_probe,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ):
                stage = run_weixin_manual_playback_capture(
                    output,
                    artifacts,
                    lambda _message: None,
                    min_duration=3600,
                )

            self.assertTrue(stage["success"])
            self.assertEqual(captured["paths"], [marker])

    def test_link_baselines_before_open_and_stops_without_fresh_playback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            calls: list[str] = []

            def baseline():
                calls.append("baseline")
                return {}

            def open_target(*_args, **_kwargs):
                calls.append("open")
                return {"method": "weixin_scheme_capture_fallback", "short_uri": "AFfTIp5Ywj"}

            def causal(*_args, **_kwargs):
                calls.append("causal")
                return {
                    "name": "causal_playback_runtime_delta",
                    "attempted": True,
                    "success": False,
                    "playback_evidence": False,
                    "fresh_candidate_url_count": 0,
                }

            with patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                return_value={"name": "source_vault_artifact", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                return_value={"packet": {}, "packet_dir": str(root / "packet")},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                return_value={"name": "direct_link_provider_probe", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.snapshot_weixin_recent_source_state",
                side_effect=baseline,
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=open_target,
            ), patch(
                "replay_mp3_studio.extractors.trigger_weixin_video_playback",
                return_value={
                    "video_window_visible": True,
                    "playing_audio": True,
                    "video_wake_lock": True,
                    "playback_verified": True,
                    "activation_method": "autoplay",
                },
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_post_open_source_vault_artifact",
                return_value={"name": "post_open_source_vault_artifact", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_causal_playback_capture",
                side_effect=causal,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_radium_source",
                side_effect=AssertionError("stale Radium fallback must not run"),
            ):
                with self.assertRaisesRegex(RuntimeError, "playback did not start"):
                    run_weixin_link(
                        "https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output,
                        artifacts,
                        lambda _message: None,
                    )

            self.assertEqual(calls, ["baseline", "open", "causal"])

    def test_link_resume_from_frozen_increment_skips_network_ui_and_new_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            url = "https://weixin.qq.com/sph/A1TN6kx8js"
            state_path, state = load_or_create_pipeline_state(
                artifacts,
                url=url,
                mode="open_then_watch",
            )
            for phase in (
                "source_vault_checked",
                "direct_probe_checked",
                "target_opened",
                "playback_verified",
                "causal_capture_complete",
            ):
                mark_pipeline_phase_complete(state_path, state, phase)

            def resume_conversion(*_args, **kwargs):
                self.assertEqual(kwargs["target_short_uri"], "A1TN6kx8js")
                output.write_bytes(b"mp3")
                return {
                    "name": "causal_playback_runtime_delta",
                    "attempted": True,
                    "success": True,
                    "playback_evidence": True,
                    "checkpoint_reused": True,
                    "capture_phase": {
                        "success": True,
                        "snapshot_file_count": 1,
                        "resumed_from_checkpoint": True,
                    },
                }

            with patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                side_effect=AssertionError("completed Source Vault check must not repeat"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                side_effect=AssertionError("completed direct probe must not repeat"),
            ), patch(
                "replay_mp3_studio.extractors.snapshot_weixin_recent_source_state",
                side_effect=AssertionError("frozen conversion must not take a new baseline"),
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=AssertionError("frozen conversion must not reopen WeChat"),
            ), patch(
                "replay_mp3_studio.extractors.trigger_weixin_video_playback",
                side_effect=AssertionError("frozen conversion must not reactivate playback"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_post_open_source_vault_artifact",
                side_effect=AssertionError("frozen conversion must not wait for a new artifact"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_causal_playback_capture",
                side_effect=resume_conversion,
            ) as causal:
                run_weixin_link(url, output, artifacts, lambda _message: None)

            diagnostics = json.loads((artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8"))
            causal.assert_called_once()
            self.assertEqual(diagnostics["resume_action"], "resume_frozen_conversion")
            self.assertTrue(output.exists())

    def test_link_reuses_only_an_existing_output_that_passes_full_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            output.write_bytes(b"existing")
            with patch(
                "replay_mp3_studio.extractors.verify_mp3",
                return_value={"ok": True, "bytes": 8, "duration_seconds": 4767.05},
            ) as verify, patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                side_effect=AssertionError("verified output must skip Source Vault"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                side_effect=AssertionError("verified output must skip direct probe"),
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=AssertionError("verified output must skip WeChat"),
            ):
                run_weixin_link(
                    "https://weixin.qq.com/sph/A1TN6kx8js",
                    output,
                    artifacts,
                    lambda _message: None,
                    min_duration=3600,
                )

            verify.assert_called_once()
            state = json.loads((artifacts / "weixin_pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "completed")
            self.assertIn("output_verified", state["completed_phases"])

    def test_link_preserves_and_rejects_an_invalid_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            output.write_bytes(b"broken")
            with patch(
                "replay_mp3_studio.extractors.verify_mp3",
                side_effect=RuntimeError("decode failed"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                side_effect=AssertionError("invalid existing output must not be overwritten"),
            ):
                with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                    run_weixin_link(
                        "https://weixin.qq.com/sph/A1TN6kx8js",
                        output,
                        artifacts,
                        lambda _message: None,
                    )

            self.assertEqual(output.read_bytes(), b"broken")

    def test_fresh_evidence_uses_bounded_fallback_and_propagates_duration_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            captured: dict[str, object] = {}

            def radium(*_args, **kwargs):
                captured["radium"] = kwargs
                raise RuntimeError("not found")

            def profile(_output, _artifacts, _log, **kwargs):
                captured["profile"] = kwargs
                output.write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                return_value={"name": "source_vault_artifact", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                return_value={"packet": {}, "packet_dir": str(root / "packet")},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                return_value={"name": "direct_link_provider_probe", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.snapshot_weixin_recent_source_state",
                return_value={},
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                return_value={"method": "file_transfer_assistant", "short_uri": "AFfTIp5Ywj"},
            ), patch(
                "replay_mp3_studio.extractors.trigger_weixin_video_playback",
                return_value={
                    "video_window_visible": True,
                    "playing_audio": True,
                    "video_wake_lock": True,
                    "playback_verified": True,
                    "activation_method": "metadata_guided_canvas_click",
                },
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_post_open_source_vault_artifact",
                return_value={"name": "post_open_source_vault_artifact", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_causal_playback_capture",
                return_value={
                    "name": "causal_playback_runtime_delta",
                    "attempted": True,
                    "success": False,
                    "playback_evidence": True,
                    "share_data_changed": False,
                },
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_radium_source",
                side_effect=radium,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_profile_state_source",
                side_effect=profile,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_sharedata_feed",
                side_effect=AssertionError("unchanged Share Data must be skipped"),
            ):
                run_weixin_link(
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output,
                    artifacts,
                    lambda _message: None,
                    duration=90,
                    min_duration=3600,
                )

            self.assertEqual(captured["radium"]["duration"], 15)
            self.assertEqual(captured["radium"]["min_duration"], 3600)
            self.assertEqual(captured["profile"]["duration"], 15)
            self.assertEqual(captured["profile"]["min_duration"], 3600)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
