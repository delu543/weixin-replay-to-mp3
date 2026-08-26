from __future__ import annotations

import tempfile
import unittest
import importlib.util
import json
import io
import os
import sys
import subprocess
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from replay_mp3_studio.extractors import (
    build_weixin_recent_source_file_list,
    find_reusable_songy_artifact,
    find_reusable_songy_mp3,
    generate_weixin_open_packet,
    import_artifact,
    import_artifact_text,
    missing_other_script_message,
    other_script_kind,
    parse_xhs_ids,
    run_blackbox_record,
    run_artifact_text,
    run_other_site,
    run_weixin_manual_playback_capture,
    run_weixin_link,
    run_weixin_profile_state_source,
    walk_media,
    write_weixin_bridge_payload_packet,
)
from replay_mp3_studio.weixin_filehelper import (
    FILEHELPER_ICON_SIGNATURE,
    PROTECTED_FILEHELPER_SIGNATURE,
    WeixinRuntimeStatus,
    WeixinWindowCaptureUnavailable,
    WeixinWindowMetadata,
    _capture_fullscreen_with_screencapture,
    _capture_screen_region,
    _normalize_ocr_observations,
    activate_weixin_main_window,
    close_existing_weixin_video_windows,
    contains_filehelper_text,
    contains_pinned_chat_group_text,
    exact_filehelper_link_click_point_from_ocr,
    filehelper_click_point_from_ocr,
    filehelper_green_icon_probe_passes,
    filehelper_green_icon_region_from_observation,
    inspect_weixin_runtime_status,
    latest_filehelper_link_click_point,
    open_weixin_filehelper,
    parse_weixin_playback_assertions,
    pinned_chat_group_click_point_from_ocr,
    reopen_verified_filehelper_link,
    require_weixin_window_capture_visible,
    require_filehelper_target_verified,
    select_visible_filehelper,
    trigger_weixin_video_playback,
    verify_and_click_latest_filehelper_link,
    weixin_filehelper_applescript,
)
from replay_mp3_studio.config import PLATFORMS
from replay_mp3_studio.jobs import (
    JobStore,
    diagnose_next_action,
    effective_blackbox_speed,
    extract_title_from_url,
    minimum_output_duration_seconds,
)
from replay_mp3_studio.jobs import action_label
from replay_mp3_studio.server import (
    bridge_autopost_js,
    bridge_launcher_html,
    bridge_launcher_manifest,
    content_disposition_for_file,
    reveal_path_in_finder,
)
from replay_mp3_studio.speed_control import (
    media_speed_bookmarklet,
    media_timeline_probe_script,
    speed_snippet_payload,
    summarize_timeline_probe_samples,
)
from replay_mp3_studio.utils import classify_url, is_media_url, parse_course_id, parse_weixin_short_uri, slugify, verify_mp3


JUSTONE_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_justone_to_mp3.py"
justone_spec = importlib.util.spec_from_file_location("weixin_justone_to_mp3", JUSTONE_SCRIPT)
justone_module = importlib.util.module_from_spec(justone_spec)
assert justone_spec.loader is not None
justone_spec.loader.exec_module(justone_module)

SHAREDATA_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_sharedata_feed_to_mp3.py"
sys.path.insert(0, str(SHAREDATA_SCRIPT.parent))
sharedata_spec = importlib.util.spec_from_file_location("weixin_sharedata_feed_to_mp3", SHAREDATA_SCRIPT)
sharedata_module = importlib.util.module_from_spec(sharedata_spec)
sys.modules["weixin_sharedata_feed_to_mp3"] = sharedata_module
assert sharedata_spec.loader is not None
sharedata_spec.loader.exec_module(sharedata_module)

DIRECT_LINKS_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "direct_links_to_mp3.py"
direct_links_spec = importlib.util.spec_from_file_location("direct_links_to_mp3", DIRECT_LINKS_SCRIPT)
direct_links_module = importlib.util.module_from_spec(direct_links_spec)
assert direct_links_spec.loader is not None
direct_links_spec.loader.exec_module(direct_links_module)

OTHER_LINK_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "other_link_to_mp3.py"
other_link_spec = importlib.util.spec_from_file_location("other_link_to_mp3", OTHER_LINK_SCRIPT)
other_link_module = importlib.util.module_from_spec(other_link_spec)
assert other_link_spec.loader is not None
other_link_spec.loader.exec_module(other_link_module)

EXTRACT_MEDIA_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "extract_media_from_artifact.py"
extract_media_spec = importlib.util.spec_from_file_location("extract_media_from_artifact", EXTRACT_MEDIA_SCRIPT)
extract_media_module = importlib.util.module_from_spec(extract_media_spec)
assert extract_media_spec.loader is not None
extract_media_spec.loader.exec_module(extract_media_module)

WEIXIN_OBJECT_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_object_artifact_to_mp3.py"
weixin_object_spec = importlib.util.spec_from_file_location("weixin_object_artifact_to_mp3", WEIXIN_OBJECT_SCRIPT)
weixin_object_module = importlib.util.module_from_spec(weixin_object_spec)
assert weixin_object_spec.loader is not None
weixin_object_spec.loader.exec_module(weixin_object_module)

WEIXIN_REGRESSION_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "weixin_link_regression.py"
weixin_regression_spec = importlib.util.spec_from_file_location("weixin_link_regression", WEIXIN_REGRESSION_SCRIPT)
weixin_regression_module = importlib.util.module_from_spec(weixin_regression_spec)
assert weixin_regression_spec.loader is not None
weixin_regression_spec.loader.exec_module(weixin_regression_module)


