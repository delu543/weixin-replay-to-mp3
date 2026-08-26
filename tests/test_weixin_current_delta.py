import importlib.util
import json
import pathlib
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_current_playback_delta_to_mp3.py"
spec = importlib.util.spec_from_file_location("weixin_current_playback_delta_to_mp3", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class WeixinCurrentDeltaTests(unittest.TestCase):
    def test_accepts_wechat_tmp_playback_file_without_media_suffix(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp/"
            ".5A4RE8SF68.com.tencent.xinWeChat.XYZ123"
        )

        self.assertTrue(module.likely_media_candidate(path, 2_000_000, 50_000))

    def test_rejects_browser_history_noise(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/"
            "web/profiles/multitab_abc/History"
        )

        self.assertFalse(module.likely_media_candidate(path, 1_200_000, 50_000))

    def test_parses_safe_lsof_media_record(self):
        output = textwrap.dedent(
            """\
            p123
            cWeChatAppEx
            f40
            tREG
            s4600000
            n/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp/.5A4RE8SF68.com.tencent.xinWeChat.ABC
            """
        )

        tmp_root = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp"
        )
        with mock.patch.object(module, "WATCH_ROOTS", [tmp_root]):
            records = module.parse_lsof_field_output(output)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].pid, "123")
        self.assertEqual(records[0].size, 4_600_000)

    def test_diagnostic_lsof_rejects_private_wechat_database_paths(self):
        private_db = (
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/"
            "wxid_test/db_storage/message/message_0.db"
        )
        private_contact = (
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/"
            "wxid_test/db_storage/contact/contact.db-wal"
        )
        temp_playback = (
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp/"
            ".5A4RE8SF68.com.tencent.xinWeChat.ABC"
        )

        self.assertFalse(module.diagnostic_lsof_candidate(private_db))
        self.assertFalse(module.diagnostic_lsof_candidate(private_contact))
        self.assertTrue(module.diagnostic_lsof_candidate(temp_playback))

    def test_write_report_prunes_private_diagnostic_lsof_paths(self):
        private_db = (
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/"
            "wxid_test/db_storage/message/message_0.db"
        )
        temp_playback = (
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp/"
            ".5A4RE8SF68.com.tencent.xinWeChat.ABC"
        )
        report = {
            "baseline_lsof": [],
            "baseline_all_lsof": [
                {"path": private_db, "relative_path": "wxid_test/db_storage/message/message_0.db"},
                {"path": temp_playback, "relative_path": ".5A4RE8SF68.com.tencent.xinWeChat.ABC"},
            ],
            "visible_events": [],
            "lsof_events": [],
            "all_lsof_events": [
                {"path": private_db, "relative_path": "wxid_test/db_storage/message/message_0.db"}
            ],
            "unreadable_lsof": [],
            "baseline_recent_visible": [
                {"path": private_db, "relative_path": "wxid_test/db_storage/message/message_0.db"}
            ],
            "recent_visible_changes": [],
            "result": {"error": "no_playable_changed_media_file"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.json"
            module.write_report(report_path, report)
            stored = json.loads(report_path.read_text(encoding="utf-8"))

        encoded = json.dumps(stored, ensure_ascii=False)
        self.assertEqual(len(stored["baseline_all_lsof"]), 1)
        self.assertEqual(stored["all_lsof_events"], [])
        self.assertEqual(stored["baseline_recent_visible"], [])
        self.assertNotIn("message_0.db", encoded)
        self.assertIn(".5A4RE8SF68.com.tencent.xinWeChat.ABC", encoded)

    def test_report_diagnostics_identifies_unlinked_baseline_fd(self):
        report = {
            "baseline_lsof": [
                {
                    "pid": "123",
                    "command": "WeChatAppEx Helper (Renderer)",
                    "fd": "13",
                    "size": 4_600_000,
                    "relative_path": ".5A4RE8SF68.com.tencent.xinWeChat.ABC",
                    "exists_as_path": False,
                    "media_candidate": True,
                }
            ],
            "visible_events": [],
            "lsof_events": [],
            "unreadable_lsof": [],
            "recent_visible_changes": [],
            "result": {"error": "no_playable_changed_media_file"},
        }

        module.refresh_report_diagnostics(report)

        self.assertEqual(report["diagnosis"], "playback_fd_unlinked")
        self.assertEqual(report["baseline_unreadable_media_fd_count"], 1)
        self.assertEqual(report["largest_unreadable_fd_bytes"], 4_600_000)
        self.assertEqual(report["sample_unreadable_fds"][0]["fd"], "13")

    def test_unreadable_fd_access_probe_records_no_safe_filesystem_alias(self):
        rows = [
            {
                "pid": "123",
                "command": "WeChatAppEx Helper (Renderer)",
                "fd": "13",
                "size": 4_600_000,
                "path": "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/tmp/.5A4RE8SF68.com.tencent.xinWeChat.ABC",
                "relative_path": ".5A4RE8SF68.com.tencent.xinWeChat.ABC",
                "exists_as_path": False,
                "media_candidate": True,
            }
        ]

        probe = module.probe_unreadable_fd_access(
            rows,
            path_exists=lambda _path: False,
        )

        self.assertFalse(probe["safe_copy_possible"])
        self.assertEqual(probe["limit_point"], "renderer_fd_has_no_safe_filesystem_alias")
        self.assertEqual(probe["checked_count"], 1)
        first = probe["samples"][0]
        self.assertEqual(first["pid"], "123")
        self.assertEqual(first["fd"], "13")
        self.assertFalse(first["original_path_exists"])
        self.assertFalse(first["proc_pid_fd_exists"])
        self.assertFalse(first["dev_fd_pid_scoped_exists"])
        self.assertEqual(first["raw_dev_fd_probe"], "not_attempted_not_pid_scoped")


if __name__ == "__main__":
    unittest.main()
