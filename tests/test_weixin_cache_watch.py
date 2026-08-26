import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_cache_watch_to_mp3.py"
spec = importlib.util.spec_from_file_location("weixin_cache_watch_to_mp3", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

SOURCE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_radium_source_to_mp3.py"
source_spec = importlib.util.spec_from_file_location("weixin_radium_source_to_mp3", SOURCE_SCRIPT)
source_module = importlib.util.module_from_spec(source_spec)
assert source_spec.loader is not None
sys.modules[source_spec.name] = source_module
source_spec.loader.exec_module(source_module)

CDNCOMM_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_cdncomm_source_to_mp3.py"
cdncomm_spec = importlib.util.spec_from_file_location("weixin_cdncomm_source_to_mp3", CDNCOMM_SCRIPT)
cdncomm_module = importlib.util.module_from_spec(cdncomm_spec)
assert cdncomm_spec.loader is not None
sys.modules[cdncomm_spec.name] = cdncomm_module
cdncomm_spec.loader.exec_module(cdncomm_module)

PROFILE_STATE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_profile_state_to_mp3.py"
profile_state_spec = importlib.util.spec_from_file_location("weixin_profile_state_to_mp3", PROFILE_STATE_SCRIPT)
profile_state_module = importlib.util.module_from_spec(profile_state_spec)
assert profile_state_spec.loader is not None
sys.modules[profile_state_spec.name] = profile_state_module
profile_state_spec.loader.exec_module(profile_state_module)

ENCRYPTED_PROBE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "outputs" / "authorized_fetchers" / "weixin_encrypted_candidate_probe.py"
encrypted_probe_spec = importlib.util.spec_from_file_location("weixin_encrypted_candidate_probe", ENCRYPTED_PROBE_SCRIPT)
encrypted_probe_module = importlib.util.module_from_spec(encrypted_probe_spec)
assert encrypted_probe_spec.loader is not None
sys.modules[encrypted_probe_spec.name] = encrypted_probe_module
encrypted_probe_spec.loader.exec_module(encrypted_probe_module)


class WeixinCacheWatchTests(unittest.TestCase):
    def test_treats_suffixless_blob_storage_file_as_media_candidate(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
            "app_data/radium/web/profiles/multitab_x/blob_storage/uuid/1"
        )

        self.assertTrue(module.likely_candidate(path, 2_000_000, 50_000))

    def test_rejects_database_files_even_when_large(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
            "xwechat_files/wxid/db_storage/message/message_0.db"
        )

        self.assertFalse(module.likely_candidate(path, 100_000_000, 50_000))

    def test_rejects_webview_gpu_cache_noise(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
            "app_data/radium/web/profiles/multitab_x/GPUCache/data_1"
        )

        self.assertFalse(module.likely_candidate(path, 270_336, 50_000))

    def test_rejects_mmap_log_cache_noise(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
            "app_data/radium/cache/main.mmap"
        )

        self.assertFalse(module.likely_candidate(path, 204_800, 50_000))

    def test_rejects_message_video_temp_when_radium_only(self):
        path = pathlib.Path(
            "/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
            "xwechat_files/wxid/cache/2026-06/Message/abc/VideoTemp/123_video_temp"
        )

        self.assertFalse(module.allowed_by_scope(path, radium_only=True))

    def test_extracts_duration_from_ffmpeg_output(self):
        output = "Input #0\n  Duration: 01:25:04.44, start: 0.000000, bitrate: 483 kb/s\n"

        self.assertEqual(module.duration_seconds(output), 5104.44)

    def test_radium_source_accepts_finder_stodownload_url(self):
        url = (
            "https://finder.video.qq.com/251/20302/stodownload?"
            "encfilekey=abc&token=def&idx=1"
        )

        self.assertTrue(source_module.is_source_url(url))
        self.assertLess(source_module.source_score(url), 30)

    def test_radium_source_scans_kvcomm_root(self):
        roots = [path.as_posix() for path in source_module.RADIIUM_ROOTS]

        self.assertTrue(any("/app_data/net/kvcomm" in root for root in roots))

    def test_radium_source_classifies_opaque_stodownload_payload(self):
        payload = source_module.classify_initial_payload(
            {"content-type": "video/mp4", "content-range": "bytes 0-4095/423307600"},
            bytes.fromhex("5ae23ed7c8072333b8a16e432e8605a7"),
        )

        self.assertEqual(payload["container_signature"], "unknown")
        self.assertTrue(payload["encrypted_or_obfuscated"])

    def test_radium_source_classifies_plain_mp4_payload(self):
        payload = source_module.classify_initial_payload(
            {"content-type": "video/mp4"},
            b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00",
        )

        self.assertEqual(payload["container_signature"], "mp4")
        self.assertFalse(payload["encrypted_or_obfuscated"])

    def test_radium_source_rejects_ad_and_image_urls(self):
        self.assertFalse(
            source_module.is_source_url(
                "https://wxsmw.wxs.qq.com/131/20210/snssvpdownload/SH/reserved/ads_svp_video.mp4?x=1"
            )
        )
        self.assertFalse(
            source_module.is_source_url(
                "https://store.mp.video.tencent-cloud.com/a/b?imageView2/1/w/583/format/webp"
            )
        )

    def test_radium_source_cleans_embedded_json_tail(self):
        raw = (
            "https://finder.video.qq.com/251/20302/stodownload?"
            "encfilekey=abc%26token%3Ddef\"},\"next\":1"
        )

        cleaned = source_module.clean_url(raw)

        self.assertIn("token=def", cleaned)
        self.assertNotIn("next", cleaned)

    def test_radium_source_scans_json_escaped_stodownload_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "payload.bin"
            path.write_text(
                '{"url":"https:\\/\\/finder.video.qq.com\\/251\\/20302\\/stodownload?encfilekey=abc\\u0026token=def"}',
                encoding="utf-8",
            )

            candidates = source_module.scan_file(path, max_read_bytes=10000)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].url,
            "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def",
        )

    def test_radium_source_snapshots_candidate_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "payload.statistic"
            path.write_text(
                '{"url":"https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=def"}',
                encoding="utf-8",
            )
            candidates = source_module.scan_file(path, max_read_bytes=10000)

            snapshot = source_module.snapshot_candidate_sources(
                candidates,
                root / "snapshots",
                max_read_bytes=32,
            )

            self.assertEqual(snapshot["snapshot_count"], 1)
            self.assertTrue(pathlib.Path(snapshot["snapshots"][0]["source_snapshot_path"]).exists())
            self.assertEqual(snapshot["snapshots"][0]["bytes_copied"], 32)
            self.assertTrue(snapshot["snapshots"][0]["truncated"])

    def test_encrypted_candidate_probe_redacts_key_material_and_reports_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "capture.json"
            source.write_text(
                '{"url":"https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",'
                '"exportkey":"privateExportKey123"}',
                encoding="utf-8",
            )
            old_range_probe = encrypted_probe_module.range_probe
            old_prepare_wasm = encrypted_probe_module._prepare_wasm_dir
            old_test_string_key = encrypted_probe_module.test_string_key

            def fake_range_probe(_url, **_kwargs):
                return {
                    "ok": True,
                    "prefix": b"encrypted-prefix",
                    "summary": {
                        "range_status": 206,
                        "content_type": "video/mp4",
                        "first_bytes_class": "binary_unknown_or_encrypted",
                    },
                }

            def fake_test_string_key(_prefix, decode_key, **_kwargs):
                self.assertEqual(decode_key, "privateExportKey123")
                return {"first_bytes_class": "mp4_container", "first16_hex": "0000001866747970", "mp4_header": True}

            try:
                encrypted_probe_module.range_probe = fake_range_probe
                encrypted_probe_module._prepare_wasm_dir = lambda work_dir, wasm_dir: root
                encrypted_probe_module.test_string_key = fake_test_string_key
                report = encrypted_probe_module.build_probe_report([source], work_dir=root / "work")
            finally:
                encrypted_probe_module.range_probe = old_range_probe
                encrypted_probe_module._prepare_wasm_dir = old_prepare_wasm
                encrypted_probe_module.test_string_key = old_test_string_key

        encoded = str(report)
        self.assertEqual(report["result"], "mp4_header_decrypted")
        self.assertIn("exportkey", encoded)
        self.assertNotIn("privateExportKey123", encoded)
        self.assertNotIn("token=secret", encoded)

    def test_encrypted_candidate_probe_writes_success_artifact_with_expected_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "capture.json"
            source.write_text(
                '{"url":"https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",'
                '"key":222222222,"encLimit":131072}',
                encoding="utf-8",
            )
            old_range_probe = encrypted_probe_module.range_probe
            old_test_numeric_key = encrypted_probe_module.test_numeric_key

            def fake_range_probe(_url, **_kwargs):
                return {
                    "ok": True,
                    "prefix": b"encrypted-prefix",
                    "summary": {
                        "range_status": 206,
                        "content_type": "video/mp4",
                        "content_length": "131072",
                        "content_range": "bytes 0-131071/423307600",
                        "first_bytes_class": "binary_unknown_or_encrypted",
                    },
                }

            def fake_test_numeric_key(_prefix, key, *, enc_limit):
                self.assertEqual(key, 222222222)
                self.assertEqual(enc_limit, 131072)
                return {"first_bytes_class": "mp4_container", "first16_hex": "0000002066747970", "mp4_header": True}

            try:
                encrypted_probe_module.range_probe = fake_range_probe
                encrypted_probe_module.test_numeric_key = fake_test_numeric_key
                report = encrypted_probe_module.build_probe_report(
                    [source],
                    work_dir=root / "work",
                    sensitive_artifact_dir=root / "sensitive",
                )
            finally:
                encrypted_probe_module.range_probe = old_range_probe
                encrypted_probe_module.test_numeric_key = old_test_numeric_key

            artifact = pathlib.Path(report["numeric_key_pair_artifact"])
            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "mp4_header_decrypted")
        self.assertEqual(payload["pairs"][0]["expected_bytes"], 423307600)
        self.assertEqual(payload["pairs"][0]["content_type"], "video/mp4")

    def test_cdncomm_source_extracts_binary_url_and_query_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.cdninfo"
            path.write_bytes(
                b"\x00\x01"
                b"https://szzjwxsns.video.qq.com/102/20202/snsvideodownload?"
                b"encfilekey=abc&token=def&idx=1&dur=10\x00"
            )

            candidates = cdncomm_module.scan_file(path, max_read_bytes=10000)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_kind, "url")
        self.assertEqual(candidates[0].query_duration, 10)
        self.assertEqual(candidates[0].query_index, "1")
        self.assertEqual(
            candidates[0].redacted_value,
            "https://szzjwxsns.video.qq.com/102/20202/snsvideodownload?<redacted>",
        )

    def test_cdncomm_local_path_probe_does_not_succeed_when_path_gone(self):
        candidate = cdncomm_module.CdnCandidate(
            source_kind="local_path",
            value="/Users/test/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid/cache/Sns/Video/xx.tmp",
            redacted_value="~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid/cache/Sns/Video/xx.tmp",
            source_path="/tmp/sample.cdninfo",
            relative_path="/tmp/sample.cdninfo",
            source_bytes=100,
            source_mtime=0,
            score=100,
            query_duration=0,
            query_index="",
        )

        result = cdncomm_module.probe(candidate, timeout=1)

        self.assertFalse(result["exists"])
        self.assertFalse(result["audio"])

    def test_profile_state_normalizes_weixin_media_url(self):
        normalized = profile_state_module.normalize_media_url(
            "http://wxapp.tc.qq.com/251/20302/stodownload?filekey=abc",
            "&token=def",
        )

        self.assertEqual(
            normalized,
            "https://finder.video.qq.com/251/20302/stodownload?filekey=abc&token=def&web=1&fexam=1",
        )

    def test_profile_state_marks_bridge_script_residual(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "000001.log"
            path.write_text(
                'const replayFrom = () => {}; "url":"https://finder.video.qq.com/251/20302/stodownload?filekey=abc"',
                encoding="utf-8",
            )

            candidates = profile_state_module.scan_file(path, max_read_bytes=10000, context_radius=200)

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].script_residual)

    def test_profile_state_rebuilds_candidate_from_url_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "000001.log"
            path.write_text(
                '{"media":[{"url":"http://wxapp.tc.qq.com/251/20302/stodownload?filekey=abc",'
                '"urlToken":"&token=defghijklmnopqrstuvwxyz"}]}',
                encoding="utf-8",
            )

            candidates = profile_state_module.scan_file(path, max_read_bytes=10000, context_radius=200)

        values = {candidate.value for candidate in candidates}
        self.assertIn(
            "https://finder.video.qq.com/251/20302/stodownload?filekey=abc&token=defghijklmnopqrstuvwxyz&web=1&fexam=1",
            values,
        )

    def test_profile_state_rejects_cover_image_url(self):
        self.assertFalse(
            profile_state_module.is_media_url(
                "https://finder.video.qq.com/251/20302/stodownload-cover.jpg?token=abc"
            )
        )


if __name__ == "__main__":
    unittest.main()