class ReplayMp3StudioTests(unittest.TestCase):
    def test_classify_platforms(self) -> None:
        self.assertEqual(
            classify_url("https://www.xiaohongshu.com/fe/live-h5/page/live_replay/570"),
            "xiaohongshu",
        )
        self.assertEqual(classify_url("https://weixin.qq.com/sph/AHCIZNAGQb"), "weixin")
        self.assertEqual(classify_url("https://webapp.songy.info/#/courses/details?course_id=783"), "third_party")
        self.assertEqual(classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "other")

    def test_other_platform_is_available(self) -> None:
        self.assertIn("other", PLATFORMS)
        self.assertEqual(PLATFORMS["other"]["label"], "其他")

    def test_mp3_download_uses_attachment_disposition(self) -> None:
        disposition = content_disposition_for_file(Path("/tmp/final replay.mp3"), download=True)

        self.assertEqual(disposition, 'attachment; filename="final replay.mp3"')
        self.assertIsNone(content_disposition_for_file(Path("/tmp/final replay.mp3"), download=False))

    def test_reveal_path_in_finder_uses_open_reveal(self) -> None:
        target = Path("/tmp/final replay.mp3")
        with (
            patch("replay_mp3_studio.server.platform.system", return_value="Darwin"),
            patch("replay_mp3_studio.server.subprocess.run") as run,
        ):
            reveal_path_in_finder(target)

        run.assert_called_once_with(["open", "-R", str(target)], check=True)

    def test_reveal_path_in_finder_uses_explorer_on_windows(self) -> None:
        target = Path("C:/Users/test/final replay.mp3")
        with (
            patch("replay_mp3_studio.server.platform.system", return_value="Windows"),
            patch("replay_mp3_studio.server.subprocess.run") as run,
        ):
            reveal_path_in_finder(target)

        run.assert_called_once_with(
            ["explorer.exe", f"/select,{target}"], check=True
        )

    def test_static_ui_exposes_download_reveal_and_clickable_classification(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "replay_mp3_studio" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        index_html = (Path(__file__).resolve().parents[1] / "replay_mp3_studio" / "static" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("download=1", app_js)
        self.assertIn("revealFile", app_js)
        self.assertIn("setStatusFilter", app_js)
        self.assertIn("setPlatformFilter", app_js)
        self.assertIn("data-filter-kind", app_js)
        self.assertIn("selectedJobIds", app_js)
        self.assertIn("pauseSelectedJobs", app_js)
        self.assertIn("deleteSelectedJobs", app_js)
        self.assertIn("data-select-job", app_js)
        self.assertIn("outputStatusText", app_js)
        self.assertIn("job.output_exists", app_js)
        self.assertIn("诊断任务 · 不产生 MP3", app_js)
        self.assertIn("weixinOpenModeManual", index_html)
        self.assertIn("weixinPlaybackConfirmedInput", index_html)
        self.assertIn("weixin_manual_playback", app_js)
        self.assertIn("expectedDurationMinutesInput", index_html)
        self.assertIn("min_duration_seconds", app_js)
        self.assertIn("candidateProofText", app_js)

    def test_extract_title_from_url_query_params(self) -> None:
        title = extract_title_from_url(
            "https://example.test/watch?v=123&title=%E5%8D%88%E9%97%B4%E7%9B%B4%E6%92%AD"
        )

        self.assertEqual(title, "午间直播")
        self.assertEqual(extract_title_from_url("https://weixin.qq.com/sph/AHCIZNAGQb"), "")

    def test_job_store_can_pause_and_delete_jobs_from_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            platform_root = root / "weixin"
            run_dir = platform_root / "run"
            run_dir.mkdir(parents=True)
            status = {
                "id": "job-1",
                "platform": "weixin",
                "platform_label": "视频号",
                "action": "convert",
                "action_label": "转 MP3",
                "url": "https://example.test/watch?title=%E6%B5%8B%E8%AF%95%E8%A7%86%E9%A2%91",
                "state": "running",
                "created_at": "2026-07-02T00:00:00+08:00",
                "started_at": "2026-07-02T00:00:01+08:00",
                "finished_at": None,
                "run_dir": str(run_dir),
                "artifact_dir": str(run_dir / "artifacts"),
                "output_path": str(run_dir / "output.mp3"),
                "log_path": str(run_dir / "job.log"),
                "error": "",
                "verify": None,
            }
            (run_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")

            patches = [
                patch("replay_mp3_studio.jobs.PLATFORMS", {"weixin": {"label": "视频号"}}),
                patch("replay_mp3_studio.jobs.platform_folder", lambda _platform: platform_root),
                patch("replay_mp3_studio.jobs.WORK_ROOT", root / "work"),
                patch("replay_mp3_studio.jobs.ensure_layout", lambda: None),
            ]
            with patches[0], patches[1], patches[2], patches[3]:
                store = JobStore()

                pause_result = store.pause_jobs(["job-1"])
                paused = store.get_job("job-1")
                self.assertEqual(pause_result["paused"], ["job-1"])
                self.assertEqual(paused["state"], "paused")
                self.assertEqual(paused["display_title"], "测试视频")

                delete_result = store.delete_jobs(["job-1"])
                self.assertEqual(delete_result["deleted"], ["job-1"])
                self.assertEqual(store.list_jobs(), [])

    def test_job_hydration_exposes_weixin_candidate_proof_without_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "weixin_vendor_source_artifact.json").write_text(
                json.dumps(
                    {
                        "source_kind": "numeric_key_pair",
                        "scan": {"numeric_key_pair_count": 2},
                        "numeric_key_conversion": {
                            "encrypted_bytes": 423307600,
                            "numeric_key_sha256_12": "46c0374c169d",
                        },
                        "numeric_key_pair_summary": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
                                "expected_bytes": 423307600,
                            }
                        ],
                        "verification": {"duration_seconds": 3587.4},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = JobStore()._hydrate_status(  # noqa: SLF001
                {
                    "platform": "weixin",
                    "platform_label": "视频号",
                    "action": "convert",
                    "state": "completed",
                    "artifact_dir": str(artifacts),
                    "output_path": str(root / "output.mp3"),
                }
            )

        encoded = json.dumps(status, ensure_ascii=False)
        self.assertEqual(status["weixin_source_proof"]["encrypted_bytes"], 423307600)
        self.assertEqual(status["weixin_source_proof"]["duration_seconds"], 3587.4)
        self.assertNotIn("token=", encoded)

    def test_parse_course_id_from_fragment(self) -> None:
        self.assertEqual(
            parse_course_id("https://webapp.songy.info/#/courses/details?course_id=783"),
            "783",
        )

    def test_parse_xhs_ids(self) -> None:
        url = (
            "https://www.xiaohongshu.com/fe/live-h5/page/live_replay/570290607425780985"
            "?share_source_id=137945126887283715&host_id=5ce2d0f3000000001700b3c8"
        )
        self.assertEqual(parse_xhs_ids(url), ("137945126887283715", "5ce2d0f3000000001700b3c8"))

    def test_slugify_has_fallback(self) -> None:
        self.assertEqual(slugify(""), "task")
        self.assertTrue(slugify("https://weixin.qq.com/sph/AHCIZNAGQb").endswith("ahciznagqb"))

    def test_parse_weixin_short_uri(self) -> None:
        self.assertEqual(parse_weixin_short_uri("https://weixin.qq.com/sph/AHCIZNAGQb"), "AHCIZNAGQb")
        self.assertEqual(parse_weixin_short_uri("Aa0UXW05IP"), "Aa0UXW05IP")

    def test_weixin_stodownload_is_treated_as_media_url(self) -> None:
        url = "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"

        self.assertTrue(is_media_url(url))
        self.assertEqual(walk_media({"data": {"downloadUrl": url}}), [url])

    def test_weixin_sns_download_urls_are_treated_as_media_urls(self) -> None:
        urls = [
            "https://shzjwxsns.video.qq.com/102/20202/snsvideodownload?token=abc",
            "https://shzjwxsns.video.qq.com/102/20202/snscosdownload?token=abc",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertIn(url, direct_links_module.media_urls({"videoUrl": url}))
                self.assertIn(url, extract_media_module.extract_from_text(f"source={url}"))

    def test_extract_media_converter_tries_next_candidate_after_failure(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.mp3"

            def fake_run(command, check=False, **_kwargs):
                url = command[2]
                calls.append(url)
                if "bad-image" in url:
                    raise subprocess.CalledProcessError(1, command)
                output.write_bytes(b"mp3")
                return SimpleNamespace(returncode=0)

            urls = [
                "https://cdn.example.test/bad-image/snscosdownload?token=image",
                "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def",
            ]
            with patch.object(extract_media_module.subprocess, "run", side_effect=fake_run):
                selected = extract_media_module.convert_first_working(urls, str(output))

            self.assertEqual(selected, urls[1])
            self.assertEqual(calls, urls)
            self.assertTrue(output.exists())

    def test_extract_media_redacts_signed_url_output(self) -> None:
        url = "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"

        self.assertEqual(
            extract_media_module.redact_url(url),
            "https://finder.video.qq.com/251/20302/stodownload?<redacted>",
        )

    def test_other_script_routing(self) -> None:
        self.assertEqual(other_script_kind("https://youtu.be/dQw4w9WgXcQ"), "youtube")
        self.assertEqual(other_script_kind("https://x.com/example/status/123"), "x")
        self.assertEqual(other_script_kind("https://cdn.example.test/audio.mp3"), "direct_media")
        self.assertEqual(other_script_kind("https://example.test/article/123"), "yt_dlp")
        self.assertEqual(other_link_module.script_kind("https://x.com/example/status/123"), "x")
        self.assertEqual(other_script_kind("https://notyoutube.com/watch?v=one"), "yt_dlp")
        self.assertEqual(other_link_module.script_kind("https://notyoutube.com/watch?v=one"), "yt_dlp")
        self.assertEqual(other_script_kind("ftp://example.test/file"), "")
        self.assertIn("只接受", missing_other_script_message("ftp://example.test/file"))

    def test_youtube_command_uses_local_ffmpeg_and_format_fallback(self) -> None:
        command = other_link_module.youtube_attempt_command(
            "https://youtu.be/dQw4w9WgXcQ?si=test",
            "/tmp/download.%(ext)s",
            "android",
            "/opt/ffmpeg",
            sample_seconds=10,
        )

        self.assertIn("--ffmpeg-location", command)
        self.assertEqual(command[command.index("--ffmpeg-location") + 1], "/opt/ffmpeg")
        self.assertIn("--force-ipv4", command)
        self.assertIn("--socket-timeout", command)
        self.assertEqual(command[command.index("--socket-timeout") + 1], "20")
        self.assertIn("-f", command)
        self.assertEqual(command[command.index("-f") + 1], "bestaudio/best")
        self.assertIn("--download-sections", command)
        self.assertEqual(command[command.index("--download-sections") + 1], "*0-10")
        self.assertIn("youtube:player_client=android", command)
        self.assertNotIn("--proxy", command)

    def test_youtube_command_can_use_proxy_without_leaking_credentials(self) -> None:
        command = other_link_module.youtube_attempt_command(
            "https://youtu.be/dQw4w9WgXcQ?si=test",
            "/tmp/download.%(ext)s",
            "",
            "/opt/ffmpeg",
            proxy="http://user:secret@127.0.0.1:7897",
        )

        self.assertIn("--proxy", command)
        self.assertEqual(command[command.index("--proxy") + 1], "http://user:secret@127.0.0.1:7897")
        self.assertIn(
            "http://<auth>@127.0.0.1:7897",
            other_link_module.redact_command(command),
        )

    def test_youtube_proxy_candidates_accept_explicit_proxy(self) -> None:
        self.assertEqual(
            other_link_module.youtube_proxy_candidates("127.0.0.1:7897"),
            ["http://127.0.0.1:7897"],
        )
        self.assertEqual(other_link_module.youtube_proxy_candidates("none"), [""])

    def test_youtube_failure_classifies_cdn_timeout(self) -> None:
        category = other_link_module.classify_youtube_failure(
            [{"stderr_tail": "Connection to tcp://rr3---sn.googlevideo.com:443 failed: Operation timed out"}],
            {"curl_returncode": 28, "curl_summary": "HTTP:000 SIZE:0 TIME:45.0"},
        )

        self.assertEqual(category, "youtube_cdn_unreachable_or_timed_out")

    def test_other_site_can_pass_sample_seconds_for_api_smoke(self) -> None:
        commands = []

        def fake_run_streaming(command, log):
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch("replay_mp3_studio.extractors.run_streaming", side_effect=fake_run_streaming):
                run_other_site(
                    "https://youtu.be/dQw4w9WgXcQ",
                    root / "output.mp3",
                    root / "artifacts",
                    lambda message: None,
                    sample_seconds=15,
                )

        self.assertEqual(len(commands), 1)
        self.assertIn("--sample-seconds", commands[0])
        self.assertEqual(commands[0][commands[0].index("--sample-seconds") + 1], "15")

    def test_weixin_blackbox_opens_with_wechat_and_disables_default_open(self) -> None:
        commands = []

        def fake_run_streaming(command, log, cwd=None):
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.open_weixin_target",
            return_value={"method": "weixin_scheme", "short_uri": "AKJkWTAlIN"},
        ) as open_target, patch("replay_mp3_studio.extractors.time.sleep") as sleep, patch(
            "replay_mp3_studio.extractors.run_streaming",
            side_effect=fake_run_streaming,
        ):
            root = Path(tmpdir)
            output = root / "out.mp3"
            output.with_suffix(".blackbox.json").write_text("{}", encoding="utf-8")
            run_blackbox_record(
                "https://weixin.qq.com/sph/AKJkWTAlIN",
                output,
                root / "artifacts",
                lambda _message: None,
                duration=30,
                speed=3,
                audio_device="system",
            )

        open_target.assert_called_once()
        sleep.assert_called_once_with(6)
        self.assertEqual(len(commands), 1)
        self.assertIn("--no-open", commands[0])

    def test_weixin_filehelper_script_targets_file_transfer_assistant(self) -> None:
        script = weixin_filehelper_applescript(click_after_send=True)

        self.assertIn("文件传输助手", script)
        self.assertIn('application "WeChat"', script)
        self.assertIn("AXRaise", script)
        self.assertIn('menu item "微信" of menu 1 of menu bar item "窗口"', script)
        self.assertIn("clicked_latest", script)
        self.assertIn("previousClipboard", script)
        self.assertIn("window_x", script)
        self.assertNotIn("set the clipboard to assistantName", script)
        self.assertNotIn("selectedChatVerified", script)
        self.assertNotIn("selected_chat_verified", script)
        self.assertNotIn("winH - 230", script)
        self.assertIn('if exists window assistantName then', script)
        self.assertIn("winH - 98", script)
        self.assertNotIn("winH - 58", script)
        self.assertIn('keystroke "a" using {command down}', script)
        self.assertIn("key code 36", script)

    def test_activate_weixin_main_window_uses_window_menu_reveal_before_erroring(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(
                returncode=0,
                stdout='{"x":0,"y":36,"width":624,"height":861}\n',
                stderr="",
            )

        with patch("replay_mp3_studio.weixin_filehelper.subprocess.run", side_effect=fake_run):
            activate_weixin_main_window()

        script = calls[0][0][2]
        self.assertIn('application id "com.tencent.xinWeChat"', script)
        self.assertIn('bundle identifier is "com.tencent.xinWeChat"', script)
        self.assertIn("repeat 20 times", script)
        self.assertIn('menu item "微信" of menu 1 of menu bar item "窗口"', script)
        self.assertIn("WeChat window not found", script)

    def test_latest_filehelper_link_click_point_matches_visible_latest_bubble(self) -> None:
        point = latest_filehelper_link_click_point({"x": 0, "y": 36, "width": 624, "height": 861})

        self.assertEqual(point, (450, 730))

    def test_exact_link_ocr_chooses_newest_matching_short_uri(self) -> None:
        window = {"x": 0, "y": 36, "width": 624, "height": 861}
        observations = [
            {"text": "AWbb8Gxj9X", "x": 20, "y": 300, "width": 100, "height": 20},
            {"text": "其他链接", "x": 30, "y": 600, "width": 100, "height": 20},
            {"text": "AWbb8Gxj9X", "x": 40, "y": 500, "width": 120, "height": 30},
        ]

        point = exact_filehelper_link_click_point_from_ocr(
            window,
            "https://weixin.qq.com/sph/AWbb8Gxj9X",
            observations,
        )

        self.assertEqual(point, (350, 641))

    def test_filehelper_click_point_uses_ocr_match_not_first_row(self) -> None:
        region = (72, 90, 245, 700)
        observations = [
            {"text": "鸡你太美 咕咕嘎嘎", "x": 30, "y": 80, "width": 150, "height": 26},
            {"text": "文件传输助手", "x": 72, "y": 166, "width": 120, "height": 26},
        ]

        point = filehelper_click_point_from_ocr(region, observations)

        self.assertEqual(point, (204, 269))

    def test_filehelper_ocr_coordinates_normalize_retina_pixels(self) -> None:
        region = (72, 90, 245, 700)
        observations = [
            {
                "text": "文件传输助手",
                "imageWidth": 490,
                "imageHeight": 1400,
                "x": 144,
                "y": 332,
                "width": 240,
                "height": 52,
            },
        ]

        normalized = _normalize_ocr_observations(observations, region)
        point = filehelper_click_point_from_ocr(region, normalized)

        self.assertEqual(point, (204, 269))

    def test_capture_screen_region_uses_fullscreen_capture_then_crop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image = Path(tmpdir) / "region.png"
            calls = []

            def fake_fullscreen(output, *, timeout):
                calls.append(("fullscreen", output.name, timeout))
                output.write_bytes(b"fullscreen")

            def fake_crop(fullscreen, _region, output, *, timeout):
                calls.append(("crop", fullscreen.name, _region, output.name, timeout))
                output.write_bytes(b"png")

            with patch(
                "replay_mp3_studio.weixin_filehelper._capture_fullscreen_with_screencapture",
                side_effect=fake_fullscreen,
            ), patch(
                "replay_mp3_studio.weixin_filehelper._crop_fullscreen_image_region",
                side_effect=fake_crop,
            ):
                _capture_screen_region((72, 90, 245, 700), image, timeout=15)

        self.assertEqual(calls[0][0], "fullscreen")
        self.assertEqual(calls[1][0], "crop")
        self.assertEqual(calls[1][2], (72, 90, 245, 700))

    def test_require_weixin_window_capture_visible_reports_blocked_sharing_state(self) -> None:
        with patch(
            "replay_mp3_studio.weixin_filehelper.weixin_window_capture_state",
            return_value={"found": True, "sharing_state": 0, "owner_name": "微信", "window_name": "微信"},
        ):
            with self.assertRaisesRegex(WeixinWindowCaptureUnavailable, "window_sharing_state=0"):
                require_weixin_window_capture_visible({"x": 0, "y": 33, "width": 624, "height": 865})

    def test_weixin_runtime_probe_uses_windowserver_when_ax_omits_windows(self) -> None:
        def fake_run(command, **_kwargs):
            if command[0] == "ps":
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "100 1 /Applications/微信.app/Contents/MacOS/WeChat\n"
                        "101 100 /Applications/微信.app/Contents/Frameworks/"
                        "WeChatAppEx.app/Contents/MacOS/WeChatAppEx\n"
                    ),
                    stderr="",
                )
            if command[0] == "ioreg":
                return SimpleNamespace(returncode=0, stdout='"IOConsoleLocked" = No\n', stderr="")
            if command[0] == "osascript":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[0] == "swift":
                return SimpleNamespace(
                    returncode=0,
                    stdout="微信\t0\t36\t624\t861\tfalse\n视频号\t20\t40\t600\t800\tfalse\n",
                    stderr="",
                )
            raise AssertionError(command)

        with patch("replay_mp3_studio.weixin_filehelper.sys.platform", "darwin"), patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
            side_effect=fake_run,
        ):
            status = inspect_weixin_runtime_status()

        self.assertEqual(status.state, "ready")
        self.assertTrue(status.app_running)
        self.assertTrue(status.renderer_running)
        self.assertEqual(status.capture_strategy, "windowserver_metadata_after_missing_ax")
        self.assertEqual([window.title_kind for window in status.windows], ["main", "video"])

    def test_screencapture_timeout_is_not_treated_as_wechat_exit(self) -> None:
        status = WeixinRuntimeStatus(
            state="ready",
            app_running=True,
            renderer_running=True,
            screen_locked=False,
            windows=(WeixinWindowMetadata("微信", 0, 36, 624, 861),),
            capture_strategy="windowserver_metadata_after_missing_ax",
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["screencapture"], timeout=8),
        ), patch(
            "replay_mp3_studio.weixin_filehelper.inspect_weixin_runtime_status",
            return_value=status,
        ):
            with self.assertRaises(WeixinWindowCaptureUnavailable) as raised:
                _capture_fullscreen_with_screencapture(Path(tmpdir) / "screen.png", timeout=8)

        diagnostics = raised.exception.safe_diagnostics()
        self.assertEqual(diagnostics["state"], "ready")
        self.assertTrue(diagnostics["renderer_running"])
        self.assertEqual(diagnostics["failure_kind"], "weixin_window_capture_unavailable")

    def test_filehelper_green_icon_region_is_left_of_verified_name(self) -> None:
        region = (72, 90, 245, 700)
        observation = {"text": "文件传输助手", "x": 72, "y": 166, "width": 120, "height": 26}

        icon_region = filehelper_green_icon_region_from_observation(region, observation)

        self.assertEqual(icon_region, (84, 246, 46, 46))

    def test_filehelper_green_icon_probe_requires_green_pixels(self) -> None:
        self.assertTrue(
            filehelper_green_icon_probe_passes(
                {
                    "green_pixels": 260,
                    "white_pixels": 42,
                    "green_ratio": 0.12,
                    "white_ratio": 0.02,
                    "green_colored_ratio": 0.50,
                }
            )
        )
        self.assertFalse(
            filehelper_green_icon_probe_passes(
                {
                    "green_pixels": 20,
                    "white_pixels": 42,
                    "green_ratio": 0.01,
                    "white_ratio": 0.02,
                    "green_colored_ratio": 0.05,
                }
            )
        )
        self.assertFalse(
            filehelper_green_icon_probe_passes(
                {
                    "green_pixels": 260,
                    "white_pixels": 0,
                    "green_ratio": 0.12,
                    "white_ratio": 0.0,
                    "green_colored_ratio": 0.50,
                }
            )
        )

    def test_filehelper_target_verification_requires_name_header_and_green_icon(self) -> None:
        payload = {
            "selected_chat_title": "文件传输助手",
            "selected_chat_verified": True,
            "filehelper_name_ocr_text": "文件传输助手",
            "filehelper_name_verified": True,
            "selected_header_ocr_text": "文件传输助手",
            "filehelper_header_verified": True,
            "filehelper_icon_verified": True,
            "filehelper_icon_signature": FILEHELPER_ICON_SIGNATURE,
        }

        require_filehelper_target_verified(payload)

        for key in (
            "filehelper_name_ocr_text",
            "filehelper_name_verified",
            "selected_header_ocr_text",
            "filehelper_header_verified",
            "filehelper_icon_verified",
            "filehelper_icon_signature",
        ):
            with self.subTest(key=key):
                broken = dict(payload)
                broken[key] = False if key.endswith("_verified") else ""
                with self.assertRaisesRegex(RuntimeError, "File Transfer Assistant target verification failed"):
                    require_filehelper_target_verified(broken)

    def test_filehelper_target_verification_accepts_exact_protected_ax_window_gate(self) -> None:
        payload = {
            "selected_chat_title": "文件传输助手",
            "selected_chat_verified": True,
            "protected_window_metadata_verified": True,
            "exact_window_title_verified": True,
            "protected_filehelper_signature": PROTECTED_FILEHELPER_SIGNATURE,
        }

        require_filehelper_target_verified(payload)

        for key in (
            "selected_chat_title",
            "selected_chat_verified",
            "protected_window_metadata_verified",
            "exact_window_title_verified",
            "protected_filehelper_signature",
        ):
            with self.subTest(key=key):
                broken = dict(payload)
                broken[key] = False if key.endswith("verified") else ""
                with self.assertRaisesRegex(RuntimeError, "File Transfer Assistant target verification failed"):
                    require_filehelper_target_verified(broken)

    def test_playback_assertions_require_audio_and_video_wake_lock(self) -> None:
        both = parse_weixin_playback_assertions(
            'pid 123(WeChatAppEx): NoIdleSleepAssertion named: "Playing audio"\n'
            'pid 123(WeChatAppEx): NoDisplaySleepAssertion named: "Video Wake Lock"\n'
        )
        audio_only = parse_weixin_playback_assertions(
            'pid 123(WeChatAppEx): NoIdleSleepAssertion named: "Playing audio"\n'
        )
        unrelated = parse_weixin_playback_assertions(
            'pid 456(Safari): NoDisplaySleepAssertion named: "Video Wake Lock"\n'
        )

        self.assertTrue(both["playback_verified"])
        self.assertFalse(audio_only["playback_verified"])
        self.assertFalse(unrelated["playback_verified"])

    def test_trigger_playback_skips_click_when_autoplay_is_already_verified(self) -> None:
        video = WeixinWindowMetadata("微信 (窗口)", 0, 38, 624, 858)
        before_activation = []
        assertions = {
            "playing_audio": True,
            "video_wake_lock": True,
            "playback_verified": True,
            "evidence_source": "pmset_assertion_metadata",
        }
        with patch(
            "replay_mp3_studio.weixin_filehelper.wait_for_weixin_video_window",
            return_value=video,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.inspect_weixin_playback_assertions",
            return_value=assertions,
        ), patch(
            "replay_mp3_studio.weixin_filehelper._click_screen_point",
        ) as click:
            result = trigger_weixin_video_playback(
                before_activation=lambda: before_activation.append("called"),
            )

        click.assert_not_called()
        self.assertEqual(before_activation, [])
        self.assertTrue(result["playback_verified"])
        self.assertEqual(result["activation_method"], "autoplay")

    def test_trigger_playback_takes_baseline_hook_only_before_manual_click(self) -> None:
        video = WeixinWindowMetadata("微信 (窗口)", 0, 38, 624, 858)
        events = []
        initial = {
            "playing_audio": False,
            "video_wake_lock": False,
            "playback_verified": False,
        }
        verified = {
            "playing_audio": True,
            "video_wake_lock": True,
            "playback_verified": True,
        }

        def click(*_args, **_kwargs):
            events.append("click")

        with patch(
            "replay_mp3_studio.weixin_filehelper.wait_for_weixin_video_window",
            return_value=video,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.inspect_weixin_playback_assertions",
            return_value=initial,
        ), patch(
            "replay_mp3_studio.weixin_filehelper._command_output",
            return_value="",
        ), patch(
            "replay_mp3_studio.weixin_filehelper._click_screen_point",
            side_effect=click,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.wait_for_weixin_playback_assertions",
            return_value=verified,
        ):
            result = trigger_weixin_video_playback(
                before_activation=lambda: events.append("baseline"),
            )

        self.assertEqual(events, ["baseline", "click"])
        self.assertTrue(result["playback_verified"])

    def test_pinned_chat_group_click_point_is_not_treated_as_filehelper(self) -> None:
        region = (72, 90, 245, 700)
        observations = [
            {"text": "28 个置顶聊天", "x": 68, "y": 648, "width": 118, "height": 28},
        ]

        self.assertTrue(contains_pinned_chat_group_text("28 个置顶聊天"))
        self.assertFalse(contains_filehelper_text("28 个置顶聊天"))
        self.assertEqual(pinned_chat_group_click_point_from_ocr(region, observations), (237, 752))

    def test_filehelper_text_match_is_strict(self) -> None:
        self.assertTrue(contains_filehelper_text("文件传输助手 15:32"))
        self.assertFalse(contains_filehelper_text("鸡你太美 咕咕嘎嘎 (241)"))

    def test_close_existing_weixin_video_windows_targets_video_window_only(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("replay_mp3_studio.weixin_filehelper.subprocess.run", side_effect=fake_run):
            result = close_existing_weixin_video_windows()

        self.assertTrue(result["attempted"])
        self.assertIn('window "微信 (窗口)"', calls[0][0][2])
        self.assertIn("button 1", calls[0][0][2])

    def test_open_weixin_filehelper_runs_osascript_without_shell(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"ok":true,"method":"file_transfer_assistant","clicked_latest":false,'
                    '"window_x":0,"window_y":36,"window_width":624,"window_height":861}\n'
                ),
                stderr="",
            )

        with patch("replay_mp3_studio.weixin_filehelper.subprocess.run", side_effect=fake_run), patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=None,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
            return_value={
                "selected_chat_title": "文件传输助手",
                "selected_chat_verified": True,
                "filehelper_name_ocr_text": "文件传输助手",
                "filehelper_name_verified": True,
                "selected_header_ocr_text": "文件传输助手",
                "filehelper_header_verified": True,
                "filehelper_icon_verified": True,
                "filehelper_icon_signature": FILEHELPER_ICON_SIGNATURE,
                "window_x": 0,
                "window_y": 36,
                "window_width": 624,
                "window_height": 861,
            },
        ) as select_visible, patch(
            "replay_mp3_studio.weixin_filehelper.verify_and_click_latest_filehelper_link",
            return_value={
                "message_copyback_verified": True,
                "message_copyback_match": True,
                "clicked_latest": True,
            },
        ) as verify_latest, patch(
            "replay_mp3_studio.weixin_filehelper.close_existing_weixin_video_windows",
        ) as close_video:
            result = open_weixin_filehelper("https://weixin.qq.com/sph/AKJkWTAlIN")

        select_visible.assert_called_once()
        verify_latest.assert_called_once()
        close_video.assert_not_called()
        self.assertEqual(result["method"], "file_transfer_assistant")
        self.assertEqual(calls[0][0][0], "osascript")
        self.assertEqual(calls[0][0][-1], "https://weixin.qq.com/sph/AKJkWTAlIN")
        self.assertTrue(calls[0][1]["capture_output"])
        self.assertTrue(result["clicked_latest"])
        self.assertTrue(result["sent_new_message"])
        self.assertFalse(result["closed_existing_video_window"])

    def test_latest_message_copyback_mismatch_refuses_old_link_click(self) -> None:
        clicks = []

        def record_click(x, y, **kwargs):
            clicks.append((x, y, kwargs.get("button", "left"), kwargs.get("label")))

        with patch(
            "replay_mp3_studio.weixin_filehelper._ensure_sck_display_exact_text",
        ), patch(
            "replay_mp3_studio.weixin_filehelper._click_screen_point",
            side_effect=record_click,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.display_exact_text_click_point",
            return_value=(500, 600),
        ), patch(
            "replay_mp3_studio.weixin_filehelper._read_plain_clipboard",
            side_effect=["before", "https://weixin.qq.com/sph/AWbb8Gxj9X"],
        ), patch(
            "replay_mp3_studio.weixin_filehelper._write_plain_clipboard",
        ):
            with self.assertRaisesRegex(RuntimeError, "stale or wrong link"):
                verify_and_click_latest_filehelper_link(
                    {"x": 436, "y": 158, "width": 598, "height": 640},
                    "https://weixin.qq.com/sph/A1TN6kx8js",
                )

        self.assertEqual([row[2] for row in clicks], ["right", "left"])
        self.assertFalse(any(row[3] == "Verified latest Weixin link" for row in clicks))

    def test_latest_message_copyback_exact_url_allows_link_click(self) -> None:
        clicks = []

        def record_click(x, y, **kwargs):
            clicks.append((x, y, kwargs.get("button", "left"), kwargs.get("label")))

        url = "https://weixin.qq.com/sph/A1TN6kx8js"
        with patch(
            "replay_mp3_studio.weixin_filehelper._ensure_sck_display_exact_text",
        ), patch(
            "replay_mp3_studio.weixin_filehelper._click_screen_point",
            side_effect=record_click,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.display_exact_text_click_point",
            return_value=(500, 600),
        ), patch(
            "replay_mp3_studio.weixin_filehelper._read_plain_clipboard",
            side_effect=["before", url],
        ), patch(
            "replay_mp3_studio.weixin_filehelper._write_plain_clipboard",
        ):
            result = verify_and_click_latest_filehelper_link(
                {"x": 436, "y": 158, "width": 598, "height": 640},
                url,
            )

        self.assertEqual([row[2] for row in clicks], ["right", "left", "left"])
        self.assertEqual(clicks[-1][3], "Verified latest Weixin link")
        self.assertTrue(result["message_copyback_verified"])
        self.assertEqual(result["verified_short_uri"], "A1TN6kx8js")

    def test_vpn_retry_reuses_verified_message_without_resending(self) -> None:
        window = WeixinWindowMetadata("文件传输助手", 436, 158, 598, 640)
        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=window,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.verify_and_click_latest_filehelper_link",
            return_value={"message_copyback_verified": True, "clicked_latest": True},
        ) as verify_latest, patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
        ) as select_visible, patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
        ) as subprocess_run:
            result = reopen_verified_filehelper_link(
                "https://weixin.qq.com/sph/A1TN6kx8js",
            )

        verify_latest.assert_called_once()
        select_visible.assert_not_called()
        subprocess_run.assert_not_called()
        self.assertFalse(result["sent_new_message"])
        self.assertTrue(result["reused_verified_message"])

    def test_open_weixin_filehelper_reuses_exact_latest_message_without_send(self) -> None:
        url = "https://weixin.qq.com/sph/A1TN6kx8js"
        window = WeixinWindowMetadata("文件传输助手", 436, 158, 598, 640)
        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=window,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.verify_and_click_latest_filehelper_link",
            return_value={"message_copyback_verified": True, "clicked_latest": True},
        ) as verify_latest, patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
        ) as select_visible, patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
        ) as subprocess_run:
            result = open_weixin_filehelper(url)

        verify_latest.assert_called_once()
        select_visible.assert_not_called()
        subprocess_run.assert_not_called()
        self.assertFalse(result["sent_new_message"])
        self.assertTrue(result["reused_verified_message"])

    def test_open_weixin_filehelper_sends_once_only_after_readable_mismatch(self) -> None:
        from replay_mp3_studio.weixin_filehelper import FilehelperLatestMessageMismatch

        url = "https://weixin.qq.com/sph/A1TN6kx8js"
        window = WeixinWindowMetadata("文件传输助手", 436, 158, 598, 640)
        selected = {
            "selected_chat_title": "文件传输助手",
            "selected_chat_verified": True,
            "filehelper_name_ocr_text": "文件传输助手",
            "filehelper_name_verified": True,
            "selected_header_ocr_text": "文件传输助手",
            "filehelper_header_verified": True,
            "filehelper_icon_verified": True,
            "filehelper_icon_signature": FILEHELPER_ICON_SIGNATURE,
            "window_x": 0,
            "window_y": 36,
            "window_width": 624,
            "window_height": 861,
        }
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout='{"ok":true}\n', stderr="")

        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=window,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.verify_and_click_latest_filehelper_link",
            side_effect=[
                FilehelperLatestMessageMismatch("stale or wrong link"),
                {"message_copyback_verified": True, "clicked_latest": True},
            ],
        ) as verify_latest, patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
            return_value=selected,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
            side_effect=fake_run,
        ):
            result = open_weixin_filehelper(url)

        self.assertEqual(verify_latest.call_count, 2)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["sent_new_message"])
        self.assertFalse(result["reused_verified_message"])

    def test_open_weixin_filehelper_does_not_send_when_reuse_verification_breaks(self) -> None:
        url = "https://weixin.qq.com/sph/A1TN6kx8js"
        window = WeixinWindowMetadata("文件传输助手", 436, 158, 598, 640)
        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=window,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.verify_and_click_latest_filehelper_link",
            side_effect=RuntimeError("copyback unavailable"),
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
        ) as select_visible, patch(
            "replay_mp3_studio.weixin_filehelper.subprocess.run",
        ) as subprocess_run:
            with self.assertRaisesRegex(RuntimeError, "copyback unavailable"):
                open_weixin_filehelper(url)

        select_visible.assert_not_called()
        subprocess_run.assert_not_called()

    def test_protected_capture_routes_to_pinned_ax_title_scan(self) -> None:
        capture_error = WeixinWindowCaptureUnavailable(
            "protected pixels",
            runtime_status=WeixinRuntimeStatus(
                state="ready",
                app_running=True,
                renderer_running=True,
                screen_locked=False,
                windows=(WeixinWindowMetadata("微信", 0, 33, 627, 864),),
                capture_strategy="windowserver_metadata_after_missing_ax",
            ),
            capture_state={"sharing_state": 0},
        )
        protected_payload = {
            "selected_chat_title": "文件传输助手",
            "selected_chat_verified": True,
            "protected_window_metadata_verified": True,
            "exact_window_title_verified": True,
            "protected_filehelper_signature": PROTECTED_FILEHELPER_SIGNATURE,
        }
        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=None,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.activate_weixin_main_window",
            return_value={"x": 0, "y": 33, "width": 627, "height": 864},
        ), patch(
            "replay_mp3_studio.weixin_filehelper.require_weixin_window_capture_visible",
            side_effect=capture_error,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_protected_filehelper_from_pinned_rows",
            return_value=protected_payload,
        ) as protected_scan, patch(
            "replay_mp3_studio.weixin_filehelper.keyboard_select_filehelper",
        ) as keyboard_search:
            result = select_visible_filehelper()

        protected_scan.assert_called_once()
        keyboard_search.assert_not_called()
        self.assertEqual(result["selected_chat_title"], "文件传输助手")

    def test_open_weixin_filehelper_refuses_missing_green_icon_before_send(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout='{"ok":true}\n', stderr="")

        with patch("replay_mp3_studio.weixin_filehelper.subprocess.run", side_effect=fake_run), patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=None,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
            return_value={
                "selected_chat_title": "文件传输助手",
                "selected_chat_verified": True,
                "filehelper_name_ocr_text": "文件传输助手",
                "filehelper_name_verified": True,
                "selected_header_ocr_text": "文件传输助手",
                "filehelper_header_verified": True,
                "filehelper_icon_verified": False,
                "filehelper_icon_signature": "",
                "window_x": 0,
                "window_y": 36,
                "window_width": 624,
                "window_height": 861,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "green_icon_verified=False"):
                open_weixin_filehelper("https://weixin.qq.com/sph/AKJkWTAlIN")

        self.assertEqual(calls, [])

    def test_open_weixin_filehelper_refuses_unverified_target_chat(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(
                returncode=0,
                stdout='{"ok":true}\n',
                stderr="",
            )

        with patch("replay_mp3_studio.weixin_filehelper.subprocess.run", side_effect=fake_run), patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=None,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
            side_effect=RuntimeError("File Transfer Assistant target verification failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "File Transfer Assistant target verification failed"):
                open_weixin_filehelper("https://weixin.qq.com/sph/AKJkWTAlIN")

        self.assertEqual(calls, [])

    def test_open_weixin_filehelper_does_not_close_video_before_capture_verification(self) -> None:
        status = WeixinRuntimeStatus(
            state="ready",
            app_running=True,
            renderer_running=True,
            screen_locked=False,
            windows=(WeixinWindowMetadata("视频号", 0, 36, 624, 861),),
            capture_strategy="windowserver_metadata_after_missing_ax",
        )
        capture_error = WeixinWindowCaptureUnavailable(
            "protected pixels",
            runtime_status=status,
        )
        with patch(
            "replay_mp3_studio.weixin_filehelper.raise_exact_filehelper_window",
            return_value=None,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.select_visible_filehelper",
            side_effect=capture_error,
        ), patch(
            "replay_mp3_studio.weixin_filehelper.close_existing_weixin_video_windows",
        ) as close_video:
            with self.assertRaises(WeixinWindowCaptureUnavailable):
                open_weixin_filehelper("https://weixin.qq.com/sph/AKJkWTAlIN")

        close_video.assert_not_called()

    def test_open_weixin_target_auto_does_not_fall_back_to_scheme_if_filehelper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.open_weixin_filehelper",
            side_effect=RuntimeError("not frontmost"),
        ), patch(
            "replay_mp3_studio.extractors.generate_weixin_open_packet",
        ) as generate_packet, patch(
            "replay_mp3_studio.extractors.subprocess.run",
        ) as subprocess_run:
            from replay_mp3_studio.extractors import open_weixin_target

            with self.assertRaisesRegex(RuntimeError, "no scheme/default-browser fallback"):
                open_weixin_target(
                    "https://weixin.qq.com/sph/AKJkWTAlIN",
                    Path(tmpdir),
                    lambda _message: None,
                )

        generate_packet.assert_not_called()
        subprocess_run.assert_not_called()

    def test_open_weixin_target_auto_refuses_scheme_for_capture_unavailable(self) -> None:
        commands = []
        status = WeixinRuntimeStatus(
            state="ready",
            app_running=True,
            renderer_running=True,
            screen_locked=False,
            windows=(WeixinWindowMetadata("微信", 0, 36, 624, 861),),
            capture_strategy="windowserver_metadata_after_missing_ax",
        )
        capture_error = WeixinWindowCaptureUnavailable(
            "protected pixels",
            runtime_status=status,
        )
        def fake_subprocess_run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.open_weixin_filehelper",
            side_effect=capture_error,
        ), patch(
            "replay_mp3_studio.extractors.generate_weixin_open_packet",
        ) as generate_packet, patch(
            "replay_mp3_studio.extractors.subprocess.run",
            side_effect=fake_subprocess_run,
        ):
            from replay_mp3_studio.extractors import open_weixin_target

            with self.assertRaisesRegex(RuntimeError, "no scheme or browser fallback"):
                open_weixin_target(
                    "https://weixin.qq.com/sph/AKJkWTAlIN",
                    Path(tmpdir),
                    lambda _message: None,
                )

        generate_packet.assert_not_called()
        self.assertEqual(commands, [])

    def test_open_weixin_target_allows_explicit_scheme_method(self) -> None:
        commands = []
        packet = {
            "short_uri": "AKJkWTAlIN",
            "packet_dir": "/tmp/packet",
            "packet": {"weixin_scheme": "weixin://dl/test"},
        }

        def fake_subprocess_run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.open_weixin_filehelper",
            side_effect=RuntimeError("not frontmost"),
        ), patch(
            "replay_mp3_studio.extractors.generate_weixin_open_packet",
            return_value=packet,
        ), patch(
            "replay_mp3_studio.extractors.subprocess.run",
            side_effect=fake_subprocess_run,
        ):
            from replay_mp3_studio.extractors import open_weixin_target

            result = open_weixin_target(
                "https://weixin.qq.com/sph/AKJkWTAlIN",
                Path(tmpdir),
                lambda _message: None,
                method="scheme",
            )

        self.assertEqual(result["method"], "weixin_scheme")
        self.assertEqual(
            commands[-1],
            ["open", "-b", "com.tencent.xinWeChat", "weixin://dl/test"],
        )

    def test_open_weixin_target_respects_strict_filehelper_environment(self) -> None:
        status = WeixinRuntimeStatus(
            state="ready",
            app_running=True,
            renderer_running=True,
            screen_locked=False,
            windows=(WeixinWindowMetadata("微信", 0, 36, 624, 861),),
            capture_strategy="windowserver_metadata_after_missing_ax",
        )
        capture_error = WeixinWindowCaptureUnavailable(
            "protected pixels",
            runtime_status=status,
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {"WEIXIN_OPEN_METHOD": "filehelper"},
        ), patch(
            "replay_mp3_studio.extractors.open_weixin_filehelper",
            side_effect=capture_error,
        ), patch(
            "replay_mp3_studio.extractors.generate_weixin_open_packet",
        ) as generate_packet:
            from replay_mp3_studio.extractors import open_weixin_target

            with self.assertRaises(WeixinWindowCaptureUnavailable):
                open_weixin_target(
                    "https://weixin.qq.com/sph/AKJkWTAlIN",
                    Path(tmpdir),
                    lambda _message: None,
                )

        generate_packet.assert_not_called()

    def test_weixin_profile_state_source_uses_targeted_scanner(self) -> None:
        commands = []

        def fake_run_streaming(command, log):
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.run_streaming",
            side_effect=fake_run_streaming,
        ):
            root = Path(tmpdir)
            run_weixin_profile_state_source(
                root / "output.mp3",
                root / "artifacts",
                lambda _message: None,
                duration=12,
                min_duration=5,
            )

        self.assertEqual(len(commands), 1)
        self.assertIn("weixin_profile_state_to_mp3.py", " ".join(commands[0]))
        self.assertIn("--duration", commands[0])
        self.assertEqual(commands[0][commands[0].index("--duration") + 1], "12")
        self.assertIn("--min-duration", commands[0])
        self.assertEqual(commands[0][commands[0].index("--min-duration") + 1], "5")

    def test_weixin_open_packet_generation_has_hard_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "replay_mp3_studio.extractors.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=45),
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out after 45s"):
                generate_weixin_open_packet(
                    "https://weixin.qq.com/sph/Aa0UXW05IP",
                    Path(tmpdir),
                    lambda _message: None,
                )

    def test_weixin_bridge_autopost_uses_snake_case_transfer_fields(self) -> None:
        script = bridge_autopost_js("http://127.0.0.1:8768/api/receive-artifact", "export/test", noprompt=True).decode()

        self.assertIn("finder_basereq", script)
        self.assertIn("encrypted_objectid", script)
        self.assertIn("live_id", script)
        self.assertIn("/finder-preview/api/feed/get_feed_info", script)
        self.assertIn("weixin_bridge_feed_info", script)
        self.assertIn("finderH5Auth", script)
        self.assertNotIn("encryptedObjectid", script)
        self.assertNotIn("finderBasereq", script)

    def test_weixin_bridge_launcher_includes_lan_candidate(self) -> None:
        manifest = bridge_launcher_manifest(
            "127.0.0.1:8765",
            8765,
            "autorun=1&noprompt=1&short_uri=Aa0UXW05IP",
            lan_addresses=["192.168.8.20"],
        )
        candidates = manifest["candidates"]

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["host"], "127.0.0.1:8765")
        self.assertEqual(candidates[1]["host"], "192.168.8.20:8765")
        self.assertIn("/weixin-bridge-autopost?autorun=1&noprompt=1&short_uri=Aa0UXW05IP", candidates[1]["bridge_page_url"])
        self.assertIn("/api/weixin/bridge-autopost-snippet?noprompt=1&short_uri=Aa0UXW05IP", candidates[1]["bridge_snippet_url"])
        self.assertIn("/api/weixin/runtime-capture-snippet", candidates[1]["runtime_capture_snippet_url"])
        self.assertEqual(candidates[1]["receive_artifact_url"], "http://192.168.8.20:8765/api/receive-artifact")

    def test_weixin_bridge_launcher_html_contains_copyable_urls(self) -> None:
        manifest = bridge_launcher_manifest(
            "localhost:8765",
            8765,
            "autorun=1&noprompt=1&eid=export%2Ftest",
            lan_addresses=["192.168.8.20"],
        )
        html = bridge_launcher_html(manifest).decode()

        self.assertIn("Weixin Bridge Launcher", html)
        self.assertIn("http://192.168.8.20:8765/weixin-bridge-autopost?", html)
        self.assertIn("Runtime Capture JS", html)
        self.assertIn("runtime-capture-snippet", html)
        self.assertIn("api.qrserver.com", html)

    def test_speed_snippet_forces_html_media_playback_rate(self) -> None:
        payload = speed_snippet_payload("8")

        self.assertEqual(payload["speed"], 8.0)
        self.assertIn("playbackRate", payload["snippet"])
        self.assertIn("MutationObserver", payload["snippet"])
        self.assertIn("javascript:", payload["bookmarklet"])
        self.assertIn("8", media_speed_bookmarklet(8))
        self.assertIn("timeline_probe_snippet", payload)

    def test_media_timeline_probe_script_samples_actual_current_time(self) -> None:
        script = media_timeline_probe_script(8, sample_seconds=1.5)

        self.assertIn("performance.now", script)
        self.assertIn("currentTime", script)
        self.assertIn("playbackRate", script)
        self.assertNotIn("document.cookie", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        self.assertNotIn("indexedDB", script)

    def test_timeline_probe_summary_accepts_actual_near_requested_speed(self) -> None:
        summary = summarize_timeline_probe_samples(
            [
                {"wall_ms": 0, "media_time": 0.0},
                {"wall_ms": 500, "media_time": 3.95},
                {"wall_ms": 1000, "media_time": 7.9},
            ],
            requested_speed=8,
        )

        self.assertTrue(summary["stable"])
        self.assertGreater(summary["observed_speed"], 7.5)
        self.assertEqual(summary["limit_point"], "html_media_timeline_advanced_at_requested_rate")

    def test_timeline_probe_summary_rejects_clamped_speed(self) -> None:
        summary = summarize_timeline_probe_samples(
            [
                {"wall_ms": 0, "media_time": 0.0},
                {"wall_ms": 1000, "media_time": 3.0},
            ],
            requested_speed=8,
        )

        self.assertFalse(summary["stable"])
        self.assertEqual(summary["limit_point"], "playback_rate_clamped_or_renderer_ignored_requested_rate")

    def test_hydrate_status_lists_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "packet.json").write_text("{}", encoding="utf-8")
            output = root / "output.mp3"
            output.write_bytes(b"mp3")
            status = {
                "artifact_dir": str(artifacts),
                "output_path": str(output),
            }
            hydrated = JobStore()._hydrate_status(status)  # noqa: SLF001
            self.assertTrue(hydrated["output_exists"])
            self.assertTrue(hydrated["expects_mp3_output"])
            self.assertEqual(hydrated["output_status"], "ready")
            self.assertEqual(hydrated["artifacts"][0]["name"], "packet.json")

    def test_hydrate_status_marks_cache_audit_as_diagnostic_only(self) -> None:
        status = JobStore()._hydrate_status(  # noqa: SLF001
            {
                "action": "audit-cache",
                "platform": "weixin",
                "state": "completed",
                "artifact_dir": "",
                "output_path": "/tmp/nonexistent-output.mp3",
                "verify": None,
            }
        )

        self.assertFalse(status["expects_mp3_output"])
        self.assertFalse(status["output_required"])
        self.assertTrue(status["diagnostic_only"])
        self.assertFalse(status["output_exists"])
        self.assertEqual(status["output_status"], "not_applicable")

    def test_hydrate_status_flags_completed_convert_missing_output(self) -> None:
        status = JobStore()._hydrate_status(  # noqa: SLF001
            {
                "action": "convert",
                "platform": "weixin",
                "state": "completed",
                "artifact_dir": "",
                "output_path": "/tmp/nonexistent-output.mp3",
                "verify": None,
            }
        )

        self.assertTrue(status["expects_mp3_output"])
        self.assertTrue(status["output_required"])
        self.assertFalse(status["diagnostic_only"])
        self.assertFalse(status["output_exists"])
        self.assertEqual(status["output_status"], "missing")

    def test_job_status_write_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "job"
            run_dir.mkdir()
            store = JobStore()
            old_status = {"id": "job1", "run_dir": str(run_dir), "state": "queued"}
            new_status = {"id": "job1", "run_dir": str(run_dir), "state": "running"}

            store._write_status(old_status)  # noqa: SLF001
            with patch.object(Path, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    store._write_status(new_status)  # noqa: SLF001

            persisted = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["state"], "queued")

    def test_import_artifact_copies_into_uploaded_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "response.json"
            source.write_text('{"ok": true}', encoding="utf-8")
            artifacts = root / "run" / "artifacts"
            first = import_artifact(str(source), artifacts)
            second = import_artifact(str(source), artifacts)
            self.assertEqual(first.name, "response.json")
            self.assertEqual(second.name, "response-2.json")
            self.assertTrue((artifacts / "uploaded" / "response.json").exists())

    def test_import_artifact_text_writes_uploaded_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            path = import_artifact_text('{"raw_url":"http://example.test/a.m4a"}', artifacts, ".json", "weixin-pasted")
            self.assertEqual(path.parent.name, "uploaded")
            self.assertTrue(path.name.startswith("weixin-pasted-"))
            self.assertEqual(path.suffix, ".json")
            self.assertIn("raw_url", path.read_text(encoding="utf-8"))

    def test_weixin_pasted_artifact_text_uses_vendor_adapter_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "output.mp3"
            calls: list[Path] = []

            def fake_vendor(source, output_path, _artifacts, _log):
                calls.append(Path(source))
                self.assertEqual(Path(source).parent.name, "uploaded")
                self.assertIn("finder.video.qq.com", Path(source).read_text(encoding="utf-8"))
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ), patch(
                "replay_mp3_studio.extractors.run_imported_artifact",
                side_effect=AssertionError("legacy imported artifact route should not run"),
            ):
                run_artifact_text(
                    "weixin",
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    '{"url":"https://finder.video.qq.com/251/20302/stodownload?token=secret","key":123456789,"encLimit":131072}',
                    ".json",
                    output,
                    artifacts,
                    lambda _message: None,
                )

            self.assertEqual(len(calls), 1)
            self.assertTrue(output.exists())

    def test_weixin_link_uses_source_vault_before_direct_probe_or_wechat_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "AFfTIp5Ywj-source.json"
            source.write_text(
                '{"url":"https://finder.video.qq.com/251/20302/stodownload?token=secret","key":123456789,"encLimit":131072}',
                encoding="utf-8",
            )
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            discovery_report = {
                "status": "matched",
                "matched_path": str(source),
                "match_reason": "path_token",
                "token_count": 1,
                "candidates_checked": 1,
            }
            calls: list[Path] = []

            def fake_vendor(source_path, output_path, _artifacts, _log, **_kwargs):
                calls.append(Path(source_path))
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.source_artifact_roots_from_env",
                return_value=(root,),
                create=True,
            ), patch(
                "replay_mp3_studio.extractors.discover_source_artifact_for_url",
                return_value=(source, discovery_report),
                create=True,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                side_effect=AssertionError("direct probe should not run after a source-vault hit"),
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=AssertionError("WeChat UI should not open after a source-vault hit"),
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                return_value={"packet": {}, "packet_dir": str(root / "packet")},
            ):
                run_weixin_link(
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output,
                    artifacts,
                    lambda _message: None,
                    duration=30,
                )

            diagnostics = json.loads((artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, [source])
            self.assertTrue(output.exists())
            self.assertEqual(diagnostics["stages"][0]["name"], "source_vault_artifact")
            self.assertTrue(diagnostics["stages"][0]["success"])
            self.assertEqual(diagnostics["stages"][0]["discovery"]["status"], "matched")

    def test_weixin_link_waits_for_source_vault_artifact_after_wechat_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "AFfTIp5Ywj-post-open-source.json"
            source.write_text(
                '{"url":"https://finder.video.qq.com/251/20302/stodownload?token=secret","key":123456789,"encLimit":131072}',
                encoding="utf-8",
            )
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            calls: list[Path] = []

            def fake_vendor(source_path, output_path, _artifacts, _log, **_kwargs):
                calls.append(Path(source_path))
                Path(output_path).write_bytes(b"mp3")

            with patch.dict("os.environ", {"WEIXIN_SOURCE_ARTIFACT_WAIT_SECONDS": "2"}, clear=False), patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                return_value={
                    "name": "source_vault_artifact",
                    "attempted": True,
                    "success": False,
                    "skipped_reason": "no_matching_authorized_source_artifact",
                },
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                return_value={"packet": {}, "packet_dir": str(root / "packet")},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                return_value={"name": "direct_link_provider_probe", "attempted": True, "success": False},
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
                    "activation_method": "autoplay",
                },
            ), patch(
                "replay_mp3_studio.extractors.wait_for_source_artifact_for_url",
                return_value=(
                    source,
                    {
                        "status": "matched",
                        "matched_path": str(source),
                        "match_reason": "text_token",
                        "attempts": 2,
                        "wait_seconds": 2.0,
                    },
                ),
                create=True,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_radium_source",
                side_effect=AssertionError("Radium scan should not run after a post-open source-vault hit"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_profile_state_source",
                side_effect=RuntimeError("profile scan should not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_cdncomm_source",
                side_effect=RuntimeError("cdncomm scan should not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_sharedata_feed",
                side_effect=RuntimeError("sharedata scan should not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_current_delta",
                side_effect=RuntimeError("current delta should not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_cache",
                side_effect=RuntimeError("cache should not run"),
            ):
                run_weixin_link(
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output,
                    artifacts,
                    lambda _message: None,
                    duration=30,
                )

            diagnostics = json.loads((artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8"))
            stage_names = [stage["name"] for stage in diagnostics["stages"]]
            self.assertIn("post_open_source_vault_artifact", stage_names)
            post_open_stage = diagnostics["stages"][stage_names.index("post_open_source_vault_artifact")]
            self.assertTrue(post_open_stage["success"])
            self.assertEqual(post_open_stage["discovery"]["status"], "matched")
            self.assertEqual(calls, [source])
            self.assertTrue(output.exists())

    def test_post_open_source_vault_default_is_immediate_without_sleep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            with patch.dict(os.environ, {}, clear=True), patch(
                "replay_mp3_studio.extractors.source_artifact_roots_from_env",
                return_value=(root,),
            ), patch(
                "replay_mp3_studio.extractors.discover_source_artifact_for_url",
                return_value=(None, {"status": "not_found"}),
            ) as discover_now, patch(
                "replay_mp3_studio.extractors.wait_for_source_artifact_for_url",
                side_effect=AssertionError("default path must not wait"),
            ):
                from replay_mp3_studio.extractors import (
                    post_open_source_artifact_wait_seconds,
                    run_weixin_post_open_source_vault_artifact,
                )

                stage = run_weixin_post_open_source_vault_artifact(
                    "https://weixin.qq.com/sph/A1TN6kx8js",
                    output,
                    artifacts,
                    lambda _message: None,
                    wait_seconds=post_open_source_artifact_wait_seconds(),
                )

            discover_now.assert_called_once()
            self.assertTrue(stage["attempted"])
            self.assertEqual(stage["lookup_mode"], "immediate")
            self.assertEqual(stage["wait_seconds"], 0.0)

    def test_weixin_link_does_not_scan_unbound_cache_after_target_open_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            with patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                return_value={
                    "name": "source_vault_artifact",
                    "attempted": True,
                    "success": False,
                    "skipped_reason": "no_matching_authorized_source_artifact",
                },
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                return_value={
                    "packet": {"short_uri": "AFfTIp5Ywj", "scene_info": {}},
                    "packet_dir": str(root / "packet"),
                },
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                return_value={"name": "direct_link_provider_probe", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=RuntimeError("target verification failed"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_radium_source",
                side_effect=AssertionError("unbound Radium scan must not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_profile_state_source",
                side_effect=AssertionError("unbound profile scan must not run"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_cdncomm_source",
                side_effect=AssertionError("unbound cdncomm scan must not run"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Weixin target open failed"):
                    run_weixin_link(
                        "https://weixin.qq.com/sph/AFfTIp5Ywj",
                        output,
                        artifacts,
                        lambda _message: None,
                        duration=30,
                    )

            diagnostics = json.loads((artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8"))
            self.assertIn("unbound playback/cache scans were skipped", diagnostics["summary"])
            self.assertFalse(output.exists())

    def test_weixin_recent_source_file_list_uses_safe_recent_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hit = root / "profiles" / "multitab_1" / "Local Storage" / "leveldb" / "001638.log"
            hit.parent.mkdir(parents=True)
            hit.write_text('{"url":"https://finder.video.qq.com/251/20302/stodownload"}', encoding="utf-8")
            safe_extra = root / "profiles" / "multitab_1" / "IndexedDB" / "weixin_xworker_0.indexeddb.leveldb" / "000056.log"
            safe_extra.parent.mkdir(parents=True)
            safe_extra.write_text("candidate", encoding="utf-8")
            sensitive = root / "profiles" / "multitab_1" / "History"
            sensitive.write_text("private history", encoding="utf-8")
            marker = root / "marker.json"
            marker.write_text(
                json.dumps(
                    {
                        "files_with_hits": [
                            {"relative_path": str(hit)},
                            {"relative_path": str(sensitive)},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            files = build_weixin_recent_source_file_list(
                marker,
                since_minutes=60,
                runtime_roots=(safe_extra.parent, sensitive.parent),
                now=time.time(),
            )

            self.assertIn(hit.resolve(), files)
            self.assertIn(safe_extra.resolve(), files)
            self.assertNotIn(sensitive.resolve(), files)

    def test_weixin_recent_source_file_list_does_not_reject_wechat_bundle_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "Library"
                / "Containers"
                / "com.tencent.xinWeChat"
                / "Data"
                / "Documents"
                / "app_data"
                / "net"
                / "kvcomm"
                / "533156473_4066646864_ready.statistic"
            )
            source.parent.mkdir(parents=True)
            source.write_text("https://finder.video.qq.com/251/20302/stodownload?token=x", encoding="utf-8")
            marker = root / "marker.json"
            marker.write_text(
                json.dumps({"files_with_hits": [{"relative_path": str(source)}]}),
                encoding="utf-8",
            )

            files = build_weixin_recent_source_file_list(marker, runtime_roots=(), now=time.time())

            self.assertEqual(files, [source.resolve()])

    def test_weixin_manual_playback_capture_converts_numeric_artifact_from_recent_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            marker = artifacts / "weixin_recent_media_marker_scan.json"
            source = root / "001638.log"
            source.write_text("source", encoding="utf-8")
            numeric = root / "successful-numeric-key-pairs.json"
            numeric.write_text('{"pairs":[]}', encoding="utf-8")
            calls: list[Path] = []

            def fake_vendor(source_path, output_path, _artifacts, _log, **_kwargs):
                calls.append(Path(source_path))
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_recent_marker_scan",
                return_value=marker,
            ), patch(
                "replay_mp3_studio.extractors.build_weixin_recent_source_file_list",
                return_value=[source],
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_encrypted_candidate_probe_for_sources",
                return_value={"result": "mp4_header_decrypted", "numeric_key_pair_artifact": str(numeric)},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ):
                stage = run_weixin_manual_playback_capture(output, artifacts, lambda _message: None)

            self.assertTrue(stage["success"])
            self.assertEqual(stage["numeric_key_pair_artifact"], str(numeric))
            self.assertEqual(calls, [numeric])
            self.assertTrue(output.exists())

    def test_weixin_manual_playback_capture_passes_min_duration_to_vendor_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            marker = artifacts / "weixin_recent_media_marker_scan.json"
            source = root / "001638.log"
            source.write_text("source", encoding="utf-8")
            numeric = root / "successful-numeric-key-pairs.json"
            numeric.write_text('{"pairs":[]}', encoding="utf-8")
            captured: dict[str, object] = {}

            def fake_vendor(_source_path, output_path, _artifacts, _log, **kwargs):
                captured["min_duration"] = kwargs.get("min_duration")
                Path(output_path).write_bytes(b"mp3")

            with patch(
                "replay_mp3_studio.extractors.run_weixin_recent_marker_scan",
                return_value=marker,
            ), patch(
                "replay_mp3_studio.extractors.build_weixin_recent_source_file_list",
                return_value=[source],
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_encrypted_candidate_probe_for_sources",
                return_value={"result": "mp4_header_decrypted", "numeric_key_pair_artifact": str(numeric)},
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_vendor_source_artifact",
                side_effect=fake_vendor,
            ):
                stage = run_weixin_manual_playback_capture(
                    output,
                    artifacts,
                    lambda _message: None,
                    min_duration=3000,
                )

            self.assertTrue(stage["success"])
            self.assertEqual(captured["min_duration"], 3000)

    def test_weixin_link_manual_playback_skips_wechat_open_and_uses_recent_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"

            def fake_manual(output_path, _artifacts, _log, **_kwargs):
                Path(output_path).write_bytes(b"mp3")
                return {"name": "manual_playback_recent_encrypted_capture", "attempted": True, "success": True}

            with patch(
                "replay_mp3_studio.extractors.run_weixin_source_vault_artifact",
                return_value={
                    "name": "source_vault_artifact",
                    "attempted": True,
                    "success": False,
                    "skipped_reason": "no_matching_authorized_source_artifact",
                },
            ), patch(
                "replay_mp3_studio.extractors.generate_weixin_open_packet",
                side_effect=AssertionError("manual playback should not generate an open packet"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_direct_link_probe",
                return_value={"name": "direct_link_provider_probe", "attempted": True, "success": False},
            ), patch(
                "replay_mp3_studio.extractors.open_weixin_target",
                side_effect=AssertionError("manual playback should not try to operate WeChat UI"),
            ), patch(
                "replay_mp3_studio.extractors.run_weixin_manual_playback_capture",
                side_effect=fake_manual,
            ):
                run_weixin_link(
                    "https://weixin.qq.com/sph/AFfTIp5Ywj",
                    output,
                    artifacts,
                    lambda _message: None,
                    duration=30,
                    manual_playback=True,
                )

            diagnostics = json.loads((artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8"))
            stage_names = [stage["name"] for stage in diagnostics["stages"]]
            self.assertIn("manual_playback_recent_encrypted_capture", stage_names)
            self.assertNotIn("open_current_wechat_playback", stage_names)
            self.assertTrue(output.exists())

    def test_weixin_bridge_payload_packet_is_written_from_open_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = {
                "scene_info": {
                    "dynamicExportId": "export/UzFfBgAAxBridgeTest",
                    "commentScene": 39,
                }
            }
            path = write_weixin_bridge_payload_packet(output_dir, "Aa0UXW05IP", packet, lambda _message: None)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["short_uri"], "Aa0UXW05IP")
        self.assertIn("finderH5Auth", json.dumps(payload, ensure_ascii=False))
        self.assertIn("pc_findergetcommentdetail", json.dumps(payload, ensure_ascii=False))
        self.assertIn("renderReplayUrl", payload["target_media_fields"][0])

    def test_weixin_object_list_only_does_not_require_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "artifact.json"
            artifact.write_text('{"dynamicExportId":"export/UzFfBgAAxBridgeTest"}', encoding="utf-8")
            with patch.object(sys, "argv", ["weixin_object_artifact_to_mp3.py", str(artifact), "--list-only"]):
                with redirect_stdout(io.StringIO()):
                    result = weixin_object_module.main()

        self.assertEqual(result, 0)

    def test_finds_latest_reusable_songy_artifact_for_same_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "third_party" / "20260101-old" / "artifacts" / "uploaded"
            newer = root / "third_party" / "20260102-new" / "artifacts" / "uploaded"
            other = root / "third_party" / "20260103-other" / "artifacts" / "uploaded"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)
            other.mkdir(parents=True)
            (older / "songy_browser_capture.authorized.json").write_text(
                '{"url":"https://webapp.songy.info/#/courses/details?course_id=783","media_urls":["http://a.test/a.m4a"]}',
                encoding="utf-8",
            )
            expected = newer / "songy_browser_capture.authorized.json"
            expected.write_text(
                '{"url":"https://webapp.songy.info/#/courses/details?course_id=783","media_urls":["http://a.test/b.m4a"]}',
                encoding="utf-8",
            )
            (other / "songy_browser_capture.authorized.json").write_text(
                '{"url":"https://webapp.songy.info/#/courses/details?course_id=784","media_urls":["http://a.test/c.m4a"]}',
                encoding="utf-8",
            )

            self.assertEqual(
                find_reusable_songy_artifact(
                    "https://webapp.songy.info/#/courses/details?course_id=783",
                    library_root=root,
                ),
                expected,
            )

    def test_finds_reusable_songy_mp3_cache_for_same_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            outputs.mkdir()
            expected = outputs / "songy_course_783.mp3"
            expected.write_bytes(b"mp3")
            (outputs / "songy_course_784.mp3").write_bytes(b"other")

            self.assertEqual(
                find_reusable_songy_mp3(
                    "https://webapp.songy.info/#/courses/details?course_id=783",
                    project_root=root,
                ),
                expected,
            )

    def test_justone_extracts_identifier_pair(self) -> None:
        pair = justone_module.first_pair(
            {
                "data": {
                    "objectId": "14557655258854393974",
                    "objectNonceId": "16168326469763538757_0_0_0_0_0",
                }
            }
        )

        self.assertEqual(pair["object_id"], "14557655258854393974")
        self.assertEqual(pair["object_nonce_id"], "16168326469763538757_0_0_0_0_0")

    def test_justone_finds_media_url(self) -> None:
        url = justone_module.find_media_url({"data": {"downloadUrl": "https://finder.video.qq.com/251/20302/stodownload?token=x"}})

        self.assertIn("finder.video.qq.com", url)

    def test_sharedata_token_fingerprint_does_not_expose_value(self) -> None:
        fingerprint = sharedata_module.token_fingerprint("sensitive-token-value")

        self.assertEqual(set(fingerprint), {"sha256_12", "length"})
        self.assertEqual(fingerprint["length"], len("sensitive-token-value"))
        self.assertNotIn("sensitive-token-value", str(fingerprint))

    def test_sharedata_extracts_generic_long_token_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = (
                root
                / "Library"
                / "Containers"
                / "com.tencent.xinWeChat"
                / "Data"
                / "Documents"
                / "app_data"
                / "radium"
                / "web"
                / "profiles"
                / "profile"
            )
            storage = profile / "Local Storage" / "leveldb"
            storage.mkdir(parents=True)
            token = "a" * 96
            path = storage / "000001.log"
            path.write_text(f"prefix {token} suffix", encoding="utf-8")

            with patch.object(sharedata_module.Path, "home", return_value=root):
                candidates = sharedata_module.extract_token_candidates(
                    since_minutes=60,
                    max_file_bytes=10_000,
                    max_candidates=5,
                )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].token, token)
            self.assertEqual(candidates[0].key_hint, "generic-long-token")

    def test_yuanbao_provider_skips_without_explicit_cookie(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            ok, stage = direct_links_module.try_weixin_yuanbao(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                Path("/tmp/out.mp3"),
            )

        self.assertFalse(ok)
        self.assertFalse(stage["configured"])
        self.assertEqual(stage["status"], "skipped")

    def test_weixin_direct_timeout_is_bounded_and_configurable(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(direct_links_module.weixin_request_timeout(5), 5.0)
        with patch.dict("os.environ", {"WEIXIN_DIRECT_REQUEST_TIMEOUT_SECONDS": "0.1"}, clear=True):
            self.assertEqual(direct_links_module.weixin_request_timeout(5), 1.0)
        with patch.dict("os.environ", {"WEIXIN_DIRECT_REQUEST_TIMEOUT_SECONDS": "999"}, clear=True):
            self.assertEqual(direct_links_module.weixin_request_timeout(5), 120.0)

    def test_direct_request_network_failure_returns_safe_bounded_result(self) -> None:
        with patch.object(
            direct_links_module.urllib.request,
            "urlopen",
            side_effect=direct_links_module.urllib.error.URLError("vpn offline"),
        ) as urlopen:
            status, payload = direct_links_module.request_json(
                "https://example.test/api",
                timeout=3,
            )

        self.assertEqual(status, 0)
        self.assertEqual(payload, {"error": "network_unavailable_or_timed_out"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)

    def test_public_weixin_feed_uses_short_default_timeout(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch.object(
            direct_links_module,
            "request_json",
            return_value=(0, {"error": "network_unavailable_or_timed_out"}),
        ) as request_json:
            direct_links_module.fetch_weixin_feed(
                {"baseReq": {"generalToken": ""}, "shortUri": "A1TN6kx8js"},
                "A1TN6kx8js",
            )

        self.assertEqual(request_json.call_args.kwargs["timeout"], 5.0)

    def test_yuanbao_provider_uses_cookie_without_reporting_it(self) -> None:
        parse_payload = {
            "data": {
                "playable_url": (
                    "https://channels.weixin.qq.com/finder-preview/pages/feed?"
                    "token=general-token-value&eid=export%2Fabc"
                )
            }
        }
        feed_payload = {
            "data": {
                "feedInfo": {
                    "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"
                }
            }
        }

        with patch.dict("os.environ", {"WEIXIN_YUANBAO_COOKIE": "secret-cookie-value"}, clear=True), patch.object(
            direct_links_module, "request_json", side_effect=[(200, parse_payload), (201, feed_payload)]
        ), patch.object(direct_links_module, "convert") as convert:
            ok, stage = direct_links_module.try_weixin_yuanbao(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                Path("/tmp/out.mp3"),
            )

        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        self.assertTrue(stage["has_general_token"])
        self.assertTrue(stage["has_export_id"])
        self.assertNotIn("secret-cookie-value", str(stage))
        convert.assert_called_once()

    def test_yuanbao_provider_decodes_same_response_url_and_key(self) -> None:
        parse_payload = {
            "data": {
                "feedInfo": {
                    "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                    "decodeKey": "0123456789abcdef",
                }
            }
        }
        output = Path("/tmp/out.mp3")

        def fake_decode(pair, output_path, **_kwargs):
            self.assertIn("stodownload", pair["url"])
            self.assertEqual(pair["decode_key"], "0123456789abcdef")
            self.assertEqual(output_path, output)
            return {
                "ok": True,
                "decode_key_sha256_12": "synthetic",
                "decode_key_length": 16,
                "url_host_path": "finder.video.qq.com/251/20302/stodownload",
            }

        with patch.dict("os.environ", {"WEIXIN_YUANBAO_COOKIE": "secret-cookie-value"}, clear=True), patch.object(
            direct_links_module, "request_json", return_value=(200, parse_payload)
        ), patch.object(direct_links_module, "convert") as convert, patch.object(
            direct_links_module, "decode_weixin_pair_to_mp3", side_effect=fake_decode
        ) as decode:
            ok, stage = direct_links_module.try_weixin_yuanbao(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                output,
            )

        encoded = json.dumps(stage, ensure_ascii=False)
        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        self.assertEqual(stage["media_source"], "yuanbao_decode_key_pair")
        self.assertEqual(stage["decode_key_pair_count"], 1)
        decode.assert_called_once()
        convert.assert_not_called()
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("secret-cookie-value", encoded)

    def test_export_token_feed_request_uses_feed_page_referer(self) -> None:
        with patch.object(direct_links_module, "request_json", return_value=(201, {"ok": True})) as request_json:
            status, _ = direct_links_module.fetch_weixin_feed_with_export_token("export/abc", "general-token")

        self.assertEqual(status, 201)
        call = request_json.call_args
        self.assertIn("finder-preview%2Fpages%2Ffeed", call.args[0])
        payload = call.kwargs["payload"]
        headers = call.kwargs["headers"]
        self.assertEqual(payload["baseReq"]["generalToken"], "general-token")
        self.assertEqual(payload["exportId"], "export/abc")
        self.assertIn("/finder-preview/pages/feed?", headers["Referer"])
        self.assertIn("token=general-token", headers["Referer"])
        self.assertIn("eid=export%2Fabc", headers["Referer"])

    def test_compact_provider_response_includes_safe_error_message(self) -> None:
        summary = direct_links_module.compact_provider_response(
            {
                "error": "parse share url: missing wx_export_id",
                "url": "https://signed.example.test/a.mp4?token=secret",
            }
        )

        self.assertEqual(summary["error_message"], "parse share url: missing wx_export_id")
        self.assertEqual(summary["candidate_media_url_count"], 1)
        self.assertEqual(summary["redacted_media_urls"][0], "https://signed.example.test/a.mp4?<redacted>")

    def test_direct_link_probe_report_redacts_nested_provider_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "target": "weixin",
                "candidate_media_urls": [
                    "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret"
                ],
                "attempts": [
                    {
                        "name": "resolver",
                        "response": {
                            "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                            "decodeKey": "0123456789abcdef",
                            "cookie": "private-cookie",
                        },
                    }
                ],
            }

            with patch.object(direct_links_module, "WORK_REPORTS", root):
                report = direct_links_module.save_report("weixin_direct_link_probe", payload)

            text = report.read_text(encoding="utf-8")

        self.assertIn("stodownload?<redacted>", text)
        self.assertNotIn("token=secret", text)
        self.assertNotIn("encfilekey=abc", text)
        self.assertNotIn("0123456789abcdef", text)
        self.assertNotIn("private-cookie", text)

    def test_configured_sph_resolver_finds_media_url(self) -> None:
        payload = {
            "data": {
                "data": {
                    "feedInfo": {
                        "h264VideoInfo": {
                            "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"
                        }
                    }
                }
            }
        }

        with patch.dict("os.environ", {"WEIXIN_SPH_RESOLVER_URL": "https://resolver.example.test"}, clear=True), patch.object(
            direct_links_module, "request_json", return_value=(200, payload)
        ), patch.object(direct_links_module, "convert") as convert:
            ok, stage = direct_links_module.try_weixin_sph_resolver(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                Path("/tmp/out.mp3"),
            )

        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        self.assertEqual(stage["summary"]["candidate_media_url_count"], 1)
        self.assertEqual(stage["attempts"][0]["endpoint"], "https://resolver.example.test/fetch_video_profile")
        convert.assert_called_once()

    def test_configured_sph_resolver_decodes_same_response_url_and_key(self) -> None:
        payload = {
            "data": {
                "feedInfo": {
                    "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                    "decodeKey": "0123456789abcdef",
                }
            }
        }
        output = Path("/tmp/out.mp3")

        def fake_decode(pair, output_path, **_kwargs):
            self.assertIn("stodownload", pair["url"])
            self.assertEqual(pair["decode_key"], "0123456789abcdef")
            self.assertEqual(output_path, output)
            return {
                "ok": True,
                "decode_key_sha256_12": "synthetic",
                "decode_key_length": 16,
                "url_host_path": "finder.video.qq.com/251/20302/stodownload",
            }

        with patch.dict("os.environ", {"WEIXIN_SPH_RESOLVER_URL": "https://resolver.example.test"}, clear=True), patch.object(
            direct_links_module, "request_json", return_value=(200, payload)
        ), patch.object(direct_links_module, "convert") as convert, patch.object(
            direct_links_module, "decode_weixin_pair_to_mp3", side_effect=fake_decode, create=True
        ) as decode:
            ok, stage = direct_links_module.try_weixin_sph_resolver(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                output,
            )

        encoded = json.dumps(stage, ensure_ascii=False)
        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        self.assertEqual(stage["media_source"], "resolver_decode_key_pair")
        self.assertEqual(stage["decode_key_pair_count"], 1)
        decode.assert_called_once()
        convert.assert_not_called()
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("encfilekey=abc", encoded)

    def test_configured_sph_resolver_can_follow_playable_url_to_feed_media(self) -> None:
        parse_payload = {
            "data": {
                "playable_url": (
                    "https://channels.weixin.qq.com/finder-preview/pages/feed?"
                    "token=general-token&eid=export%2Fabc"
                )
            }
        }
        feed_payload = {
            "data": {
                "feedInfo": {
                    "originVideoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=xyz",
                }
            }
        }

        with patch.dict("os.environ", {"WEIXIN_SPH_RESOLVER_URL": "https://resolver.example.test"}, clear=True), patch.object(
            direct_links_module, "request_json", return_value=(200, parse_payload)
        ) as request_json, patch.object(
            direct_links_module, "fetch_weixin_feed_with_export_token", return_value=(200, feed_payload)
        ) as feed, patch.object(direct_links_module, "convert") as convert:
            ok, stage = direct_links_module.try_weixin_sph_resolver(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                Path("/tmp/out.mp3"),
            )

        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        request_json.assert_called_once()
        feed.assert_called_once_with("export/abc", "general-token")
        convert.assert_called_once()
        self.assertEqual(stage["playable_summary"]["media_source"], "playable_url_feed")

    def test_configured_sph_resolver_falls_back_to_api_path(self) -> None:
        payload = {
            "data": {
                "feedInfo": {
                    "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"
                }
            }
        }

        with patch.dict("os.environ", {"WEIXIN_SPH_RESOLVER_URL": "https://resolver.example.test"}, clear=True), patch.object(
            direct_links_module, "request_json", side_effect=[(404, {"error": "not found"}), (200, payload)]
        ) as request_json, patch.object(direct_links_module, "convert") as convert:
            ok, stage = direct_links_module.try_weixin_sph_resolver(
                "https://weixin.qq.com/sph/Aa0UXW05IP",
                Path("/tmp/out.mp3"),
            )

        self.assertTrue(ok)
        self.assertEqual(stage["status"], "created-mp3")
        self.assertEqual(len(stage["attempts"]), 2)
        self.assertEqual(stage["attempts"][1]["endpoint"], "https://resolver.example.test/api/fetch_video_profile")
        self.assertEqual(request_json.call_count, 2)
        convert.assert_called_once()

    def test_configured_sph_resolver_specs_include_wx_channel_compatible_routes(self) -> None:
        specs = direct_links_module.sph_resolver_request_specs(
            "https://resolver.example.test",
            "https://weixin.qq.com/sph/Aa0UXW05IP",
        )
        endpoints = [spec["endpoint"] for spec in specs]
        methods = {spec["name"]: spec["method"] for spec in specs}

        self.assertIn(
            "https://resolver.example.test/api/channels/parse_sph?url=https%3A%2F%2Fweixin.qq.com%2Fsph%2FAa0UXW05IP",
            endpoints,
        )
        self.assertIn(
            "https://resolver.example.test/api/channels/shared_feed/profile?url=https%3A%2F%2Fweixin.qq.com%2Fsph%2FAa0UXW05IP",
            endpoints,
        )
        self.assertIn("https://resolver.example.test/api/channels/share/resolve", endpoints)
        self.assertEqual(methods["channels_parse_sph"], "GET")
        self.assertEqual(methods["channels_share_resolve_backend"], "POST")

    def test_weixin_jobs_default_to_a_minimum_output_duration(self) -> None:
        self.assertEqual(minimum_output_duration_seconds("weixin", {}), 180)
        self.assertEqual(minimum_output_duration_seconds("weixin", {"allow_short_output": True}), 0)
        self.assertEqual(minimum_output_duration_seconds("weixin", {"min_duration_seconds": 60}), 60)
        self.assertEqual(minimum_output_duration_seconds("third_party", {}), 0)
        self.assertEqual(
            minimum_output_duration_seconds(
                "third_party",
                {"url": "https://webapp.songy.info/#/courses/details?course_id=783"},
            ),
            180,
        )

    def test_weixin_blackbox_speed_is_capped_to_verified_official_speed(self) -> None:
        self.assertEqual(effective_blackbox_speed("weixin", 8), 3.0)
        self.assertEqual(effective_blackbox_speed("weixin", 3), 3.0)
        self.assertEqual(effective_blackbox_speed("third_party", 8), 8.0)

    def test_blackbox_speed_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            effective_blackbox_speed("weixin", 0)

    def test_weixin_blackbox_job_uses_capped_effective_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, float] = {}

            def temp_platform_folder(platform: str) -> Path:
                path = root / platform
                path.mkdir(parents=True, exist_ok=True)
                return path

            def fake_run_blackbox_record(
                _url,
                output,
                _artifacts,
                _log,
                *,
                duration,
                speed,
                audio_device,
                wait_audio_timeout=0,
            ) -> None:
                captured["duration"] = float(duration)
                captured["speed"] = float(speed)
                captured["wait_audio_timeout"] = float(wait_audio_timeout)
                self.assertEqual(audio_device, "system")
                Path(output).write_bytes(b"mp3")

            with patch("replay_mp3_studio.jobs.platform_folder", side_effect=temp_platform_folder), patch(
                "replay_mp3_studio.jobs.run_blackbox_record",
                side_effect=fake_run_blackbox_record,
            ), patch(
                "replay_mp3_studio.jobs.verify_mp3",
                return_value={"ok": True, "duration_seconds": 10.0, "bytes": 3},
            ):
                store = JobStore()
                status = store.create_job(
                    {
                        "platform": "weixin",
                        "action": "blackbox-record",
                        "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                        "duration": 30,
                        "blackbox_speed": 8,
                        "audio_device": "system",
                        "allow_short_output": True,
                    }
                )
                deadline = time.time() + 5
                current = store.get_job(status["id"])
                while time.time() < deadline:
                    current = store.get_job(status["id"])
                    if current["state"] in {"completed", "failed"}:
                        break
                    time.sleep(0.05)

        self.assertEqual(current["state"], "completed", current)
        self.assertEqual(captured["speed"], 3.0)
        self.assertEqual(current["blackbox_requested_speed"], 8.0)
        self.assertEqual(current["blackbox_effective_speed"], 3.0)

    def test_long_weixin_blackbox_job_uses_auto_segmented_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, object] = {}

            def temp_platform_folder(platform: str) -> Path:
                path = root / platform
                path.mkdir(parents=True, exist_ok=True)
                return path

            def fake_run_weixin_auto_blackbox_fallback(
                _url,
                output,
                _artifacts,
                _log,
                *,
                payload,
                duration,
                requested_speed,
                effective_speed,
                min_duration_seconds,
            ) -> dict[str, object]:
                captured["duration"] = float(duration)
                captured["requested_speed"] = float(requested_speed)
                captured["effective_speed"] = float(effective_speed)
                captured["min_duration_seconds"] = float(min_duration_seconds)
                captured["payload_audio_device"] = payload.get("audio_device")
                Path(output).write_bytes(b"mp3")
                return {
                    "mp3_complete": True,
                    "selected_route": "segmented_blackbox",
                    "highest_stable_speed": "3x_requested_segmented",
                    "report": str(root / "auto-report.md"),
                    "json_report": str(root / "auto-report.json"),
                    "routes": [
                        {
                            "name": "segmented_blackbox",
                            "status": "success",
                            "manifest": str(root / "blackbox-segments" / "manifest.json"),
                        }
                    ],
                }

            with patch("replay_mp3_studio.jobs.platform_folder", side_effect=temp_platform_folder), patch(
                "replay_mp3_studio.jobs.run_blackbox_record",
                side_effect=AssertionError("long Weixin blackbox job should use the auto segmented pipeline"),
            ), patch(
                "replay_mp3_studio.jobs.run_weixin_auto_blackbox_fallback",
                side_effect=fake_run_weixin_auto_blackbox_fallback,
            ), patch(
                "replay_mp3_studio.jobs.verify_mp3",
                return_value={"ok": True, "duration_seconds": 7200.0, "bytes": 3},
            ):
                store = JobStore()
                status = store.create_job(
                    {
                        "platform": "weixin",
                        "action": "blackbox-record",
                        "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                        "duration": 7200,
                        "blackbox_speed": 8,
                        "audio_device": "system",
                        "allow_short_output": True,
                    }
                )
                deadline = time.time() + 5
                current = store.get_job(status["id"])
                while time.time() < deadline:
                    current = store.get_job(status["id"])
                    if current["state"] in {"completed", "failed"}:
                        break
                    time.sleep(0.05)

        self.assertEqual(current["state"], "completed")
        self.assertEqual(captured["duration"], 7200.0)
        self.assertEqual(captured["requested_speed"], 8.0)
        self.assertEqual(captured["effective_speed"], 3.0)
        self.assertEqual(captured["payload_audio_device"], "system")
        self.assertEqual(current["blackbox_requested_speed"], 8.0)
        self.assertEqual(current["blackbox_effective_speed"], 3.0)
        self.assertEqual(current["auto_pipeline_selected_route"], "segmented_blackbox")
        self.assertEqual(current["auto_pipeline_highest_stable_speed"], "3x_requested_segmented")
        self.assertTrue(current["auto_pipeline_report_path"].endswith("auto-report.md"))

    def test_weixin_manual_playback_job_passes_manual_flag_to_link_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, object] = {}

            def temp_platform_folder(platform: str) -> Path:
                path = root / platform
                path.mkdir(parents=True, exist_ok=True)
                return path

            def fake_run_weixin_link(
                _url,
                output,
                _artifacts,
                _log,
                *,
                duration,
                watch_current_only=False,
                manual_playback=False,
                min_duration=0,
            ) -> None:
                captured["duration"] = duration
                captured["watch_current_only"] = watch_current_only
                captured["manual_playback"] = manual_playback
                captured["min_duration"] = min_duration
                Path(output).write_bytes(b"mp3")

            with patch("replay_mp3_studio.jobs.platform_folder", side_effect=temp_platform_folder), patch(
                "replay_mp3_studio.jobs.run_weixin_link",
                side_effect=fake_run_weixin_link,
            ), patch(
                "replay_mp3_studio.jobs.verify_mp3",
                return_value={"ok": True, "duration_seconds": 4179.7, "bytes": 3},
            ):
                store = JobStore()
                status = store.create_job(
                    {
                        "platform": "weixin",
                        "action": "convert",
                        "url": "https://weixin.qq.com/sph/AFfTIp5Ywj",
                        "duration": 300,
                        "weixin_manual_playback": True,
                    }
                )
                deadline = time.time() + 5
                current = store.get_job(status["id"])
                while time.time() < deadline:
                    current = store.get_job(status["id"])
                    if current["state"] in {"completed", "failed"}:
                        break
                    time.sleep(0.05)

        self.assertEqual(current["state"], "completed")
        self.assertEqual(captured["duration"], 300)
        self.assertFalse(captured["watch_current_only"])
        self.assertTrue(captured["manual_playback"])
        self.assertEqual(captured["min_duration"], 180)

    def test_action_labels_cover_diagnostic_modes(self) -> None:
        self.assertEqual(action_label("convert"), "转 MP3")
        self.assertEqual(action_label("audit-cache"), "缓存审计")
        self.assertEqual(action_label("probe-url"), "网络探测")
        self.assertEqual(action_label("blackbox-record"), "黑箱录制")

    def test_songy_capture_failure_gets_login_play_retry_action(self) -> None:
        action = diagnose_next_action(
            {
                "platform": "third_party",
                "url": "https://webapp.songy.info/#/courses/details?course_id=783",
                "state": "failed",
                "error": "Songy browser capture failed with exit code 1",
                "artifacts": [{"name": "songy_browser_capture.json", "path": "/tmp/songy_browser_capture.json"}],
            }
        )

        self.assertEqual(action["kind"], "songy_login_play_retry")
        self.assertIn("登录", action["label"])
        self.assertIn("播放", action["detail"])
        self.assertEqual(action["artifact_path"], "/tmp/songy_browser_capture.json")

    def test_weixin_failure_gets_playback_bridge_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet = Path(tmp) / "packet.json"
            packet.write_text(
                '{"short_uri":"Aa0UXW05IP","scene_info":{"dynamicExportId":"export/UzFfBgAAxBridgeTest"}}',
                encoding="utf-8",
            )
            action = diagnose_next_action(
                {
                    "platform": "weixin",
                    "url": "https://weixin.qq.com/sph/Aa0UXW05IP",
                    "state": "failed",
                    "error": "Weixin link-to-MP3 failed; see diagnostics: /tmp/weixin_link_diagnostics.json",
                    "artifacts": [
                        {"name": "weixin_link_diagnostics.json", "path": "/tmp/weixin_link_diagnostics.json"},
                        {"name": "weixin_open_packet/open_packet.html", "path": "/tmp/open_packet.html"},
                        {"name": "weixin_open_packet/packet.json", "path": str(packet)},
                        {"name": "weixin_bridge_payload_packet.json", "path": str(Path(tmp) / "payload.json")},
                    ],
                }
            )

        self.assertEqual(action["kind"], "weixin_playback_bridge")
        self.assertIn("视频号播放页", action["label"])
        self.assertEqual(action["diagnostics_path"], "/tmp/weixin_link_diagnostics.json")
        self.assertEqual(action["open_packet_path"], "/tmp/open_packet.html")
        self.assertIn("/api/weixin/bridge-autopost-snippet?", action["bridge_snippet_url"])
        self.assertIn("noprompt=1", action["bridge_snippet_url"])
        self.assertIn("short_uri=Aa0UXW05IP", action["bridge_snippet_url"])
        self.assertIn("/weixin-bridge-launcher?", action["bridge_launcher_url"])
        self.assertIn("short_uri=Aa0UXW05IP", action["bridge_launcher_url"])
        self.assertEqual(action["bridge_payload_packet_path"], str(Path(tmp) / "payload.json"))

    def test_weixin_unlinked_playback_fd_gets_specific_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = root / "packet.json"
            packet.write_text(
                '{"short_uri":"AIt1nfC2d7","scene_info":{"dynamicExportId":"export/UzFfBgAAxBridgeTest"}}',
                encoding="utf-8",
            )
            diagnostics = root / "diagnostics.json"
            diagnostics.write_text(
                """
                {
                  "target_identity": {
                    "short_uri": "AIt1nfC2d7",
                    "dynamic_export_id_sha256_12": "abc123def456"
                  },
                  "stages": [
                    {
                      "name": "direct_link_provider_probe",
                      "provider_keys": {"WXSHARES_KEY": false, "DAJIALA_KEY": false}
                    },
                    {
                      "name": "current_playback_delta_watch",
                      "diagnostics": {"diagnosis": "playback_fd_unlinked"}
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            action = diagnose_next_action(
                {
                    "platform": "weixin",
                    "url": "https://weixin.qq.com/sph/AIt1nfC2d7",
                    "state": "failed",
                    "error": "Weixin link-to-MP3 failed; see diagnostics: /tmp/weixin_link_diagnostics.json",
                    "artifacts": [
                        {"name": "weixin_link_diagnostics.json", "path": str(diagnostics)},
                        {"name": "weixin_open_packet/open_packet.html", "path": str(root / "open_packet.html")},
                        {"name": "weixin_open_packet/packet.json", "path": str(packet)},
                        {"name": "weixin_bridge_payload_packet.json", "path": str(root / "payload.json")},
                    ],
                }
            )

        self.assertEqual(action["kind"], "weixin_bridge_or_provider_required")
        self.assertEqual(action["identity_hash"], "abc123def456")
        self.assertIn("未命名临时 fd", action["detail"])
        self.assertEqual(action["provider_keys_configured"], "no")
        self.assertIn("/weixin-bridge-launcher?", action["bridge_launcher_url"])
        self.assertEqual(action["bridge_payload_packet_path"], str(root / "payload.json"))

    def test_weixin_bridge_access_denied_artifact_gets_context_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploaded = root / "artifacts" / "uploaded"
            uploaded.mkdir(parents=True)
            artifact = uploaded / "weixin-pasted.json"
            artifact.write_text(
                json.dumps(
                    {
                        "source": "weixin_bridge_autopost",
                        "error": "No liveId in FinderGetCommentDetail response",
                        "detail": {"err_msg": "system:access_denied"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            action = diagnose_next_action(
                {
                    "platform": "weixin",
                    "state": "failed",
                    "error": "Artifact conversion failed with exit code 1",
                    "artifacts": [{"name": "uploaded/weixin-pasted.json", "path": str(artifact)}],
                }
            )

        self.assertEqual(action["kind"], "weixin_bridge_wrong_context")
        self.assertIn("真实播放页上下文", action["label"])
        self.assertEqual(action["artifact_path"], str(artifact))

    def test_weixin_regression_auto_timeout_covers_full_pipeline(self) -> None:
        self.assertGreaterEqual(
            weixin_regression_module.recommended_timeout_seconds(duration=90, open_wechat=True),
            360,
        )
        self.assertGreaterEqual(
            weixin_regression_module.recommended_timeout_seconds(duration=3, open_wechat=False),
            120,
        )

    def test_weixin_regression_timeout_summary_overrides_running_state(self) -> None:
        job = weixin_regression_module.timeout_job_summary(
            {"id": "abc", "state": "running", "error": "", "artifacts": []},
            timeout=12,
        )

        self.assertEqual(job["state"], "timeout")
        self.assertEqual(job["original_state"], "running")
        self.assertTrue(job["regression_timeout"])

    def test_weixin_regression_defaults_to_opening_links(self) -> None:
        self.assertTrue(weixin_regression_module.should_open_wechat(open_wechat=True, watch_current=False))
        self.assertFalse(weixin_regression_module.should_open_wechat(open_wechat=False, watch_current=True))
        self.assertTrue(weixin_regression_module.should_open_wechat(open_wechat=True, watch_current=True))

    def test_health_check_action_is_not_treated_as_user_deliverable(self) -> None:
        status = JobStore()._hydrate_status(  # noqa: SLF001
            {
                "action": "health-check",
                "platform": "weixin",
                "state": "completed",
                "artifact_dir": "",
                "output_path": "",
            }
        )

        self.assertTrue(status["is_health_check"])
        self.assertFalse(status["diagnostic_only"])
        self.assertTrue(status["expects_mp3_output"])

    def test_verify_mp3_rejects_outputs_shorter_than_minimum_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "short.mp3"
            output.write_bytes(b"fake mp3")
            logs: list[str] = []
            ffmpeg_result = SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="Duration: 00:00:01.04, start: 0.000000, bitrate: 128 kb/s",
            )

            with patch("replay_mp3_studio.utils.find_ffmpeg", return_value="/usr/bin/ffmpeg"), patch(
                "replay_mp3_studio.utils.child_env", return_value={}
            ), patch("replay_mp3_studio.utils.subprocess.run", return_value=ffmpeg_result):
                with self.assertRaisesRegex(RuntimeError, "shorter than required"):
                    verify_mp3(output, logs.append, min_duration_seconds=180)

    def test_verify_mp3_reports_duration_from_ffmpeg_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sample.mp3"
            output.write_bytes(b"fake mp3")
            logs: list[str] = []
            ffmpeg_result = SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="Duration: 00:01:17.50, start: 0.000000, bitrate: 128 kb/s",
            )

            with patch("replay_mp3_studio.utils.find_ffmpeg", return_value="/usr/bin/ffmpeg"), patch(
                "replay_mp3_studio.utils.child_env", return_value={}
            ), patch("replay_mp3_studio.utils.subprocess.run", return_value=ffmpeg_result):
                result = verify_mp3(output, logs.append)

            self.assertEqual(result.get("duration_seconds"), 77.5)


if __name__ == "__main__":
    unittest.main()
