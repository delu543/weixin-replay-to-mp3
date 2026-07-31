from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_mp3_studio.weixin_source_pairs import (
    decode_key_marker_inventory_from_text,
    extract_decode_key_pairs_from_text,
    extract_numeric_key_pairs_from_text,
    redacted_numeric_key_pair_summary,
    redacted_pair_summary,
)


MULTI_OPEN_SCRIPT = Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_multi_open_capture.py"
multi_open_spec = importlib.util.spec_from_file_location("weixin_multi_open_capture", MULTI_OPEN_SCRIPT)
multi_open_module = importlib.util.module_from_spec(multi_open_spec)
assert multi_open_spec.loader is not None
multi_open_spec.loader.exec_module(multi_open_module)

CANDIDATE_CLASSIFIER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_candidate_url_classifier.py"
)
candidate_classifier_spec = importlib.util.spec_from_file_location(
    "weixin_candidate_url_classifier",
    CANDIDATE_CLASSIFIER_SCRIPT,
)
candidate_classifier_module = importlib.util.module_from_spec(candidate_classifier_spec)
assert candidate_classifier_spec.loader is not None
candidate_classifier_spec.loader.exec_module(candidate_classifier_module)


class WeixinSourcePairTests(unittest.TestCase):
    def test_multi_open_sends_once_then_reuses_verified_message(self) -> None:
        url = "https://weixin.qq.com/sph/A1TN6kx8js"
        with patch.object(
            multi_open_module,
            "open_weixin_filehelper",
            return_value={"sent_new_message": True},
        ) as first_open, patch.object(
            multi_open_module,
            "reopen_verified_filehelper_link",
            return_value={"sent_new_message": False, "reused_verified_message": True},
        ) as retry_open:
            first = multi_open_module.open_authorized_link_for_round(url, 1, timeout=25)
            retry = multi_open_module.open_authorized_link_for_round(url, 2, timeout=25)

        first_open.assert_called_once_with(url, click_after_send=True, timeout=25)
        retry_open.assert_called_once_with(url, timeout=25)
        self.assertTrue(first["sent_new_message"])
        self.assertFalse(retry["sent_new_message"])
        self.assertTrue(retry["reused_verified_message"])

    def test_extract_decode_key_pairs_from_escaped_json_context(self) -> None:
        payload = (
            r'{"mediaUrl":"https:\/\/finder.video.qq.com\/251\/20302\/stodownload'
            r'?token=secret&encfilekey=secret","decodeKey":"0123456789abcdef"}'
        )

        pairs = extract_decode_key_pairs_from_text(payload, path="sample")

        self.assertEqual(len(pairs), 1)
        self.assertIn("stodownload", pairs[0]["url"])
        self.assertEqual(pairs[0]["decode_key"], "0123456789abcdef")

    def test_extract_decode_key_pairs_accepts_decrypt_key_alias(self) -> None:
        payload = (
            '{"mediaUrl":"https://finder.video.qq.com/251/20302/stodownload?token=secret",'
            '"decryptKey":"aliasDecryptKey123"}'
        )

        pairs = extract_decode_key_pairs_from_text(payload, path="sample")
        summary = redacted_pair_summary(pairs)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["decode_key"], "aliasDecryptKey123")
        self.assertEqual(pairs[0]["key_field"], "decryptKey")
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertIn("decryptKey", encoded)
        self.assertNotIn("aliasDecryptKey123", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_extract_numeric_key_pairs_from_ltaoo_style_artifact(self) -> None:
        payload = (
            '{"url":"https://finder.video.qq.com/251/20302/stodownload?token=secret",'
            '"key":123456789,"encLimit":131072}'
        )

        pairs = extract_numeric_key_pairs_from_text(payload, path="sample")
        summary = redacted_numeric_key_pair_summary(pairs)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["key"], 123456789)
        self.assertEqual(pairs[0]["enc_limit"], 131072)
        self.assertEqual(pairs[0]["key_field"], "key")
        self.assertIn("numeric_key_sha256_12", encoded)
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertNotIn("123456789", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_redacted_pair_summary_does_not_leak_key_or_query(self) -> None:
        pairs = [
            {
                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                "decode_key": "0123456789abcdef",
                "path": "sample",
            }
        ]

        encoded = json.dumps(redacted_pair_summary(pairs), ensure_ascii=False)

        self.assertIn("decode_key_sha256_12", encoded)
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_far_away_key_and_url_do_not_pair_with_small_context(self) -> None:
        payload = (
            "https://finder.video.qq.com/251/20302/stodownload?token=secret"
            + ("x" * 200)
            + '"decodeKey":"0123456789abcdef"'
        )

        pairs = extract_decode_key_pairs_from_text(payload, context_radius=20)

        self.assertEqual(pairs, [])

    def test_decode_key_marker_inventory_detects_alias_without_leaking_values(self) -> None:
        payload = (
            '{"url":"https://finder.video.qq.com/251/20302/stodownload?token=secret",'
            '"decryptKey":"privateDecryptMaterial123"}'
        )

        inventory = decode_key_marker_inventory_from_text(payload, path="sample")
        encoded = json.dumps(inventory, ensure_ascii=False)

        self.assertEqual(inventory["marker_count"], 1)
        self.assertEqual(inventory["near_media_count"], 1)
        self.assertEqual(inventory["field_counts"], {"decryptKey": 1})
        self.assertEqual(inventory["markers"][0]["field_name"], "decryptKey")
        self.assertEqual(inventory["markers"][0]["value_length"], len("privateDecryptMaterial123"))
        self.assertIn("value_sha256_12", inventory["markers"][0])
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertNotIn("privateDecryptMaterial123", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_decode_key_marker_inventory_ignores_encfilekey_query_param(self) -> None:
        payload = "https://finder.video.qq.com/251/20302/stodownload?token=secret&encfilekey=notDecodeKey"

        inventory = decode_key_marker_inventory_from_text(payload, path="sample")

        self.assertEqual(inventory["marker_count"], 0)
        self.assertEqual(inventory["near_media_count"], 0)

    def test_multi_open_scans_child_report_source_files_for_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "radium-state.txt"
            report = root / "child-report.json"
            source.write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "0123456789abcdef",
                    }
                ),
                encoding="utf-8",
            )
            report.write_text(
                json.dumps({"files_with_hits": [{"relative_path": str(source)}]}),
                encoding="utf-8",
            )

            result = multi_open_module.scan_decode_pairs_from_reports([report], max_read_bytes=100_000)

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["source_file_count"], 1)
        self.assertEqual(result["files_with_pairs"], 1)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "0123456789abcdef")
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_scans_source_file_decrypt_key_alias_for_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "radium-state.txt"
            report = root / "child-report.json"
            source.write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decryptKey": "sourceAliasDecrypt123",
                    }
                ),
                encoding="utf-8",
            )
            report.write_text(
                json.dumps({"files_with_hits": [{"relative_path": str(source)}]}),
                encoding="utf-8",
            )

            result = multi_open_module.scan_decode_pairs_from_reports([report], max_read_bytes=100_000)

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["source_file_count"], 1)
        self.assertEqual(result["files_with_pairs"], 1)
        self.assertEqual(result["report_files_with_pairs"], 0)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "sourceAliasDecrypt123")
        self.assertEqual(result["pairs"][0]["key_field"], "decryptKey")
        self.assertIn("decryptKey", encoded)
        self.assertNotIn("sourceAliasDecrypt123", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_rescans_existing_run_dir_without_reopening_wechat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "round-01"
            round_dir.mkdir()
            source = root / "profile-state.txt"
            child_report = round_dir / "profile-state.json"
            source.write_text(
                json.dumps(
                    {
                        "media": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "fedcba9876543210",
                    }
                ),
                encoding="utf-8",
            )
            child_report.write_text(
                json.dumps({"candidates": [{"source_path": str(source)}]}),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dir(root, max_read_bytes=100_000)

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["child_report_count"], 1)
        self.assertEqual(result["source_file_count"], 1)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "fedcba9876543210")
        self.assertNotIn("fedcba9876543210", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_rescan_scans_child_report_text_for_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "round-01"
            round_dir.mkdir()
            child_report = round_dir / "radium-source.json"
            child_report.write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                                "decodeKey": "feedface12345678",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dir(root, max_read_bytes=100_000)

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["report_files_scanned"], 1)
        self.assertEqual(result["report_files_with_pairs"], 1)
        self.assertEqual(result["source_file_count"], 0)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "feedface12345678")
        self.assertNotIn("feedface12345678", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_rescan_reports_missing_referenced_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "round-01"
            round_dir.mkdir()
            existing = root / "existing-state.txt"
            missing = root / "missing-state.txt"
            child_report = round_dir / "profile-state.json"
            existing.write_text("{}", encoding="utf-8")
            child_report.write_text(
                json.dumps(
                    {
                        "candidates": [
                            {"source_path": str(existing)},
                            {"source_path": str(missing)},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dir(root, max_read_bytes=100_000)

        self.assertEqual(result["source_file_reference_count"], 2)
        self.assertEqual(result["source_file_count"], 1)
        self.assertEqual(result["missing_source_file_count"], 1)

    def test_multi_open_rescan_uses_preserved_sensitive_source_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "round-01"
            round_dir.mkdir()
            source = root / "volatile-profile-state.txt"
            child_report = round_dir / "profile-state.json"
            snapshot_report = round_dir / "source-snapshots.json"
            source.write_text(
                json.dumps(
                    {
                        "media": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "decafbad12345678",
                    }
                ),
                encoding="utf-8",
            )
            child_report.write_text(
                json.dumps({"candidates": [{"source_path": str(source)}]}),
                encoding="utf-8",
            )

            snapshot = multi_open_module.snapshot_source_files_from_reports(
                [child_report],
                root / "sensitive-source-snapshots",
                max_read_bytes=100_000,
            )
            snapshot_report.write_text(json.dumps(snapshot), encoding="utf-8")
            source.unlink()

            result = multi_open_module.rescan_decode_pairs_in_run_dir(root, max_read_bytes=100_000)

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["missing_source_file_count"], 1)
        self.assertGreaterEqual(result["source_file_count"], 1)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "decafbad12345678")
        self.assertNotIn("decafbad12345678", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_rescan_scans_extra_run_dirs_and_source_snapshot_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary-run"
            extra = root / "extra-run"
            snapshot_root = root / "source-snapshots"
            primary.mkdir()
            (extra / "round-01").mkdir(parents=True)
            snapshot_root.mkdir()
            child_report = extra / "round-01" / "marker-scan.json"
            source_snapshot = snapshot_root / "001-source"
            child_report.write_text(
                json.dumps({"files_with_hits": [{"relative_path": str(source_snapshot)}]}),
                encoding="utf-8",
            )
            source_snapshot.write_text(
                json.dumps(
                    {
                        "media": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "aabbccdd12345678",
                    }
                ),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dirs(
                [primary, extra],
                source_snapshot_roots=[snapshot_root],
                max_read_bytes=100_000,
            )

        encoded = json.dumps(result["redacted_pair_summary"], ensure_ascii=False)
        self.assertEqual(result["run_dir_count"], 2)
        self.assertEqual(result["source_snapshot_file_count"], 1)
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["pairs"][0]["decode_key"], "aabbccdd12345678")
        self.assertNotIn("aabbccdd12345678", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_rescan_ignores_unrelated_json_artifacts_under_broad_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unrelated = root / "source-artifact-smoke"
            unrelated.mkdir()
            (unrelated / "authorized-resolver.json").write_text(
                json.dumps(
                    {
                        "media": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "synthetic12345678",
                    }
                ),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dirs([root], max_read_bytes=100_000)

        self.assertEqual(result["pair_count"], 0)
        self.assertEqual(result["report_files_with_pairs"], 0)

    def test_multi_open_rescan_reports_decode_marker_inventory_without_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "round-01"
            round_dir.mkdir()
            child_report = round_dir / "profile-state.json"
            child_report.write_text(
                json.dumps(
                    {
                        "candidate": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decryptKey": "privateDecryptMaterial123",
                    }
                ),
                encoding="utf-8",
            )

            result = multi_open_module.rescan_decode_pairs_in_run_dir(root, max_read_bytes=100_000)

        encoded = json.dumps(result["decode_key_marker_inventory"], ensure_ascii=False)
        self.assertEqual(result["pair_count"], 0)
        self.assertEqual(result["decode_key_marker_inventory"]["marker_count"], 1)
        self.assertEqual(result["decode_key_marker_inventory"]["near_media_count"], 1)
        self.assertIn("decryptKey", encoded)
        self.assertNotIn("privateDecryptMaterial123", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_multi_open_filesystem_delta_scans_changed_safe_files_for_pairs_without_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = multi_open_module.snapshot_safe_file_state([root], max_file_bytes=100_000, max_files=50)
            changed = root / "app_data" / "radium" / "source.json"
            changed.parent.mkdir(parents=True)
            changed.write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "decodeKey": "0123456789abcdef",
                    }
                ),
                encoding="utf-8",
            )
            private_db = root / "xwechat_files" / "wxid_test" / "db_storage" / "message" / "message_0.db"
            private_db.parent.mkdir(parents=True)
            private_db.write_text(
                "https://finder.video.qq.com/private/stodownload?token=secret decodeKey=leakleak",
                encoding="utf-8",
            )

            after = multi_open_module.snapshot_safe_file_state([root], max_file_bytes=100_000, max_files=50)
            delta = multi_open_module.scan_safe_file_delta(before, after, max_read_bytes=100_000)
            raw_pairs = delta.pop("pairs")

        self.assertEqual(len(raw_pairs), 1)
        self.assertEqual(delta["changed_file_count"], 1)
        self.assertEqual(delta["decode_key_pair_count"], 1)
        encoded = json.dumps(delta, ensure_ascii=False)
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("message_0.db", encoded)

    def test_multi_open_filesystem_delta_scans_numeric_key_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = multi_open_module.snapshot_safe_file_state([root], max_file_bytes=100_000, max_files=50)
            changed = root / "listener" / "numeric.json"
            changed.parent.mkdir(parents=True)
            changed.write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?token=secret",
                        "key": 123456789,
                        "encLimit": 65536,
                    }
                ),
                encoding="utf-8",
            )

            after = multi_open_module.snapshot_safe_file_state([root], max_file_bytes=100_000, max_files=50)
            delta = multi_open_module.scan_safe_file_delta(before, after, max_read_bytes=100_000)
            raw_numeric_pairs = delta.pop("numeric_pairs")

        self.assertEqual(len(raw_numeric_pairs), 1)
        self.assertEqual(raw_numeric_pairs[0]["key"], 123456789)
        self.assertEqual(delta["numeric_key_pair_count"], 1)
        encoded = json.dumps(delta, ensure_ascii=False)
        self.assertNotIn("123456789", encoded)

    def test_multi_open_sanitizes_child_report_urls_and_keys_after_pair_extraction(self) -> None:
        payload = {
            "probes": [
                {
                    "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=secret&token=secret",
                    "decodeKey": "0123456789abcdef",
                }
            ],
            "numeric": {"key": 123456789},
            "stdout_tail": (
                "https://wst.wxapp.tc.qq.com/161/20304/snscosdownload/SH/reserved/"
                "63f87ce80004532e2a44211f6a34b00b000000a100004f50 "
                "https%3A%2F%2Ffinder.video.qq.com%2F251%2F20302%2Fstodownload%3Ftoken%3Dsecret"
            ),
        }

        sanitized = multi_open_module.sanitize_child_report_payload(payload)
        encoded = json.dumps(sanitized, ensure_ascii=False)

        self.assertIn("stodownload?<redacted>", encoded)
        self.assertIn("https://wst.wxapp.tc.qq.com/<redacted-media-path>", encoded)
        self.assertNotIn("encfilekey=secret", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("snscosdownload/SH/reserved", encoded)
        self.assertNotIn("https%3A%2F%2F", encoded)
        self.assertNotIn("0123456789abcdef", encoded)
        self.assertNotIn("123456789", encoded)

    def test_candidate_classifier_reports_snapshot_urls_without_raw_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_dir = root / "capture"
            snapshot_dir = root / "snapshots"
            round_dir = capture_dir / "round-01"
            round_dir.mkdir(parents=True)
            snapshot_dir.mkdir()
            snapshot = snapshot_dir / "sample.statistic"
            snapshot.write_text(
                "14951824894528589266,"
                "https://finder.video.qq.com/251/20302/stodownload?encfilekey=secret&token=secret "
                "https://wst.wxapp.tc.qq.com/161/20304/snscosdownload/SH/reserved/private-path",
                encoding="utf-8",
            )
            (round_dir / "source-snapshots.json").write_text(
                json.dumps(
                    {
                        "snapshots": [
                            {
                                "source_path_redacted": "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/net/kvcomm/sample.statistic",
                                "source_snapshot_path": str(snapshot),
                                "sha256_16": "fixture",
                                "source_size": snapshot.stat().st_size,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = candidate_classifier_module.build_classification(capture_dir, probe=False)
            encoded = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["unique_candidate_url_count"], 2)
        self.assertIn("stodownload?<redacted>", encoded)
        self.assertIn("https://wst.wxapp.tc.qq.com/<redacted-media-path>", encoded)
        self.assertIn("numeric_sha256_12", encoded)
        self.assertNotIn("encfilekey=secret", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("14951824894528589266", encoded)
        self.assertNotIn("private-path", encoded)


if __name__ == "__main__":
    unittest.main()
