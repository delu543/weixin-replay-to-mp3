from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from replay_mp3_studio.fast_pipeline import (
    REQUIRED_REPORT_QUESTIONS,
    AutoPipelineOptions,
    complete_min_duration_seconds,
    estimate_wall_clock_model,
    extract_weixin_decode_key_pairs,
    evaluate_timeline_seek_strategy,
    plan_blackbox_segments,
    plan_auto_routes,
    redact_sensitive_text,
    redacted_decode_key_pair_summary,
    render_report_markdown,
    run_auto_pipeline,
    safe_wx_channels_download_config,
    summarize_speed_capability_probe,
    summarize_webview_control_channels,
    _numeric_key_pairs_from_source_payload,
    _summarize_current_delta_report,
)


class FastPipelineTests(unittest.TestCase):
    def test_source_capture_orders_numeric_candidates_by_verified_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "numeric-pairs.json"
            artifact.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {"url": "https://example.test/short", "key": 111, "expected_bytes": 1_000},
                            {"url": "https://example.test/full", "key": 222, "expected_bytes": 400_000_000},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            pairs = _numeric_key_pairs_from_source_payload(
                {"numeric_key_pair_artifact": str(artifact)}
            )

        self.assertEqual([pair["key"] for pair in pairs], [222, 111])

    def test_auto_plan_prefers_source_download_before_blackbox_fallback(self) -> None:
        routes = plan_auto_routes("https://weixin.qq.com/sph/AFfTIp5Ywj")

        self.assertEqual(
            [route.name for route in routes],
            [
                "existing_direct_or_artifact",
                "wx_channels_source_download",
                "wx_channels_current_delta_watch",
                "html_media_speed_probe",
                "timeline_seek_probe",
                "segmented_blackbox",
                "blackbox_3x_fallback",
            ],
        )
        self.assertEqual(routes[1].expected_bottleneck, "network_download_decode_ffmpeg")
        self.assertLess(routes[1].expected_min_speedup_over_3x, routes[1].expected_max_speedup_over_3x)
        self.assertEqual(routes[2].expected_bottleneck, "visible_playback_cache_availability")

    def test_sensitive_text_redaction_removes_signed_url_and_key_material(self) -> None:
        raw = (
            "download --url "
            '"https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret&sign=sig" '
            "--key 123456789\n"
            "-----BEGIN " + "PRIVATE KEY-----\nsecret\n-----END " + "PRIVATE KEY-----"
        )

        redacted = redact_sensitive_text(raw)

        self.assertIn("stodownload?<redacted>", redacted)
        self.assertNotIn("token=secret", redacted)
        self.assertNotIn("sign=sig", redacted)
        self.assertNotIn("123456789", redacted)
        self.assertNotIn("PRIVATE KEY", redacted)

    def test_safe_wx_config_disables_tun_pagespy_and_remote_servers(self) -> None:
        config = safe_wx_channels_download_config(
            cert_file="/tmp/codex-local.crt",
            key_file="/tmp/codex-local.key",
            cert_name="CodexLocalWeixinTest",
            port=20233,
            upstream_proxy="http://127.0.0.1:7897",
            skip_install_root_cert=True,
        )

        self.assertIn("file: /tmp/codex-local.crt", config)
        self.assertIn("key: /tmp/codex-local.key", config)
        self.assertIn("name: CodexLocalWeixinTest", config)
        self.assertIn("hostname: 127.0.0.1", config)
        self.assertIn("port: 20233", config)
        self.assertIn("tun: false", config)
        self.assertIn("skipInstallRootCert: true", config)
        self.assertIn('upstreamProxy: "http://127.0.0.1:7897"', config)
        self.assertIn("enabled: false", config)
        self.assertNotIn("SunnyRoot", config)
        self.assertNotIn("debug.weixin.qq.com", config)

    def test_complete_min_duration_prefers_explicit_threshold_over_declared_duration(self) -> None:
        threshold = complete_min_duration_seconds(
            AutoPipelineOptions(
                url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                output=Path("/tmp/out.mp3"),
                report=Path("/tmp/report.md"),
                work_dir=Path("/tmp/work"),
                duration=3588,
                min_duration_seconds=3000,
            )
        )

        self.assertEqual(threshold, 3000)

    def test_complete_min_duration_uses_declared_duration_with_probe_tolerance(self) -> None:
        threshold = complete_min_duration_seconds(
            AutoPipelineOptions(
                url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                output=Path("/tmp/out.mp3"),
                report=Path("/tmp/report.md"),
                work_dir=Path("/tmp/work"),
                duration=3588,
            )
        )

        self.assertEqual(threshold, 3586.0)

    def test_report_markdown_answers_required_questions(self) -> None:
        report = render_report_markdown(
            {
                "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                "output": "/tmp/out.mp3",
                "mode": "auto",
                "started_at": "2026-06-29T23:10:00+08:00",
                "finished_at": "2026-06-29T23:10:05+08:00",
                "wall_seconds": 5.0,
                "mp3_complete": False,
                "highest_stable_speed": "unverified",
                "limit_point": "not tested yet",
                "routes": [
                    {
                        "name": "wx_channels_source_download",
                        "status": "not_run",
                        "summary": "planned",
                    }
                ],
            }
        )

        for question in REQUIRED_REPORT_QUESTIONS:
            self.assertIn(question, report)
        self.assertIn("wx_channels_source_download", report)
        self.assertNotIn("token=", report)

    def test_report_markdown_includes_segmented_blackbox_manifest(self) -> None:
        report = render_report_markdown(
            {
                "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                "output": "/tmp/out.mp3",
                "mode": "auto",
                "started_at": "2026-06-30T18:00:00+08:00",
                "finished_at": "2026-06-30T18:02:00+08:00",
                "wall_seconds": 120,
                "mp3_complete": True,
                "highest_stable_speed": "3x_requested_segmented",
                "time_model": {
                    "source_duration_seconds": 7200,
                    "confirmed_playback_speed": 3,
                    "playback_wall_seconds": 2400,
                    "serial_segmented_wall_seconds": 2418.5,
                    "pipelined_segmented_wall_seconds": 2400,
                    "saved_vs_serial_segmented_seconds": 18.5,
                    "hard_lower_bound_without_source_seconds": 2400,
                    "saved_explanation": "Pipeline overlaps post-processing with later recording.",
                },
                "routes": [
                    {
                        "name": "segmented_blackbox",
                        "status": "success",
                        "summary": "merged",
                        "manifest": "/tmp/manifest.json",
                        "postprocess_pipeline": {
                            "mode": "raw_capture_then_background_convert",
                            "estimated_saved_vs_serial_segmented_seconds": 18.5,
                        },
                        "resume_plan": {
                            "first_incomplete_segment_index": 2,
                            "reuse_ready_segment_indices": [1],
                            "retry_segment_indices": [2],
                            "same_work_dir_required": "/tmp/work",
                            "same_output_required": "/tmp/out.mp3",
                            "command_template": [
                                "python3",
                                "main.py",
                                "--url",
                                "<same-weixin-url>",
                                "--output",
                                "/tmp/out.mp3",
                                "--work-dir",
                                "/tmp/work",
                            ],
                        },
                        "segments": [
                            {"index": 1, "duration_seconds": 60.0, "status": "success", "output": "/tmp/p1.mp3"},
                            {"index": 2, "duration_seconds": 30.0, "status": "success", "output": "/tmp/p2.mp3"},
                        ],
                    }
                ],
            }
        )

        self.assertIn("## Segmented Blackbox Evidence", report)
        self.assertIn("/tmp/manifest.json", report)
        self.assertIn("raw_capture_then_background_convert", report)
        self.assertIn("18.50s", report)
        self.assertIn("## Time Model", report)
        self.assertIn("playback_wall_seconds", report)
        self.assertIn("part 1", report)
        self.assertIn("60.00s", report)
        self.assertIn("Resume plan", report)
        self.assertIn("first incomplete segment: `2`", report)
        self.assertIn("<same-weixin-url>", report)
        self.assertNotIn("AFfTIp5Ywj", report.split("Resume plan", 1)[1])

    def test_report_markdown_includes_speed_control_probe_details(self) -> None:
        report = render_report_markdown(
            {
                "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                "output": "/tmp/out.mp3",
                "mode": "auto",
                "routes": [
                    {
                        "name": "html_media_speed_probe",
                        "status": "completed",
                        "summary": "Observed playback stack desktop_wechat_wxplayer_libvlc",
                        "probe": {
                            "player_stack": "desktop_wechat_wxplayer_libvlc",
                            "safe_control_channel": "none_verified",
                            "libvlc_set_rate_symbol": True,
                            "control_probe": {
                                "remote_debugging_flags": ["--remote-debugging-pipe"],
                                "candidate_debug_ports": [],
                                "safe_webview_control_channel": "none_verified",
                                "limit_point": "wechat_webview_cdp_not_exposed",
                            },
                            "actual_timeline_probe": {
                                "status": "not_run",
                                "reason": "no_safe_page_context_control_channel",
                            },
                        },
                    }
                ],
            }
        )

        self.assertIn("## Speed Control Probe", report)
        self.assertIn("- player_stack: `desktop_wechat_wxplayer_libvlc`", report)
        self.assertIn("- safe_control_channel: `none_verified`", report)
        self.assertIn("- remote_debugging_flags: `--remote-debugging-pipe`", report)
        self.assertIn("- control_limit_point: `wechat_webview_cdp_not_exposed`", report)
        self.assertIn("- actual_timeline_probe.status: `not_run`", report)
        self.assertIn("- actual_timeline_probe.reason: `no_safe_page_context_control_channel`", report)

    def test_timeline_seek_strategy_rejects_incomplete_audio_sampling(self) -> None:
        probe = evaluate_timeline_seek_strategy(
            source_duration_seconds=7200,
            confirmed_playback_speed=3,
            segment_seconds=600,
            capture_window_seconds=30,
            source_media_access=False,
            safe_fast_seek_control=False,
        )

        self.assertFalse(probe["complete_mp3_possible"])
        self.assertEqual(probe["planned_seek_count"], 12)
        self.assertEqual(probe["sampled_source_seconds"], 360.0)
        self.assertEqual(probe["source_coverage_ratio"], 0.05)
        self.assertEqual(probe["hard_lower_bound_without_source_seconds"], 2400.0)
        self.assertEqual(probe["limit_point"], "seek_burst_captures_discontinuous_audio")

    def test_report_markdown_includes_timeline_seek_probe_details(self) -> None:
        report = render_report_markdown(
            {
                "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                "output": "/tmp/out.mp3",
                "mode": "auto",
                "routes": [
                    {
                        "name": "timeline_seek_probe",
                        "status": "completed",
                        "summary": "Seek-burst sampling is not a complete MP3 route.",
                        "probe": {
                            "complete_mp3_possible": False,
                            "planned_seek_count": 12,
                            "sampled_source_seconds": 360.0,
                            "source_coverage_ratio": 0.05,
                            "hard_lower_bound_without_source_seconds": 2400.0,
                            "limit_point": "seek_burst_captures_discontinuous_audio",
                        },
                    }
                ],
            }
        )

        self.assertIn("## Timeline Seek Probe", report)
        self.assertIn("- complete_mp3_possible: `False`", report)
        self.assertIn("- source_coverage_ratio: `0.05`", report)
        self.assertIn("- limit_point: `seek_burst_captures_discontinuous_audio`", report)

    def test_auto_pipeline_records_route_timing_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    time.sleep(0.01)
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    duration=7200,
                    blackbox_speed=3,
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {},
            )

            ledger = run.get("route_timing_ledger")
            self.assertIsInstance(ledger, list)
            self.assertGreaterEqual(len(ledger), 5)
            direct = next(item for item in ledger if item["name"] == "existing_direct_or_artifact")
            self.assertEqual(direct["status"], "failed")
            self.assertIn("elapsed_seconds", direct)
            self.assertGreater(direct["elapsed_seconds"], 0)
            self.assertIn("evidence_level", direct)
            timeline = next(item for item in ledger if item["name"] == "timeline_seek_probe")
            self.assertEqual(timeline["status"], "completed")
            self.assertEqual(timeline["limit_point"], "seek_burst_captures_discontinuous_audio")
            rendered = report.read_text(encoding="utf-8")
            self.assertIn("## Route Timing Ledger", rendered)
            self.assertIn("existing_direct_or_artifact", rendered)
            self.assertIn("timeline_seek_probe", rendered)

    def test_current_delta_summary_preserves_baseline_unreadable_fd_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "weixin_current_playback_delta.json"
            report_path.write_text(
                json.dumps(
                    {
                        "diagnosis": "playback_fd_unlinked",
                        "baseline_unreadable_media_fd_count": 4,
                        "unreadable_media_fd_event_count": 0,
                        "largest_unreadable_fd_bytes": 4916302,
                        "sample_unreadable_fds": [
                            {
                                "pid": "123",
                                "command": "WeChatAppEx Helper (Renderer)",
                                "fd": "13",
                                "size": 4916302,
                                "relative_path": ".5A4RE8SF68.com.tencent.xinWeChat.ABC",
                            }
                        ],
                        "unreadable_fd_access_probe": {
                            "checked_count": 1,
                            "safe_copy_possible": False,
                            "limit_point": "renderer_fd_has_no_safe_filesystem_alias",
                            "samples": [
                                {
                                    "pid": "123",
                                    "fd": "13",
                                    "original_path_exists": False,
                                    "proc_pid_fd_exists": False,
                                    "dev_fd_pid_scoped_exists": False,
                                    "raw_dev_fd_probe": "not_attempted_not_pid_scoped",
                                }
                            ],
                        },
                        "visible_events": [],
                        "unreadable_lsof": [],
                        "attempts": [],
                        "result": {"error": "no_playable_changed_media_file"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = _summarize_current_delta_report(report_path)

            self.assertEqual(summary["baseline_unreadable_media_fd_count"], 4)
            self.assertEqual(summary["unreadable_media_fd_event_count"], 0)
            self.assertEqual(summary["largest_unreadable_fd_bytes"], 4916302)
            self.assertEqual(summary["sample_unreadable_fds"][0]["fd"], "13")
            self.assertEqual(
                summary["unreadable_fd_access_probe"]["limit_point"],
                "renderer_fd_has_no_safe_filesystem_alias",
            )

            rendered = render_report_markdown(
                {
                    "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    "output": "/tmp/out.mp3",
                    "mode": "auto",
                    "routes": [
                        {
                            "name": "wx_channels_current_delta_watch",
                            "status": "failed",
                            "summary": "Current playback delta watcher did not create a verified MP3.",
                            **summary,
                        }
                    ],
                }
            )

            self.assertIn("baseline_unreadable_media_fd_count", rendered)
            self.assertIn("sample_unreadable_fds", rendered)
            self.assertIn("unreadable_fd_access_probe", rendered)
            self.assertIn("renderer_fd_has_no_safe_filesystem_alias", rendered)
            self.assertIn("4916302", rendered)

    def test_report_markdown_includes_post_capture_rescan_evidence(self) -> None:
        report = render_report_markdown(
            {
                "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                "output": "/tmp/out.mp3",
                "mode": "auto",
                "started_at": "2026-06-30T20:00:00+08:00",
                "finished_at": "2026-06-30T20:01:30+08:00",
                "wall_seconds": 90,
                "mp3_complete": False,
                "highest_stable_speed": "unverified",
                "routes": [
                    {
                        "name": "wx_channels_source_download",
                        "status": "failed",
                        "summary": "Captured source evidence.",
                        "post_capture_rescan_report": "/tmp/decode-pair-rescan.json",
                        "post_capture_rescan_result": "decode_key_pair_missing_after_rescan",
                        "post_capture_rescan_pair_count": 0,
                        "post_capture_rescan_stats": {
                            "child_report_count": 8,
                            "source_file_count": 7,
                            "missing_source_file_count": 3,
                            "report_files_scanned": 8,
                            "pair_count": 0,
                            "decode_key_marker_inventory": {
                                "marker_count": 1,
                                "near_media_count": 1,
                                "field_counts": {"decryptKey": 1},
                            },
                        },
                    }
                ],
            }
        )

        self.assertIn("## Post-Capture Rescan Evidence", report)
        self.assertIn("/tmp/decode-pair-rescan.json", report)
        self.assertIn("decode_key_pair_missing_after_rescan", report)
        self.assertIn("child_report_count", report)
        self.assertIn("missing_source_file_count", report)
        self.assertIn("decode_key_marker_inventory", report)
        self.assertIn("decryptKey", report)

    def test_wall_clock_model_separates_playback_bound_from_pipeline_savings(self) -> None:
        model = estimate_wall_clock_model(
            source_duration_seconds=7200,
            confirmed_playback_speed=3,
            segment_seconds=600,
            postprocess_seconds=[20, 20, 20],
            source_decode_seconds=300,
        )

        self.assertEqual(model["playback_wall_seconds"], 2400)
        self.assertEqual(model["hard_lower_bound_without_source_seconds"], 2400)
        self.assertEqual(model["serial_segmented_wall_seconds"], 2460)
        self.assertEqual(model["pipelined_segmented_wall_seconds"], 2400)
        self.assertEqual(model["saved_vs_serial_segmented_seconds"], 60)
        self.assertEqual(model["source_decode_saved_vs_3x_seconds"], 2100)

    def test_cli_dry_run_writes_report_without_output_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            proc = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--url",
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    "--output",
                    str(output),
                    "--mode",
                    "auto",
                    "--dry-run",
                    "--report",
                    str(report),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(output.exists())
            self.assertTrue(report.exists())
            self.assertIn("report_path", proc.stdout)

    def test_cli_non_dry_run_failure_writes_report_and_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            direct_script = root / "direct_links_to_mp3.py"
            direct_script.write_text(
                "import sys\nprint('synthetic direct failure')\nsys.exit(2)\n",
                encoding="utf-8",
            )
            patch = (
                "from pathlib import Path;"
                "import replay_mp3_studio.fast_pipeline as fp;"
                f"fp.AUTHORIZED_FETCHERS=Path({str(root)!r});"
                "raise SystemExit(fp.run_cli())"
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    patch,
                    "--url",
                    "https://weixin.qq.com/sph/NOLOCAL12345",
                    "--output",
                    str(output),
                    "--mode",
                    "auto",
                    "--report",
                    str(report),
                    "--work-dir",
                    str(root / "work"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 2)
            self.assertFalse(output.exists())
            self.assertTrue(report.exists())
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("Direct/provider route did not create a verified MP3", report_text)
            self.assertIn("Skipped because --allow-wechat-ui was not set", report_text)
            self.assertIn("Skipped because --allow-blackbox was not set", report_text)

    def test_auto_pipeline_direct_route_success_verifies_mp3_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                output.write_bytes(b"mp3")
                return SimpleNamespace(returncode=0, stdout="direct ok", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 120.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "existing_direct_or_artifact")
            self.assertTrue(report.exists())
            self.assertIn("最终 MP3 是否完整", report.read_text(encoding="utf-8"))
            self.assertEqual(len(calls), 1)
            self.assertIn("direct_links_to_mp3.py", " ".join(calls[0]))

    def test_auto_pipeline_direct_route_reports_decode_key_provider_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            probe_report = root / "weixin_direct_link_probe.json"

            def fake_runner(command, **_kwargs):
                output.write_bytes(b"mp3")
                probe_report.write_text(
                    json.dumps(
                        {
                            "target": "weixin",
                            "candidate_media_urls": ["configured-sph-resolver"],
                            "attempts": [
                                {"name": "yuanbao-cookie", "status": "skipped"},
                                {
                                    "name": "configured-sph-resolver",
                                    "status": "created-mp3",
                                    "media_source": "resolver_decode_key_pair",
                                    "decode_key_pair_count": 1,
                                    "decode_key_pair_summary": [
                                        {
                                            "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                                            "decode_key_sha256_12": "synthetic",
                                            "decode_key_length": 16,
                                        }
                                    ],
                                },
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, stdout="direct decode ok", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            with patch("replay_mp3_studio.fast_pipeline.DIRECT_LINK_PROBE_REPORT", probe_report, create=True):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "existing_direct_or_artifact")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_source_decode_key")
            direct_route = next(route for route in run["routes"] if route["name"] == "existing_direct_or_artifact")
            self.assertEqual(direct_route["direct_provider_media_source"], "resolver_decode_key_pair")
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("non-realtime_source_decode_key", report_text)

    def test_auto_pipeline_source_artifact_converts_before_running_direct_or_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            source_artifact = root / "authorized-resolver.json"
            source_artifact.write_text(
                json.dumps(
                    {
                        "resolver": {
                            "media": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                            "decodeKey": "0123456789abcdef",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            runner_calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                runner_calls.append(command)
                return SimpleNamespace(returncode=2, stdout="should not run", stderr="")

            def fake_convert(pair, output_path, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {
                    "ok": True,
                    "decode_key_sha256_12": "synthetic",
                    "decode_key_length": len(pair["decode_key"]),
                    "url_host_path": "finder.video.qq.com/251/20302/stodownload",
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 52.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            with patch("replay_mp3_studio.fast_pipeline.decode_weixin_pair_to_mp3", side_effect=fake_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        source_artifact=source_artifact,
                        allow_wechat_ui=True,
                        allow_blackbox=True,
                        duration=120,
                        audio_device="BlackHole",
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            self.assertEqual(runner_calls, [])
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "existing_direct_or_artifact")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_source_decode_key")
            direct_route = next(route for route in run["routes"] if route["name"] == "existing_direct_or_artifact")
            self.assertEqual(direct_route["decode_key_pair_count"], 1)
            self.assertTrue(output.exists())
            report_text = report.read_text(encoding="utf-8")
            json_text = report.with_suffix(".json").read_text(encoding="utf-8")
            self.assertIn("authorized resolver artifact", report_text)
            self.assertNotIn("0123456789abcdef", report_text)
            self.assertNotIn("token=secret", report_text)
            self.assertNotIn("0123456789abcdef", json_text)
            self.assertNotIn("token=secret", json_text)

    def test_auto_pipeline_source_artifact_directory_uses_vendor_adapter_before_direct_or_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            source_dir = root / "vendor-export"
            source_dir.mkdir()
            (source_dir / "downloaded.flv").write_bytes(b"flv" * 128)
            runner_calls: list[list[str]] = []

            def fake_runner(command, *, timeout, cwd=None):
                runner_calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "-i" in command and "-f" in command and "direct_links_to_mp3.py" not in joined:
                    Path(command[-1]).write_bytes(b"mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=2, stdout="direct route should not run", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    source_artifact=source_dir,
                    allow_wechat_ui=True,
                    allow_blackbox=True,
                    duration=120,
                    audio_device="BlackHole",
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in runner_calls)
            self.assertNotIn("direct_links_to_mp3.py", joined_calls)
            self.assertNotIn("weixin_multi_open_capture.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "existing_direct_or_artifact")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_vendor_source")
            direct_route = next(route for route in run["routes"] if route["name"] == "existing_direct_or_artifact")
            self.assertEqual(direct_route["vendor_source_kind"], "local_media_file")
            self.assertTrue(output.exists())
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("source-listener artifact", report_text)
            self.assertIn("source_decode_saved_vs_3x_seconds", report_text)
            self.assertIn("bypasses playback", report_text)
            self.assertNotIn("Pipeline overlaps post-processing", report_text)

    def test_source_artifact_must_satisfy_declared_duration_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            source_dir = root / "vendor-export"
            source_dir.mkdir()
            (source_dir / "downloaded.flv").write_bytes(b"flv" * 128)

            def fake_runner(command, *, timeout, cwd=None):
                joined = " ".join(str(part) for part in command)
                if "-i" in command and "-f" in command and "direct_links_to_mp3.py" not in joined:
                    Path(command[-1]).write_bytes(b"short-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                duration = 10.0
                if min_duration_seconds and duration < min_duration_seconds:
                    raise RuntimeError(
                        f"MP3 output is shorter than required minimum: {duration:.2f}s < "
                        f"{min_duration_seconds:.2f}s ({path})"
                    )
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": duration,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    source_artifact=source_dir,
                    duration=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertFalse(run["mp3_complete"])
            self.assertNotEqual(run.get("selected_route"), "existing_direct_or_artifact")
            direct_route = next(route for route in run["routes"] if route["name"] == "existing_direct_or_artifact")
            self.assertIn("shorter than required minimum", direct_route.get("vendor_source_error", ""))
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("### 6. 最终 MP3 是否完整？", report_text)
            self.assertIn("no", report_text)

    def test_auto_pipeline_discovers_matching_source_vault_artifact_from_url_before_direct_or_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            vault_root = root / "authorized-source-vault" / "sources"
            source_dir = vault_root / "AFfTIp5Ywj-listener-export"
            source_dir.mkdir(parents=True)
            (source_dir / "manifest.json").write_text(
                json.dumps({"url": "https://weixin.qq.com/sph/AFfTIp5Ywj"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (source_dir / "downloaded.flv").write_bytes(b"flv" * 128)
            runner_calls: list[list[str]] = []

            def fake_runner(command, *, timeout, cwd=None):
                runner_calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "-i" in command and "-f" in command and "direct_links_to_mp3.py" not in joined:
                    Path(command[-1]).write_bytes(b"mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=2, stdout="slower route should not run", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    source_artifact_roots=(vault_root,),
                    allow_wechat_ui=True,
                    allow_blackbox=True,
                    duration=120,
                    audio_device="BlackHole",
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in runner_calls)
            self.assertNotIn("direct_links_to_mp3.py", joined_calls)
            self.assertNotIn("weixin_multi_open_capture.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "existing_direct_or_artifact")
            direct_route = next(route for route in run["routes"] if route["name"] == "existing_direct_or_artifact")
            self.assertEqual(direct_route["source_artifact_status"], "auto_discovered")
            self.assertEqual(direct_route["source_artifact_discovery"]["status"], "matched")
            self.assertEqual(Path(direct_route["source_artifact_discovery"]["matched_path"]).name, source_dir.name)
            self.assertEqual(direct_route["vendor_source_kind"], "local_media_file")
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("auto-discovered source artifact", report_text)
            self.assertIn("Source Artifact Discovery", report_text)
            self.assertIn("AFfTIp5Ywj-listener-export", report_text)
            self.assertNotIn("slower route should not run", report_text)

    def test_auto_pipeline_uses_source_vault_artifact_created_after_wechat_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            vault_root = root / "authorized-source-vault" / "sources"
            runner_calls: list[list[str]] = []

            def fake_runner(command, *, timeout, cwd=None):
                runner_calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no direct source", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "decode_key_pair_count": 0,
                                "rounds": [{"round": 1}],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    source_dir = vault_root / "AFfTIp5Ywj-post-open-export"
                    source_dir.mkdir(parents=True)
                    (source_dir / "manifest.json").write_text(
                        json.dumps({"url": "https://weixin.qq.com/sph/AFfTIp5Ywj"}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    (source_dir / "downloaded.flv").write_bytes(b"flv" * 128)
                    return SimpleNamespace(returncode=0, stdout="opened and listener wrote artifact", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    (run_dir / "decode-pair-rescan.json").write_text(
                        json.dumps({"result": "decode_key_pair_missing_after_rescan", "decode_key_pair_count": 0}),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="no pair", stderr="")
                if "-i" in command and "-f" in command:
                    Path(command[-1]).write_bytes(b"mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=2, stdout="unexpected slow path", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    source_artifact_roots=(vault_root,),
                    allow_wechat_ui=True,
                    allow_blackbox=True,
                    duration=120,
                    audio_device="BlackHole",
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in runner_calls)
            self.assertIn("weixin_multi_open_capture.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_source_download")
            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertEqual(source_route["post_open_source_artifact_discovery"]["status"], "matched")
            self.assertEqual(source_route["vendor_source_kind"], "local_media_file")
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("Post-Open Source Artifact Discovery", report_text)
            self.assertIn("AFfTIp5Ywj-post-open-export", report_text)
            self.assertNotIn("unexpected slow path", report_text)

    def test_auto_pipeline_can_use_current_delta_watch_after_wechat_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            vault_root = root / "authorized-source-vault" / "sources"
            runner_calls: list[list[str]] = []

            def fake_runner(command, *, timeout, cwd=None):
                runner_calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no direct source", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "decode_key_pair_count": 0,
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="opened but no decode pair", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    (run_dir / "decode-pair-rescan.json").write_text(
                        json.dumps({"result": "decode_key_pair_missing_after_rescan", "decode_key_pair_count": 0}),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="no pair", stderr="")
                if "weixin_current_playback_delta_to_mp3.py" in joined:
                    output.write_bytes(b"mp3")
                    report_arg = Path(command[command.index("--report") + 1])
                    report_arg.parent.mkdir(parents=True, exist_ok=True)
                    report_arg.write_text(
                        json.dumps(
                            {
                                "diagnosis": "visible_media_converted",
                                "result": {
                                    "source": str(root / "captured-cache.mp4"),
                                    "duration": 120.0,
                                    "output": str(output),
                                },
                                "visible_events": [
                                    {
                                        "relative_path": "Data/tmp/.5A4RE8SF68.com.tencent.xinWeChat.MEDIA",
                                        "bytes": 1234567,
                                        "media_candidate": True,
                                    }
                                ],
                                "attempts": [{"duration": 120.0, "output_duration": 120.0}],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="delta converted", stderr="")
                if "blackbox-record" in joined:
                    return SimpleNamespace(returncode=2, stdout="blackbox should not run", stderr="")
                return SimpleNamespace(returncode=2, stdout="unexpected route", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 120.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    source_artifact_roots=(vault_root,),
                    allow_wechat_ui=True,
                    allow_blackbox=True,
                    duration=120,
                    audio_device="BlackHole",
                    current_delta_watch_seconds=2,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in runner_calls)
            self.assertIn("weixin_current_playback_delta_to_mp3.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_current_delta_watch")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_current_delta_source")
            delta_route = next(route for route in run["routes"] if route["name"] == "wx_channels_current_delta_watch")
            self.assertEqual(delta_route["status"], "success")
            self.assertEqual(delta_route["diagnosis"], "visible_media_converted")
            self.assertEqual(delta_route["visible_media_event_count"], 1)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("wx_channels_current_delta_watch", report_text)
            self.assertIn("visible_media_converted", report_text)
            self.assertNotIn("blackbox should not run", report_text)

    def test_current_delta_success_archives_source_for_next_auto_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "first.mp3"
            report = root / "first.report.md"
            second_output = root / "second.mp3"
            second_report = root / "second.report.md"
            vault_root = root / "authorized-source-vault" / "sources"
            captured_media = root / "captured-visible-cache.mp4"
            captured_media.write_bytes(b"mp4" * 256)
            runner_calls: list[list[str]] = []

            def fake_runner(command, *, timeout, cwd=None):
                runner_calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no direct source", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps({"result": "encrypted_stodownload_found_decode_key_missing"}),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="opened", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in joined:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    (run_dir / "decode-pair-rescan.json").write_text(
                        json.dumps({"result": "decode_key_pair_missing_after_rescan", "decode_key_pair_count": 0}),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="no pair", stderr="")
                if "weixin_current_playback_delta_to_mp3.py" in joined:
                    output.write_bytes(b"mp3")
                    report_arg = Path(command[command.index("--report") + 1])
                    report_arg.parent.mkdir(parents=True, exist_ok=True)
                    report_arg.write_text(
                        json.dumps(
                            {
                                "diagnosis": "visible_media_converted",
                                "attempts": [{"captured": str(captured_media), "duration": 120.0}],
                                "result": {
                                    "source": str(captured_media),
                                    "duration": 120.0,
                                    "output": str(output),
                                },
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="delta converted", stderr="")
                if "-i" in command and "-f" in command:
                    Path(command[-1]).write_bytes(b"mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=2, stdout="unexpected", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 120.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            first = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "first-work",
                    source_artifact_roots=(vault_root,),
                    allow_wechat_ui=True,
                    duration=120,
                    current_delta_watch_seconds=2,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(first["mp3_complete"])
            self.assertEqual(first["selected_route"], "wx_channels_current_delta_watch")
            delta_route = next(route for route in first["routes"] if route["name"] == "wx_channels_current_delta_watch")
            archive = delta_route["source_vault_archive"]
            self.assertEqual(archive["status"], "archived")
            artifact_path = Path(archive["artifact_path"])
            self.assertTrue((artifact_path / "manifest.json").exists())
            self.assertTrue((artifact_path / "downloaded.mp4").exists())
            manifest_text = (artifact_path / "manifest.json").read_text(encoding="utf-8")
            self.assertIn("current_delta_watch", manifest_text)
            self.assertIn("AFfTIp5Ywj", str(artifact_path))

            runner_calls.clear()
            second = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=second_output,
                    report=second_report,
                    mode="auto",
                    work_dir=root / "second-work",
                    source_artifact_roots=(vault_root,),
                    allow_wechat_ui=True,
                    duration=120,
                    current_delta_watch_seconds=2,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in runner_calls)
            self.assertTrue(second["mp3_complete"])
            self.assertEqual(second["selected_route"], "existing_direct_or_artifact")
            self.assertNotIn("weixin_multi_open_capture.py", joined_calls)
            self.assertNotIn("weixin_current_playback_delta_to_mp3.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)

    def test_auto_pipeline_does_not_send_or_record_without_explicit_allow_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {},
            )

            self.assertFalse(run["mp3_complete"])
            statuses = {route["name"]: route["status"] for route in run["routes"]}
            self.assertEqual(statuses["existing_direct_or_artifact"], "failed")
            self.assertEqual(statuses["wx_channels_source_download"], "skipped")
            self.assertEqual(statuses["blackbox_3x_fallback"], "skipped")
            joined_calls = "\n".join(" ".join(command) for command in calls)
            self.assertIn("direct_links_to_mp3.py", joined_calls)
            self.assertIn("ps -ax", joined_calls)
            self.assertNotIn("weixin_multi_open_capture.py", joined_calls)
            self.assertNotIn("blackbox-record", joined_calls)

    def test_auto_pipeline_reports_fallback_eta_without_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    duration=7200,
                    blackbox_speed=3,
                    segment_seconds=600,
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {},
            )

            self.assertFalse(run["mp3_complete"])
            self.assertEqual(run["time_model"]["playback_wall_seconds"], 2400)
            self.assertEqual(run["time_model"]["planned_segment_count"], 12)
            timeline = next(route for route in run["routes"] if route["name"] == "timeline_seek_probe")
            self.assertEqual(timeline["status"], "completed")
            self.assertFalse(timeline["probe"]["complete_mp3_possible"])
            self.assertEqual(timeline["probe"]["limit_point"], "seek_burst_captures_discontinuous_audio")
            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")
            self.assertEqual(len(segmented["planned_segments"]), 12)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("## Time Model", report_text)
            self.assertIn("Planned segments", report_text)
            joined_calls = "\n".join(" ".join(command) for command in calls)
            self.assertNotIn("blackbox-record", joined_calls)
            self.assertEqual(segmented["planned_segments"][0]["source_duration_seconds"], 600.0)
            self.assertEqual(segmented["planned_segments"][0]["record_duration_seconds"], 200.0)

    def test_nonsegmented_blackbox_records_at_wall_clock_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            record_durations: list[float] = []

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    record_durations.append(float(command[command.index("--duration") + 1]))
                    Path(command[command.index("--out") + 1]).write_bytes(b"blackbox-mp3")
                    return SimpleNamespace(returncode=0, stdout="record ok", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 120.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=3,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            blackbox = next(route for route in run["routes"] if route["name"] == "blackbox_3x_fallback")
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(record_durations, [40.0])
            self.assertEqual(blackbox["source_duration_seconds"], 120)
            self.assertEqual(blackbox["record_duration_seconds"], 40.0)

    def test_auto_pipeline_caps_weixin_blackbox_speed_to_verified_official_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            record_commands: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    record_commands.append(command)
                    Path(command[command.index("--out") + 1]).write_bytes(b"blackbox-mp3")
                    return SimpleNamespace(returncode=0, stdout="recorded", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=8,
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 40.0},
            )

            self.assertEqual(run["selected_route"], "blackbox_3x_fallback")
            self.assertEqual(run["highest_stable_speed"], "3x_requested")
            blackbox = next(route for route in run["routes"] if route["name"] == "blackbox_3x_fallback")
            self.assertEqual(blackbox["requested_speed"], 8)
            self.assertEqual(blackbox["effective_speed"], 3.0)
            self.assertEqual(record_commands[0][record_commands[0].index("--speed") + 1], "3.0")
            self.assertEqual(float(record_commands[0][record_commands[0].index("--duration") + 1]), 40.0)

    def test_auto_pipeline_records_wechat_source_capture_limit_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                if "weixin_multi_open_capture.py" in " ".join(command):
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "rounds": [
                                    {
                                        "inline_marker_scan": {"candidate_url_count": 8},
                                        "source_snapshot_summary": {
                                            "snapshot_count": 2,
                                            "source_file_reference_count": 3,
                                            "source_file_count": 2,
                                            "missing_source_file_count": 1,
                                        },
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="multi_open_result=encrypted_stodownload_found_decode_key_missing", stderr="")
                if "weixin_candidate_url_classifier.py" in " ".join(command):
                    output_path = Path(command[command.index("--output") + 1])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        json.dumps(
                            {
                                "unique_candidate_url_count": 3,
                                "probe_enabled": True,
                                "probe_results": [
                                    {
                                        "range_status": 206,
                                        "content_type": "video/mp4",
                                        "content_range": "bytes 0-4095/21997456",
                                        "first_bytes_class": "binary_unknown_or_encrypted",
                                    },
                                    {
                                        "range_status": 400,
                                        "content_type": "application/octet-stream",
                                        "first_bytes_class": "empty",
                                    },
                                    {
                                        "range_status": 200,
                                        "content_type": "image/png",
                                        "content_range": "bytes 0-1526/1527",
                                        "first_bytes_class": "binary_unknown_or_encrypted",
                                    },
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="classified", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_wechat_ui=True,
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {},
            )

            self.assertFalse(run["mp3_complete"])
            self.assertEqual(run["limit_point"], "encrypted_stodownload_decode_key_missing")
            self.assertIn("decode key", run["speed_reason"])
            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertEqual(source_route["capture_result"], "encrypted_stodownload_found_decode_key_missing")
            self.assertEqual(source_route["source_snapshot_summary"]["snapshot_count"], 2)
            self.assertEqual(
                source_route["candidate_url_classification_summary"]["direct_playable_candidate_count"],
                0,
            )
            self.assertEqual(
                source_route["candidate_url_classification_summary"]["encrypted_video_candidate_count"],
                1,
            )
            self.assertIn("source_snapshot_summary", report.read_text(encoding="utf-8"))
            self.assertIn("snapshot_count", report.read_text(encoding="utf-8"))
            self.assertIn("Candidate URL Classification", report.read_text(encoding="utf-8"))
            self.assertIn("direct_playable_candidate_count", report.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(calls), 2)

    def test_auto_pipeline_converts_encrypted_candidate_probe_numeric_key_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            numeric_artifact = root / "successful-numeric-pairs.json"
            calls: list[list[str]] = []
            numeric_artifact.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                "key": 123456789,
                                "encLimit": 131072,
                                "source": "heuristic_numeric_key",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(str(part) for part in command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no direct", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in command:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    round_dir = run_dir / "round-01"
                    round_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "decode_key_pair_count": 0,
                                "rounds": [
                                    {
                                        "source_snapshot_summary": {
                                            "snapshot_count": 1,
                                            "source_file_count": 1,
                                        }
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="encrypted source", stderr="")
                if "weixin_candidate_url_classifier.py" in joined:
                    output_path = Path(command[command.index("--output") + 1])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        json.dumps(
                            {
                                "unique_candidate_url_count": 1,
                                "probe_enabled": True,
                                "probe_results": [
                                    {
                                        "range_status": 206,
                                        "content_type": "video/mp4",
                                        "content_range": "bytes 0-4095/423307600",
                                        "first_bytes_class": "binary_unknown_or_encrypted",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="classified", stderr="")
                if "weixin_encrypted_candidate_probe.py" in joined:
                    output_path = Path(command[command.index("--output") + 1])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        json.dumps(
                            {
                                "source_file_count": 3,
                                "candidate_url_count": 1,
                                "heuristic_numeric_key_count": 12,
                                "successful_numeric_pair_count": 1,
                                "result": "mp4_header_decrypted",
                                "raw_values_in_report": False,
                                "numeric_key_pair_artifact": str(numeric_artifact),
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="probe success", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in command:
                    raise AssertionError("rescan should not run after encrypted probe conversion succeeds")
                return SimpleNamespace(returncode=2, stdout="unexpected", stderr="")

            def fake_vendor_convert(source_artifact, output_path, **_kwargs):
                self.assertEqual(Path(source_artifact), numeric_artifact)
                Path(output_path).write_bytes(b"mp3")
                return {
                    "source_kind": "numeric_key_pair",
                    "scan": {
                        "source_is_directory": False,
                        "file_count": 1,
                        "text_file_scanned_count": 1,
                        "numeric_key_pair_count": 1,
                        "raw_values_in_report": False,
                    },
                    "numeric_key_pair_summary": [
                        {
                            "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                            "numeric_key_sha256_12": "synthetic",
                            "numeric_key_digits": 9,
                            "enc_limit": 131072,
                        }
                    ],
                    "verification": {"ok": True, "path": str(output_path), "duration_seconds": 120.0},
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            with patch("replay_mp3_studio.fast_pipeline.convert_vendor_source_to_mp3", side_effect=fake_vendor_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            joined_calls = "\n".join(" ".join(str(part) for part in call) for call in calls)
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_source_download")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_source_numeric_key")
            self.assertIn("weixin_encrypted_candidate_probe.py", joined_calls)
            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertEqual(source_route["encrypted_candidate_probe_summary"]["result"], "mp4_header_decrypted")
            self.assertEqual(source_route["vendor_source_kind"], "numeric_key_pair")
            report_text = report.read_text(encoding="utf-8")
            json_text = report.with_suffix(".json").read_text(encoding="utf-8")
            self.assertIn("Encrypted Candidate Probe", report_text)
            self.assertIn("successful_numeric_pair_count", report_text)
            self.assertNotIn("123456789", report_text)
            self.assertNotIn("token=secret", report_text)
            self.assertNotIn("123456789", json_text)
            self.assertNotIn("token=secret", json_text)

    def test_auto_pipeline_summarizes_decode_key_pairs_from_source_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"

            def fake_runner(command, **_kwargs):
                if "weixin_multi_open_capture.py" in " ".join(command):
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "decode_key_pair_found_not_converted",
                                "rounds": [
                                    {
                                        "same_response": {
                                            "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                            "decodeKey": "0123456789abcdef",
                                        }
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="decode pair", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            with patch(
                "replay_mp3_studio.fast_pipeline.decode_weixin_pair_to_mp3",
                side_effect=RuntimeError("synthetic conversion unavailable"),
            ):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=lambda *_args, **_kwargs: {},
                )

            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            encoded = json.dumps(source_route["decode_key_pair_summary"], ensure_ascii=False)
            self.assertEqual(source_route["decode_key_pair_count"], 1)
            self.assertIn("stodownload?<redacted>", encoded)
            self.assertNotIn("0123456789abcdef", encoded)
            self.assertNotIn("token=secret", encoded)
            self.assertEqual(source_route["decode_key_conversion"]["status"], "failed")

    def test_auto_pipeline_converts_same_response_decode_key_pair_to_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"

            def fake_runner(command, **_kwargs):
                if "weixin_multi_open_capture.py" in " ".join(command):
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "decode_key_pair_found",
                                "same_response": {
                                    "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                    "decode_key": "0123456789abcdef",
                                },
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="decode pair", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            def fake_convert(pair, output_path, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {
                    "ok": True,
                    "decode_key_sha256_12": "synthetic",
                    "decode_key_length": len(pair["decode_key"]),
                    "url_host_path": "finder.video.qq.com/251/20302/stodownload",
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": 52.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            with patch("replay_mp3_studio.fast_pipeline.decode_weixin_pair_to_mp3", side_effect=fake_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_source_download")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_source_decode_key")
            self.assertTrue(output.exists())
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("non-realtime_source_decode_key", report_text)
            self.assertNotIn("0123456789abcdef", report_text)
            self.assertNotIn("token=secret", report_text)

    def test_auto_pipeline_converts_artifact_decode_key_pair_to_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            artifact = root / "sensitive-pairs.json"
            artifact.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                "decode_key": "0123456789abcdef",
                                "path": "local-source",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_runner(command, **_kwargs):
                if "weixin_multi_open_capture.py" in " ".join(command):
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "decode_key_pair_found",
                                "decode_key_pair_count": 1,
                                "decode_key_pair_artifact": str(artifact),
                                "decode_key_pair_summary": [
                                    {
                                        "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                                        "decode_key_sha256_12": "synthetic",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="decode artifact", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            def fake_convert(pair, output_path, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {
                    "ok": True,
                    "decode_key_sha256_12": "synthetic",
                    "decode_key_length": len(pair["decode_key"]),
                    "url_host_path": "finder.video.qq.com/251/20302/stodownload",
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            with patch("replay_mp3_studio.fast_pipeline.decode_weixin_pair_to_mp3", side_effect=fake_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_source_download")
            self.assertEqual(source_route["decode_key_pair_count"], 1)
            self.assertTrue(output.exists())
            report_text = report.read_text(encoding="utf-8")
            json_text = report.with_suffix(".json").read_text(encoding="utf-8")
            self.assertNotIn("0123456789abcdef", report_text)
            self.assertNotIn("token=secret", report_text)
            self.assertNotIn("0123456789abcdef", json_text)
            self.assertNotIn("token=secret", json_text)

    def test_auto_pipeline_converts_artifact_numeric_key_pair_to_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            artifact = root / "sensitive-numeric-pairs.json"
            artifact.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                "key": 123456789,
                                "enc_limit": 65536,
                                "path": "delta-source",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_runner(command, **_kwargs):
                if "weixin_multi_open_capture.py" in " ".join(command):
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "numeric_key_pair_found",
                                "numeric_key_pair_count": 1,
                                "numeric_key_pair_artifact": str(artifact),
                                "numeric_key_pair_summary": [
                                    {
                                        "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                                        "numeric_key_sha256_12": "synthetic",
                                        "numeric_key_digits": 9,
                                        "enc_limit": 65536,
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="numeric artifact", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            def fake_convert(pair, output_path, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {
                    "ok": True,
                    "numeric_key_sha256_12": "synthetic",
                    "numeric_key_digits": len(str(pair["key"])),
                    "url_host_path": "finder.video.qq.com/251/20302/stodownload",
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            with patch("replay_mp3_studio.fast_pipeline.decode_weixin_numeric_key_pair_to_mp3", side_effect=fake_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "wx_channels_source_download")
            self.assertEqual(run["highest_stable_speed"], "non-realtime_source_numeric_key")
            self.assertEqual(source_route["numeric_key_pair_count"], 1)
            report_text = report.read_text(encoding="utf-8")
            json_text = report.with_suffix(".json").read_text(encoding="utf-8")
            self.assertNotIn("123456789", report_text)
            self.assertNotIn("token=secret", report_text)
            self.assertNotIn("123456789", json_text)
            self.assertNotIn("token=secret", json_text)

    def test_auto_pipeline_runs_post_capture_rescan_and_converts_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            artifact = root / "rescan-sensitive-pairs.json"
            calls: list[list[str]] = []
            artifact.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                "decode_key": "fedcba9876543210",
                                "path": "post-capture-rescan",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(command)
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in command:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "decode_key_pair_count": 0,
                                "rounds": [],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="missing pair", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in command:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    (run_dir / "decode-pair-rescan.json").write_text(
                        json.dumps(
                            {
                                "result": "decode_key_pair_found",
                                "decode_key_pair_count": 1,
                                "decode_key_pair_artifact": str(artifact),
                                "decode_key_pair_summary": [
                                    {
                                        "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                                        "decode_key_sha256_12": "synthetic",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=0, stdout="rescan pair", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            def fake_convert(pair, output_path, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {
                    "ok": True,
                    "decode_key_sha256_12": "synthetic",
                    "decode_key_length": len(pair["decode_key"]),
                    "url_host_path": "finder.video.qq.com/251/20302/stodownload",
                }

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            with patch("replay_mp3_studio.fast_pipeline.decode_weixin_pair_to_mp3", side_effect=fake_convert):
                run = run_auto_pipeline(
                    AutoPipelineOptions(
                        url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output=output,
                        report=report,
                        mode="auto",
                        work_dir=root / "work",
                        allow_wechat_ui=True,
                    ),
                    runner=fake_runner,
                    verifier=fake_verify,
                )

            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            joined_calls = "\n".join(" ".join(command) for command in calls)
            report_text = report.read_text(encoding="utf-8")
            json_text = report.with_suffix(".json").read_text(encoding="utf-8")
            self.assertTrue(run["mp3_complete"])
            self.assertIn("--rescan-only", joined_calls)
            self.assertTrue(source_route["post_capture_rescan_report"].endswith("decode-pair-rescan.json"))
            self.assertNotIn("fedcba9876543210", report_text)
            self.assertNotIn("token=secret", report_text)
            self.assertNotIn("fedcba9876543210", json_text)
            self.assertNotIn("token=secret", json_text)

    def test_auto_pipeline_post_capture_rescan_preserves_original_capture_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" not in command:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / "report.json").write_text(
                        json.dumps(
                            {
                                "result": "encrypted_stodownload_found_decode_key_missing",
                                "decode_key_pair_count": 0,
                                "rounds": [
                                    {"inline_marker_scan": {"candidate_url_count": 3}},
                                    {"inline_marker_scan": {"candidate_url_count": 8}},
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="missing pair", stderr="")
                if "weixin_multi_open_capture.py" in joined and "--rescan-only" in command:
                    run_dir = Path(command[command.index("--run-dir") + 1])
                    (run_dir / "decode-pair-rescan.json").write_text(
                        json.dumps(
                            {
                                "result": "decode_key_pair_missing_after_rescan",
                                "decode_key_pair_count": 0,
                                "rescan": {
                                    "child_report_count": 8,
                                    "source_file_count": 4,
                                    "pair_count": 0,
                                },
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return SimpleNamespace(returncode=2, stdout="no rescan pair", stderr="")
                return SimpleNamespace(returncode=2, stdout="no media", stderr="")

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_wechat_ui=True,
                ),
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {},
            )

            source_route = next(route for route in run["routes"] if route["name"] == "wx_channels_source_download")
            self.assertFalse(run["mp3_complete"])
            self.assertEqual(source_route["capture_result"], "encrypted_stodownload_found_decode_key_missing")
            self.assertEqual(source_route["capture_rounds"], 2)
            self.assertEqual(source_route["post_capture_rescan_result"], "decode_key_pair_missing_after_rescan")
            self.assertEqual(source_route["post_capture_rescan_pair_count"], 0)

    def test_speed_capability_probe_classifies_desktop_vlc_without_control_channel(self) -> None:
        summary = summarize_speed_capability_probe(
            ps_output="123 ?? wxplayer\n456 ?? WeChatAppEx Helper (Renderer)",
            lsof_output="/Applications/WeChat.app/Contents/Frameworks/libvlc.12.dylib\n",
            nm_output="0000000000000000 T _libvlc_media_player_set_rate\n",
        )

        self.assertEqual(summary["player_stack"], "desktop_wechat_wxplayer_libvlc")
        self.assertTrue(summary["libvlc_set_rate_symbol"])
        self.assertEqual(summary["safe_control_channel"], "none_verified")
        self.assertIn("not_html_media", summary["limit_point"])

    def test_speed_probe_detects_safe_cdp_remote_debugging_channel(self) -> None:
        summary = summarize_speed_capability_probe(
            ps_output=(
                "123 /Applications/WeChat.app/Contents/MacOS/wxplayer\n"
                "456 /Applications/WeChat.app/Contents/Frameworks/WeChatAppEx Helper "
                "--type=renderer --remote-debugging-port=9222\n"
            ),
            lsof_output="/Applications/WeChat.app/Contents/Frameworks/libvlc.12.dylib\n",
            nm_output="0000000000000000 T _libvlc_media_player_set_rate\n",
            cdp_versions={9222: '{"Browser":"Chrome/120.0","Protocol-Version":"1.3"}'},
        )

        self.assertEqual(summary["safe_control_channel"], "cdp")
        self.assertEqual(summary["control_probe"]["candidate_debug_ports"], [9222])
        self.assertTrue(summary["control_probe"]["cdp_version_ok"])
        self.assertIn("--remote-debugging-port=9222", summary["control_probe"]["remote_debugging_flags"])

    def test_webview_control_probe_reports_no_safe_channel_without_debugging_flag(self) -> None:
        probe = summarize_webview_control_channels(
            ps_output="123 /Applications/WeChat.app/Contents/MacOS/wxplayer\n"
            "456 /Applications/WeChat.app/Contents/Frameworks/WeChatAppEx Helper --type=renderer\n",
            lsof_output="",
        )

        self.assertEqual(probe["safe_webview_control_channel"], "none_verified")
        self.assertEqual(probe["candidate_debug_ports"], [])
        self.assertEqual(probe["limit_point"], "wechat_webview_cdp_not_exposed")

    def test_plan_blackbox_segments_covers_total_duration(self) -> None:
        segments = plan_blackbox_segments(total_duration=125, segment_seconds=60)

        self.assertEqual(
            segments,
            [
                {"index": 1, "start_seconds": 0.0, "duration_seconds": 60.0},
                {"index": 2, "start_seconds": 60.0, "duration_seconds": 60.0},
                {"index": 3, "start_seconds": 120.0, "duration_seconds": 5.0},
            ],
        )

    def test_extract_weixin_decode_key_pairs_requires_same_response_object(self) -> None:
        payload = {
            "data": {
                "media": {
                    "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                    "decode_key": "0123456789abcdef",
                },
                "unrelated": {
                    "url": "https://finder.video.qq.com/251/20302/stodownload?token=other",
                },
            }
        }

        pairs = extract_weixin_decode_key_pairs(payload)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["decode_key"], "0123456789abcdef")
        self.assertIn("stodownload", pairs[0]["url"])

    def test_redacted_decode_key_pair_summary_does_not_leak_key_or_query(self) -> None:
        pairs = [
            {
                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                "decode_key": "0123456789abcdef",
                "path": "data.media",
            }
        ]

        summary = redacted_decode_key_pair_summary(pairs)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertIn("decode_key_sha256_12", summary[0])
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_auto_pipeline_segmented_blackbox_records_parts_and_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    out = Path(command[command.index("--out") + 1])
                    out.with_suffix(".fast.m4a").write_bytes(b"fast-segment")
                    return SimpleNamespace(returncode=0, stdout="segment ok", stderr="")
                if "convert-file" in joined:
                    Path(command[command.index("--out") + 1]).write_bytes(b"segment-mp3")
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                if "-f concat" in joined:
                    Path(command[-1]).write_bytes(b"merged-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=125,
                    audio_device="system",
                    blackbox_speed=3,
                    segment_seconds=60,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "segmented_blackbox")
            self.assertTrue(output.exists())
            joined_calls = "\n".join(" ".join(command) for command in calls)
            self.assertEqual(joined_calls.count("blackbox-record"), 3)
            self.assertEqual(joined_calls.count("convert-file"), 3)
            self.assertEqual(joined_calls.count("--raw-only"), 3)
            self.assertEqual(joined_calls.count("--keep-fast"), 3)
            self.assertIn("-f concat", joined_calls)
            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")
            self.assertEqual(segmented["status"], "success")
            self.assertEqual(len(segmented["segments"]), 3)
            self.assertEqual(segmented["segments"][0]["postprocess_mode"], "pipeline_raw_capture_then_convert")
            self.assertIn("time_model", segmented)
            self.assertIn("playback_wall_seconds", run["time_model"])
            self.assertTrue(Path(segmented["manifest"]).exists())

    def test_auto_pipeline_auto_segments_long_blackbox_fallback_without_explicit_segment_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    out = Path(command[command.index("--out") + 1])
                    if "--raw-only" in command:
                        out.with_suffix(".fast.m4a").write_bytes(b"fast-segment")
                    else:
                        out.write_bytes(b"single-recording")
                    return SimpleNamespace(returncode=0, stdout="record ok", stderr="")
                if "convert-file" in joined:
                    Path(command[command.index("--out") + 1]).write_bytes(b"segment-mp3")
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                if "-f concat" in joined:
                    Path(command[-1]).write_bytes(b"merged-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=7200,
                    audio_device="system",
                    blackbox_speed=3,
                    min_duration_seconds=7200,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(run["mp3_complete"])
            self.assertEqual(run["selected_route"], "segmented_blackbox")
            joined_calls = "\n".join(" ".join(command) for command in calls)
            self.assertEqual(joined_calls.count("blackbox-record"), 12)
            self.assertEqual(joined_calls.count("convert-file"), 12)
            self.assertEqual(joined_calls.count("--raw-only"), 12)
            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")
            blackbox = next(route for route in run["routes"] if route["name"] == "blackbox_3x_fallback")
            self.assertEqual(segmented["segment_selection"]["source"], "auto_long_blackbox_default")
            self.assertEqual(segmented["segment_selection"]["segment_seconds"], 600.0)
            self.assertEqual(len(segmented["segments"]), 12)
            self.assertEqual(segmented["segments"][0]["source_duration_seconds"], 600.0)
            self.assertEqual(segmented["segments"][0]["record_duration_seconds"], 200.0)
            self.assertEqual(segmented["time_model"]["segment_seconds"], 600.0)
            self.assertEqual(blackbox["status"], "replaced")

    def test_segmented_blackbox_records_source_segments_at_wall_clock_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            record_durations: list[float] = []

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    record_durations.append(float(command[command.index("--duration") + 1]))
                    out = Path(command[command.index("--out") + 1])
                    out.with_suffix(".fast.m4a").write_bytes(b"fast-segment")
                    return SimpleNamespace(returncode=0, stdout="segment ok", stderr="")
                if "convert-file" in joined:
                    Path(command[command.index("--out") + 1]).write_bytes(b"segment-mp3")
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                if "-f concat" in joined:
                    Path(command[-1]).write_bytes(b"merged-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=3,
                    segment_seconds=60,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")
            self.assertEqual(record_durations, [20.0, 20.0])
            self.assertEqual(segmented["segments"][0]["source_duration_seconds"], 60.0)
            self.assertEqual(segmented["segments"][0]["record_duration_seconds"], 20.0)

    def test_segmented_blackbox_postprocess_overlaps_next_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            events: list[tuple[str, float]] = []
            convert_started = threading.Event()
            allow_convert_finish = threading.Event()

            def fake_runner(command, **_kwargs):
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    out = Path(command[command.index("--out") + 1])
                    events.append((f"record_start:{out.name}", time.monotonic()))
                    if out.name.endswith("part002.mp3"):
                        if not convert_started.wait(timeout=1):
                            raise AssertionError("part 2 recording started without part 1 conversion running")
                        events.append(("record2_observed_convert1_running", time.monotonic()))
                        allow_convert_finish.set()
                    time.sleep(0.01)
                    out.with_suffix(".fast.m4a").write_bytes(b"fast-segment")
                    events.append((f"record_end:{out.name}", time.monotonic()))
                    return SimpleNamespace(returncode=0, stdout="segment ok", stderr="")
                if "convert-file" in joined:
                    out = Path(command[command.index("--out") + 1])
                    events.append((f"convert_start:{out.name}", time.monotonic()))
                    convert_started.set()
                    if not allow_convert_finish.wait(timeout=1):
                        raise AssertionError("conversion was not allowed to overlap the next recording")
                    out.write_bytes(b"segment-mp3")
                    events.append((f"convert_end:{out.name}", time.monotonic()))
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                if "-f concat" in joined:
                    Path(command[-1]).write_bytes(b"merged-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {"ok": True, "path": str(path), "bytes": Path(path).stat().st_size}

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=3,
                    segment_seconds=60,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(run["mp3_complete"])
            names = [name for name, _when in events]
            self.assertIn("record2_observed_convert1_running", names)

    def test_auto_pipeline_segmented_blackbox_skips_verified_existing_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            existing = root / "work" / "blackbox-segments" / "output.part001.mp3"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"existing-segment")
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    out = Path(command[command.index("--out") + 1])
                    out.with_suffix(".fast.m4a").write_bytes(b"new-fast-segment")
                    return SimpleNamespace(returncode=0, stdout="segment ok", stderr="")
                if "convert-file" in joined:
                    Path(command[command.index("--out") + 1]).write_bytes(b"new-segment")
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                if "-f concat" in joined:
                    Path(command[-1]).write_bytes(b"merged-mp3")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=3,
                    segment_seconds=60,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            self.assertTrue(run["mp3_complete"])
            joined_calls = "\n".join(" ".join(command) for command in calls)
            self.assertEqual(joined_calls.count("blackbox-record"), 1)
            self.assertEqual(joined_calls.count("convert-file"), 1)
            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")
            self.assertEqual(segmented["segments"][0]["status"], "reused")
            self.assertEqual(segmented["segments"][1]["status"], "success")

    def test_segmented_blackbox_writes_recovery_manifest_when_later_segment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            report = root / "report.md"
            calls: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                calls.append(command)
                joined = " ".join(command)
                if "direct_links_to_mp3.py" in joined:
                    return SimpleNamespace(returncode=2, stdout="no media", stderr="")
                if "blackbox-record" in joined:
                    out = Path(command[command.index("--out") + 1])
                    if out.name.endswith("part002.mp3"):
                        return SimpleNamespace(returncode=9, stdout="", stderr="record failed")
                    out.with_suffix(".fast.m4a").write_bytes(b"fast-segment")
                    return SimpleNamespace(returncode=0, stdout="segment ok", stderr="")
                if "convert-file" in joined:
                    Path(command[command.index("--out") + 1]).write_bytes(b"segment-mp3")
                    return SimpleNamespace(returncode=0, stdout="convert ok", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_verify(path, log, min_duration_seconds=0):
                return {
                    "ok": True,
                    "path": str(path),
                    "bytes": Path(path).stat().st_size,
                    "duration_seconds": min_duration_seconds or 10.0,
                    "min_duration_seconds": min_duration_seconds,
                }

            run = run_auto_pipeline(
                AutoPipelineOptions(
                    url="https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output=output,
                    report=report,
                    mode="auto",
                    work_dir=root / "work",
                    allow_blackbox=True,
                    duration=120,
                    audio_device="system",
                    blackbox_speed=3,
                    segment_seconds=60,
                    min_duration_seconds=120,
                ),
                runner=fake_runner,
                verifier=fake_verify,
            )

            manifest_path = root / "work" / "blackbox-segments" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            segmented = next(route for route in run["routes"] if route["name"] == "segmented_blackbox")

            self.assertFalse(run["mp3_complete"])
            self.assertEqual(segmented["status"], "failed")
            self.assertTrue(manifest["recoverable"])
            self.assertEqual(manifest["completed_segment_count"], 1)
            self.assertEqual(manifest["failed_segment_count"], 1)
            self.assertEqual(manifest["segments"][0]["status"], "success")
            self.assertEqual(manifest["segments"][1]["status"], "failed")
            self.assertEqual(segmented["segments"][0]["status"], "success")
            resume_plan = manifest["resume_plan"]
            self.assertEqual(resume_plan["first_incomplete_segment_index"], 2)
            self.assertEqual(resume_plan["reuse_ready_segment_indices"], [1])
            self.assertEqual(resume_plan["retry_segment_indices"], [2])
            self.assertEqual(resume_plan["same_work_dir_required"], str((root / "work").resolve()))
            self.assertEqual(resume_plan["same_output_required"], str(output.resolve()))
            self.assertIn("--work-dir", resume_plan["command_template"])
            self.assertIn("<same-weixin-url>", resume_plan["command_template"])
            self.assertNotIn("AFfTIp5Ywj", " ".join(resume_plan["command_template"]))
