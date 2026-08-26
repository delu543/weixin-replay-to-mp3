from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import weixin_replay_cli as cli
from replay_mp3_studio import extractors, platform_support, user_storage, utils, web_tools
from scripts import bootstrap


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WindowsSupportTests(unittest.TestCase):
    def test_windows_application_root_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            local = Path(tmp) / "local"
            root = platform_support.application_root(
                home,
                environ={"LOCALAPPDATA": str(local)},
                system="Windows",
            )
        self.assertEqual(root, (local / "WeixinReplayToMP3").resolve())

    def test_windows_runtime_roots_accept_semicolon_override_and_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            configured_a = base / "configured-a"
            configured_b = base / "configured-b"
            env = {
                "APPDATA": str(base / "roaming"),
                "LOCALAPPDATA": str(base / "local"),
                platform_support.RUNTIME_ROOTS_ENV: f"{configured_a};{configured_b}",
            }
            roots = platform_support.weixin_marker_scan_roots(
                base / "home", environ=env, system="Windows"
            )
        self.assertEqual(roots[:2], (configured_a, configured_b))
        self.assertIn(base / "roaming" / "Tencent" / "xwechat" / "radium", roots)
        self.assertIn(
            base / "local" / "Tencent" / "WeChat" / "XPlugin" / "Plugins" / "RadiumWMPF",
            roots,
        )

    def test_macos_root_sets_remain_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            data = home / "Library/Containers/com.tencent.xinWeChat/Data"
            marker = platform_support.weixin_marker_scan_roots(home, environ={}, system="Darwin")
            recent = platform_support.weixin_recent_source_roots(home, environ={}, system="Darwin")
            audit = platform_support.weixin_cache_audit_roots(home, environ={}, system="Darwin")
        self.assertEqual(
            marker,
            (
                data / "Documents/app_data/radium",
                data / "Documents/app_data/net/cdncomm",
                data / "Documents/app_data/net/kvcomm",
                data / "Documents/app_data/log/radium",
                data / "Documents/app_data/log/player",
                home / "Library/Group Containers/5A4RE8SF68.com.tencent.xinWeChat/Library/Caches",
            ),
        )
        self.assertEqual(
            recent,
            (
                data / "Documents/app_data/radium/web/profiles",
                data / "Documents/app_data/net/cdncomm",
                data / "Documents/app_data/net/kvcomm",
                data / "Documents/app_data/log/radium",
                data / "Documents/app_data/log/player",
            ),
        )
        self.assertEqual(
            audit,
            (
                data / "tmp",
                data / "Documents/app_data/radium",
                data / "Documents/app_data/net/cdncomm",
            ),
        )

    def test_windows_wechat_process_detection_accepts_both_names(self) -> None:
        runner = mock.Mock(
            return_value=SimpleNamespace(returncode=0, stdout='"Weixin.exe","1234"', stderr="")
        )
        self.assertTrue(platform_support.wechat_process_running(system="Windows", runner=runner))
        self.assertEqual(runner.call_args.args[0][:2], ["tasklist", "/FO"])

    def test_windows_bootstrap_selects_scripts_and_windows_hashes(self) -> None:
        venv = Path("C:/runtime/work/venv")
        self.assertEqual(bootstrap.venv_python(venv, "Windows"), venv / "Scripts" / "python.exe")
        self.assertEqual(
            bootstrap.requirements_path("Windows"),
            bootstrap.RUNTIME_ROOT / "requirements-windows.txt",
        )

    def test_windows_preflight_explains_manual_playback(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(cli.platform, "system", return_value="Windows"),
            mock.patch.object(cli.sys, "version_info", (3, 11, 0)),
            mock.patch.object(cli, "wechat_installed_or_running", return_value=(True, True)),
            mock.patch("replay_mp3_studio.utils.find_ffmpeg", return_value="C:/ffmpeg.exe"),
            mock.patch(
                "replay_mp3_studio.web_tools.web_tools_status",
                return_value={
                    "yt_dlp_ready": True,
                    "yt_dlp_version": "2026.8.19",
                    "javascript_runtime_ready": True,
                    "javascript_runtime": "deno",
                },
            ),
        ):
            payload = cli.preflight_payload("windows-test")
        self.assertTrue(payload["ready"])
        self.assertFalse(payload["automatic_filehelper_ready"])
        self.assertTrue(payload["manual_playback_ready"])
        self.assertTrue(payload["web_link_ready"])
        self.assertEqual(payload["desktop_automation_mode"], "user_confirmed_manual_playback")
        self.assertIn("文件传输助手", " ".join(payload["windows_manual_steps"]))

    def test_windows_manual_cli_refuses_when_wechat_is_not_running(self) -> None:
        with (
            mock.patch.object(cli.platform, "system", return_value="Windows"),
            mock.patch.object(cli, "wechat_installed_or_running", return_value=(True, False)),
        ):
            with self.assertRaisesRegex(RuntimeError, "WeChat is not running"):
                cli._cmd_run_private(
                    SimpleNamespace(
                        url="https://weixin.qq.com/sph/Abc123",
                        manual_playback=True,
                    )
                )

    def test_windows_uses_shared_youtube_route_without_touching_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                user_storage.DATA_ROOT_ENV: str(root / "data"),
                user_storage.OUTPUT_ROOT_ENV: str(root / "outputs"),
            }
            args = SimpleNamespace(
                url="https://www.youtube.com/watch?v=AbC_123-xYz",
                manual_playback=False,
                profile="",
                output="",
                capture_window=1,
                min_duration=0.0,
            )
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(cli.platform, "system", return_value="Windows"),
                mock.patch.object(
                    cli,
                    "wechat_installed_or_running",
                    side_effect=AssertionError("non-Weixin route must not inspect WeChat"),
                ),
                mock.patch.object(extractors, "run_other_site") as run_other,
                mock.patch.object(
                    utils,
                    "verify_mp3",
                    return_value={"bytes": 321, "duration_seconds": 12.5},
                ),
            ):
                result = cli._cmd_run_private(args)
        self.assertEqual(result, 0)
        run_other.assert_called_once()
        self.assertIn("AbC_123-xYz", run_other.call_args.args[0])

    def test_windows_uses_shared_xiaohongshu_route_without_touching_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                user_storage.DATA_ROOT_ENV: str(root / "data"),
                user_storage.OUTPUT_ROOT_ENV: str(root / "outputs"),
            }
            args = SimpleNamespace(
                url=(
                    "https://www.xiaohongshu.com/fe/live-h5/page/live_replay/570"
                    "?host_id=88"
                ),
                manual_playback=False,
                profile="",
                output="",
                capture_window=1,
                min_duration=0.0,
            )
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(cli.platform, "system", return_value="Windows"),
                mock.patch.object(
                    cli,
                    "wechat_installed_or_running",
                    side_effect=AssertionError("non-Weixin route must not inspect WeChat"),
                ),
                mock.patch.object(extractors, "run_xiaohongshu") as run_xhs,
                mock.patch.object(
                    utils,
                    "verify_mp3",
                    return_value={"bytes": 654, "duration_seconds": 25.0},
                ),
            ):
                result = cli._cmd_run_private(args)
        self.assertEqual(result, 0)
        run_xhs.assert_called_once()

    def test_windows_rejects_weixin_manual_flag_for_other_platforms(self) -> None:
        args = SimpleNamespace(
            url="https://x.com/example/status/2091487928124047817",
            manual_playback=True,
        )
        with mock.patch.object(cli.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "only valid for a Weixin"):
                cli._cmd_run_private(args)

    def test_windows_ffmpeg_discovery_uses_venv_scripts_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg = root / "work" / "venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win.exe"
            ffmpeg.parent.mkdir(parents=True)
            ffmpeg.write_bytes(b"binary")
            with (
                mock.patch.object(utils, "PROJECT_ROOT", root),
                mock.patch.object(utils.shutil, "which", return_value=None),
                mock.patch.dict(os.environ, {"FFMPEG": ""}, clear=False),
            ):
                self.assertEqual(utils.find_ffmpeg(), str(ffmpeg))

    def test_windows_web_tools_use_venv_scripts_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "work" / "venv" / "Scripts"
            scripts.mkdir(parents=True)
            yt_dlp = scripts / "yt-dlp.exe"
            deno = scripts / "deno.exe"
            yt_dlp.write_bytes(b"tool")
            deno.write_bytes(b"tool")
            with mock.patch.object(web_tools.shutil, "which", return_value="C:/system/yt-dlp.exe"):
                self.assertEqual(web_tools.yt_dlp_command(root), [str(yt_dlp.resolve())])
            self.assertEqual(web_tools.javascript_runtime(root), ("deno", str(deno.resolve())))

    def test_bootstrap_detects_pinned_windows_web_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            scripts = runtime / "work" / "venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "yt-dlp.exe").write_bytes(b"tool")
            (scripts / "deno.exe").write_bytes(b"tool")
            with mock.patch.object(bootstrap, "RUNTIME_ROOT", runtime):
                tools = bootstrap.installed_web_tools()
        self.assertTrue(tools["yt_dlp"].endswith("yt-dlp.exe"))
        self.assertTrue(tools["deno"].endswith("deno.exe"))

    def test_windows_without_confirmation_stops_before_ui_or_runtime_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.mp3"
            artifacts = root / "artifacts"
            with (
                mock.patch.object(
                    extractors,
                    "run_weixin_source_vault_artifact",
                    return_value={"name": "source_vault_artifact", "success": False},
                ),
                mock.patch.object(
                    extractors,
                    "run_weixin_direct_link_probe",
                    return_value={"name": "direct_link_provider_probe", "success": False},
                ),
                mock.patch.object(extractors, "open_weixin_target") as open_target,
                mock.patch.object(extractors, "run_weixin_manual_playback_capture") as scan,
            ):
                with self.assertRaisesRegex(RuntimeError, "Manual playback is required"):
                    extractors.run_weixin_link(
                        "https://weixin.qq.com/sph/Abc123",
                        output,
                        artifacts,
                        lambda _message: None,
                        desktop_automation_available=False,
                    )
            open_target.assert_not_called()
            scan.assert_not_called()
            diagnostic = json.loads(
                (artifacts / "weixin_link_diagnostics.json").read_text(encoding="utf-8")
            )
        self.assertIn("No unbound runtime scan was started", diagnostic["summary"])

    def test_confirmed_windows_manual_route_does_not_call_macos_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(
                    extractors,
                    "run_weixin_source_vault_artifact",
                    return_value={"name": "source_vault_artifact", "success": False},
                ),
                mock.patch.object(
                    extractors,
                    "run_weixin_direct_link_probe",
                    return_value={"name": "direct_link_provider_probe", "success": False},
                ),
                mock.patch.object(
                    extractors,
                    "run_weixin_manual_playback_capture",
                    return_value={"name": "manual", "success": True},
                ) as manual,
                mock.patch.object(extractors, "open_weixin_target") as open_target,
            ):
                extractors.run_weixin_link(
                    "https://weixin.qq.com/sph/Abc123",
                    root / "output.mp3",
                    root / "artifacts",
                    lambda _message: None,
                    manual_playback=True,
                    desktop_automation_available=False,
                )
            manual.assert_called_once()
            open_target.assert_not_called()

    def test_directshow_device_listing_and_capture_arguments(self) -> None:
        extractor_root = ROOT / "video-audio-extractor"
        if str(extractor_root) not in sys.path:
            sys.path.insert(0, str(extractor_root))
        recorder = importlib.import_module("src.blackbox_recorder")
        stderr = '\n'.join(
            [
                '[dshow @ 000] "Microphone Array" (audio)',
                '[dshow @ 000] "Stereo Mix" (audio)',
            ]
        )
        with (
            mock.patch.object(recorder.platform, "system", return_value="Windows"),
            mock.patch.object(recorder, "require_ffmpeg", return_value="C:/ffmpeg.exe"),
            mock.patch.object(
                recorder.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stdout="", stderr=stderr),
            ),
        ):
            devices = recorder.list_avfoundation_devices()
        self.assertEqual(devices["capture_backend"], "dshow")
        self.assertEqual(devices["audio_devices"], ["Microphone Array", "Stereo Mix"])
        self.assertEqual(
            recorder._ffmpeg_capture_input("Stereo Mix", system="Windows"),
            (["-f", "dshow", "-i", "audio=Stereo Mix"], "dshow"),
        )

    def test_recording_fallback_requires_explicit_playback_confirmation(self) -> None:
        args = SimpleNamespace(
            playback_confirmed=False,
            audio_device="Stereo Mix",
            duration=10.0,
            speed=1.0,
        )
        with mock.patch.object(cli.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "explicit-only"):
                cli.cmd_record(args)

    def test_xwechat_runtime_name_is_not_mistaken_for_chat_database(self) -> None:
        scanner = load_script(
            "windows_marker_scanner_test",
            "outputs/authorized_fetchers/weixin_recent_media_marker_scan.py",
        )
        self.assertFalse(scanner.should_skip(Path("C:/Users/test/AppData/Tencent/xwechat/radium")))
        self.assertTrue(scanner.should_skip(Path("C:/Users/test/AppData/Tencent/xwechat/message")))


if __name__ == "__main__":
    unittest.main()
