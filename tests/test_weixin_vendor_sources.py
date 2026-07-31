from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from replay_mp3_studio.weixin_vendor_sources import (
    convert_vendor_source_to_mp3,
    load_vendor_decode_pairs,
    load_vendor_numeric_key_pairs,
    scan_vendor_source,
)
from replay_mp3_studio.weixin_runtime_capture import (
    runtime_capture_artifact_from_profiles,
    runtime_capture_snippet,
)


class WeixinVendorSourceTests(unittest.TestCase):
    def test_scan_vendor_source_reports_media_and_redacted_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "视频" / "clip.mp4"
            media.parent.mkdir()
            media.write_bytes(b"mp4" * 128)
            (root / "mitmdump.exe").write_bytes(b"exe")
            source = root / "capture.json"
            source.write_text(
                json.dumps(
                    {
                        "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                        "decodeKey": "0123456789abcdef",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = scan_vendor_source(root)
            encoded = json.dumps(report, ensure_ascii=False)

            self.assertEqual(report["local_media_candidate_count"], 1)
            self.assertEqual(report["decode_key_pair_count"], 1)
            self.assertEqual(report["skipped_executable_count"], 1)
            self.assertIn("stodownload?<redacted>", encoded)
            self.assertNotIn("token=secret", encoded)
            self.assertNotIn("0123456789abcdef", encoded)

    def test_load_vendor_decode_pairs_keeps_raw_values_for_local_conversion_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "capture.log"
            source.write_text(
                'url="https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret" '
                'decryptKey="fedcba9876543210"',
                encoding="utf-8",
            )

            pairs = load_vendor_decode_pairs(source)

            self.assertEqual(len(pairs), 1)
            self.assertIn("token=secret", pairs[0]["url"])
            self.assertEqual(pairs[0]["decode_key"], "fedcba9876543210")

    def test_load_vendor_numeric_key_pairs_accepts_ltaoo_style_key_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "capture.json"
            source.write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                        "key": 123456789,
                        "encLimit": 131072,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            pairs = load_vendor_numeric_key_pairs(source)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["key"], 123456789)
            self.assertEqual(pairs[0]["enc_limit"], 131072)

    def test_runtime_capture_artifact_accepts_ltaoo_profile_string_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "runtime-capture.json"
            artifact = runtime_capture_artifact_from_profiles(
                [
                    {
                        "type": "media",
                        "id": "feed-1",
                        "nonce_id": "nonce-1",
                        "title": "授权测试视频",
                        "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                        "key": "feedface12345678",
                        "spec": [{"fileFormat": 1}],
                    }
                ],
                page_url="https://weixin.qq.com/sph/AFfTIp5Ywj",
            )
            source.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

            pairs = load_vendor_decode_pairs(source)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["decode_key"], "feedface12345678")
            self.assertIn("token=secret", pairs[0]["url"])

    def test_runtime_capture_artifact_combines_feed_url_token_and_numeric_decode_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "runtime-capture.json"
            artifact = runtime_capture_artifact_from_profiles(
                [
                    {
                        "id": "feed-2",
                        "objectNonceId": "nonce-2",
                        "objectDesc": {
                            "mediaType": 4,
                            "description": "授权测试视频",
                            "media": [
                                {
                                    "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc",
                                    "urlToken": "&token=secret",
                                    "decodeKey": 123456789,
                                    "fileSize": 1024,
                                }
                            ],
                        },
                        "contact": {"nickname": "creator"},
                    }
                ],
                page_url="https://weixin.qq.com/sph/AFfTIp5Ywj",
            )
            source.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

            pairs = load_vendor_numeric_key_pairs(source)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["key"], 123456789)
            self.assertIn("token=secret", pairs[0]["url"])

    def test_runtime_capture_snippet_posts_only_runtime_media_fields(self) -> None:
        snippet = runtime_capture_snippet("http://127.0.0.1:8765/api/receive-artifact")

        self.assertIn("__wx_channels_store__", snippet)
        self.assertIn("__wx_channels_live_store__", snippet)
        self.assertIn("weixin_runtime_profile_capture", snippet)
        self.assertIn("if (!items.length)", snippet)
        self.assertIn("fetch(STUDIO_ENDPOINT", snippet)
        self.assertNotIn("document.cookie", snippet)
        self.assertNotIn("localStorage", snippet)
        self.assertNotIn("sessionStorage", snippet)
        self.assertNotIn("indexedDB", snippet)

    def test_convert_vendor_source_prefers_decode_pair_over_media_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out.mp3"
            (root / "clip.mp4").write_bytes(b"mp4" * 128)
            (root / "capture.json").write_text(
                json.dumps(
                    {
                        "videoUrl": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                        "decodeKey": "0123456789abcdef",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            decoded_pairs: list[dict[str, str]] = []

            def fake_decoder(pair, output_path, **_kwargs):
                decoded_pairs.append(pair)
                Path(output_path).write_bytes(b"mp3")
                return {"ok": True, "decode_key_length": len(pair["decode_key"])}

            result = convert_vendor_source_to_mp3(
                root,
                output,
                decoder=fake_decoder,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            self.assertEqual(result["source_kind"], "decode_key_pair")
            self.assertEqual(decoded_pairs[0]["decode_key"], "0123456789abcdef")
            self.assertTrue(output.exists())
            self.assertNotIn("0123456789abcdef", json.dumps(result, ensure_ascii=False))

    def test_convert_vendor_source_prefers_numeric_key_pair_over_media_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out.mp3"
            (root / "clip.mp4").write_bytes(b"mp4" * 128)
            (root / "capture.json").write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret",
                        "key": 123456789,
                        "encLimit": 131072,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            numeric_pairs: list[dict] = []

            def fake_numeric_decoder(pair, output_path, **_kwargs):
                numeric_pairs.append(pair)
                Path(output_path).write_bytes(b"mp3")
                return {"ok": True, "numeric_key_digits": len(str(pair["key"]))}

            result = convert_vendor_source_to_mp3(
                root,
                output,
                numeric_decoder=fake_numeric_decoder,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            encoded = json.dumps(result, ensure_ascii=False)
            self.assertEqual(result["source_kind"], "numeric_key_pair")
            self.assertEqual(numeric_pairs[0]["key"], 123456789)
            self.assertTrue(output.exists())
            self.assertNotIn("123456789", encoded)
            self.assertNotIn("token=secret", encoded)

    def test_convert_vendor_source_prefers_larger_verified_numeric_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out.mp3"
            source = root / "successful-numeric-key-pairs.json"
            source.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=short",
                                "key": 111111111,
                                "encLimit": 131072,
                                "expected_bytes": 1_791_828,
                            },
                            {
                                "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=complete",
                                "key": 222222222,
                                "encLimit": 131072,
                                "expected_bytes": 423_307_600,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            attempted: list[int] = []

            def fake_numeric_decoder(pair, output_path, **_kwargs):
                attempted.append(int(pair["key"]))
                Path(output_path).write_bytes(f"mp3-{pair['key']}".encode())
                return {"ok": True, "encrypted_bytes": int(pair.get("expected_bytes") or 0)}

            result = convert_vendor_source_to_mp3(
                source,
                output,
                numeric_decoder=fake_numeric_decoder,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 3587.4},
            )

            encoded = json.dumps(result, ensure_ascii=False)
            self.assertEqual(attempted, [222222222])
            self.assertEqual(result["numeric_key_pair_summary"][0]["expected_bytes"], 423_307_600)
            self.assertEqual(output.read_bytes(), b"mp3-222222222")
            self.assertNotIn("222222222", encoded)
            self.assertNotIn("token=complete", encoded)

    def test_convert_vendor_source_tries_next_numeric_pair_when_first_is_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out.mp3"
            (root / "a-short.json").write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=short",
                        "key": 111111111,
                        "encLimit": 131072,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "b-complete.json").write_text(
                json.dumps(
                    {
                        "url": "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=complete",
                        "key": 222222222,
                        "encLimit": 131072,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            attempted: list[int] = []

            def fake_numeric_decoder(pair, output_path, **_kwargs):
                attempted.append(int(pair["key"]))
                Path(output_path).write_bytes(f"mp3-{pair['key']}".encode())
                return {"ok": True, "numeric_key_digits": len(str(pair["key"]))}

            def fake_verifier(path, _log, min_duration_seconds=0):
                if Path(path).read_bytes() == b"mp3-111111111":
                    raise RuntimeError("MP3 output is shorter than required minimum: 1200.00s < 3000.00s")
                return {"ok": True, "duration_seconds": 3300.0, "min_duration_seconds": min_duration_seconds}

            result = convert_vendor_source_to_mp3(
                root,
                output,
                numeric_decoder=fake_numeric_decoder,
                verifier=fake_verifier,
                min_duration_seconds=3000,
            )

            encoded = json.dumps(result, ensure_ascii=False)
            self.assertEqual(attempted, [111111111, 222222222])
            self.assertEqual(result["source_kind"], "numeric_key_pair")
            self.assertEqual(result["verification"]["duration_seconds"], 3300.0)
            self.assertNotIn("111111111", encoded)
            self.assertNotIn("222222222", encoded)
            self.assertNotIn("token=short", encoded)
            self.assertEqual(output.read_bytes(), b"mp3-222222222")

    def test_numeric_variants_for_same_url_reuse_one_download_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out.mp3"
            source = root / "pairs.json"
            shared_url = "https://finder.video.qq.com/251/20302/stodownload?token=same"
            source.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {"url": shared_url, "key": 111111111, "encLimit": 131072},
                            {"url": shared_url, "key": 222222222, "encLimit": 65536},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            work_dirs: list[Path] = []

            def fake_numeric_decoder(pair, output_path, **kwargs):
                work_dirs.append(Path(kwargs["work_dir"]))
                Path(output_path).write_bytes(f"mp3-{pair['key']}".encode())
                return {"ok": True}

            def fake_verifier(path, _log, min_duration_seconds=0):
                if Path(path).read_bytes() == b"mp3-111111111":
                    raise RuntimeError("synthetic first variant failure")
                return {"ok": True, "duration_seconds": 3600.0}

            result = convert_vendor_source_to_mp3(
                source,
                output,
                numeric_decoder=fake_numeric_decoder,
                verifier=fake_verifier,
            )

            self.assertTrue(result["mp3_complete"])
            self.assertEqual(len(work_dirs), 2)
            self.assertEqual(work_dirs[0], work_dirs[1])

    def test_convert_vendor_source_can_convert_local_downloaded_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "downloaded.flv"
            output = root / "out.mp3"
            media.write_bytes(b"flv" * 128)
            commands: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp3")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            result = convert_vendor_source_to_mp3(
                media,
                output,
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            self.assertEqual(result["source_kind"], "local_media_file")
            self.assertEqual(commands[0][commands[0].index("-i") + 1], str(media.resolve()))
            self.assertTrue(output.exists())

    def test_convert_vendor_source_copies_existing_mp3_without_lossy_reencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "downloaded.mp3"
            output = root / "out.mp3"
            media.write_bytes(b"original-mp3-bytes")

            result = convert_vendor_source_to_mp3(
                media,
                output,
                runner=lambda *_args, **_kwargs: self.fail("MP3 reuse must not invoke ffmpeg"),
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            self.assertEqual(result["source_kind"], "local_media_file")
            self.assertEqual(result["local_media_conversion"]["mode"], "copied_verified_local_mp3")
            self.assertEqual(output.read_bytes(), media.read_bytes())

    def test_convert_vendor_source_tries_next_media_when_first_candidate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            larger = root / "larger-bad.mp4"
            smaller = root / "smaller-good.mp4"
            output = root / "out.mp3"
            larger.write_bytes(b"bad" * 256)
            smaller.write_bytes(b"good" * 128)
            attempted: list[str] = []

            def fake_runner(command, **_kwargs):
                source = command[command.index("-i") + 1]
                attempted.append(Path(source).name)
                if "larger-bad" in source:
                    return SimpleNamespace(returncode=1, stdout="", stderr="invalid media")
                Path(command[-1]).write_bytes(b"mp3")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            result = convert_vendor_source_to_mp3(
                root,
                output,
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            self.assertEqual(result["source_kind"], "local_media_file")
            self.assertEqual(attempted, ["larger-bad.mp4", "smaller-good.mp4"])
            self.assertEqual(Path(result["selected_media"]["path"]).name, "smaller-good.mp4")

    def test_convert_vendor_source_writes_report_when_no_source_candidate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "capture.json").write_text(json.dumps({"status": "no media"}), encoding="utf-8")
            report_path = root / "report.json"

            with self.assertRaisesRegex(RuntimeError, "numeric_key"):
                convert_vendor_source_to_mp3(
                    root,
                    root / "out.mp3",
                    report_path=report_path,
                    verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["mp3_complete"])
            self.assertEqual(report["scan"]["numeric_key_pair_count"], 0)
            self.assertEqual(report["scan"]["decode_key_pair_count"], 0)
            self.assertEqual(report["scan"]["file_count"], 1)
            self.assertNotIn("no media", json.dumps(report, ensure_ascii=False))

    def test_conversion_report_redacts_new_secrets_even_when_stderr_is_partly_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "downloaded.flv"
            output = root / "out.mp3"
            media.write_bytes(b"flv" * 128)

            def fake_runner(command, **_kwargs):
                Path(command[-1]).write_bytes(b"mp3")
                return SimpleNamespace(
                    returncode=0,
                    stdout="",
                    stderr=(
                        "already <redacted> but also "
                        "https://finder.video.qq.com/251/20302/stodownload?encfilekey=abc&token=secret "
                        "decodeKey=0123456789abcdef"
                    ),
                )

            result = convert_vendor_source_to_mp3(
                media,
                output,
                runner=fake_runner,
                verifier=lambda *_args, **_kwargs: {"ok": True, "duration_seconds": 10.0},
            )

            encoded = json.dumps(result, ensure_ascii=False)
            self.assertIn("stodownload?<redacted>", encoded)
            self.assertNotIn("token=secret", encoded)
            self.assertNotIn("0123456789abcdef", encoded)


if __name__ == "__main__":
    unittest.main()
