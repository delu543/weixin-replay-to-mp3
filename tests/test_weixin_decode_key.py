from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import replay_mp3_studio.weixin_decode_key as decode_module
from replay_mp3_studio.weixin_decode_key import (
    KEYSTREAM_SIZE,
    assert_mp4_header,
    decode_key_fingerprint,
    decrypt_weixin_numeric_key_bytes,
    decrypt_weixin_encrypted_bytes,
    generate_keystream_via_node,
    numeric_key_fingerprint,
)


class WeixinDecodeKeyTests(unittest.TestCase):
    def test_decrypt_weixin_encrypted_bytes_xors_only_encrypted_prefix(self) -> None:
        plain = bytearray(b"\x00\x00\x00\x20ftypisom" + b"a" * (KEYSTREAM_SIZE + 8))
        keystream = bytes((index % 251 for index in range(KEYSTREAM_SIZE)))
        encrypted = bytearray(plain)
        for index, key_byte in enumerate(keystream):
            encrypted[index] ^= key_byte

        decrypted = decrypt_weixin_encrypted_bytes(bytes(encrypted), keystream)

        self.assertEqual(decrypted[:32], bytes(plain[:32]))
        self.assertEqual(decrypted[KEYSTREAM_SIZE:], bytes(plain[KEYSTREAM_SIZE:]))
        assert_mp4_header(decrypted)

    def test_assert_mp4_header_rejects_wrong_key_result(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "ftyp"):
            assert_mp4_header(b"not-an-mp4")

    def test_decode_key_fingerprint_does_not_return_raw_key(self) -> None:
        fingerprint = decode_key_fingerprint("0123456789abcdef")

        self.assertEqual(fingerprint["decode_key_length"], 16)
        self.assertIn("decode_key_sha256_12", fingerprint)
        self.assertNotIn("0123456789abcdef", str(fingerprint))

    def test_numeric_key_decryption_roundtrip_restores_mp4_header(self) -> None:
        plain = b"\x00\x00\x00\x20ftypisom" + b"a" * 160
        encrypted = decrypt_weixin_numeric_key_bytes(plain, key=123456789, enc_limit=96)

        decrypted = decrypt_weixin_numeric_key_bytes(encrypted, key=123456789, enc_limit=96)

        self.assertNotEqual(encrypted[:96], plain[:96])
        self.assertEqual(decrypted, plain)
        assert_mp4_header(decrypted)

    def test_prefix_stream_decryption_restores_file_without_whole_file_transform(self) -> None:
        plain = b"\x00\x00\x00\x20ftypisom" + b"a" * (1024 * 1024)
        encrypted_bytes = decrypt_weixin_numeric_key_bytes(
            plain, key=123456789, enc_limit=96
        )
        with tempfile.TemporaryDirectory() as tmp:
            encrypted = Path(tmp) / "encrypted.mp4"
            decrypted = Path(tmp) / "decrypted.mp4"
            encrypted.write_bytes(encrypted_bytes)

            result = decode_module._decrypt_prefix_file(
                encrypted,
                decrypted,
                prefix_bytes=96,
                transform=lambda payload: decrypt_weixin_numeric_key_bytes(
                    payload, key=123456789, enc_limit=96
                ),
            )

            self.assertEqual(decrypted.read_bytes(), plain)
            self.assertEqual(result["mode"], "prefix_stream_copy")
            self.assertEqual(result["prefix_bytes"], 96)

    def test_numeric_key_fingerprint_does_not_return_raw_key(self) -> None:
        fingerprint = numeric_key_fingerprint(123456789)

        self.assertEqual(fingerprint["numeric_key_digits"], 9)
        self.assertIn("numeric_key_sha256_12", fingerprint)
        self.assertNotIn("123456789", str(fingerprint))

    def test_generate_keystream_via_node_passes_key_by_temp_file_not_command_arg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wasm_dir = root / "wasm"
            wasm_dir.mkdir()
            (wasm_dir / "wasm_video_decode.js").write_text("// synthetic", encoding="utf-8")
            (wasm_dir / "wasm_video_decode.wasm").write_bytes(b"wasm")
            commands: list[list[str]] = []

            def fake_runner(command, **_kwargs):
                commands.append(command)
                out_path = Path(command[command.index("--out") + 1])
                out_path.write_bytes(bytes([7]) * KEYSTREAM_SIZE)
                return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

            data = generate_keystream_via_node(
                "0123456789abcdef",
                wasm_dir=wasm_dir,
                work_dir=root / "work",
                runner=fake_runner,
            )

        self.assertEqual(len(data), KEYSTREAM_SIZE)
        flattened = " ".join(commands[0])
        self.assertIn("--decode-key-file", flattened)
        self.assertNotIn("0123456789abcdef", flattened)

    def test_range_download_continues_after_short_read_until_expected_size(self) -> None:
        payload = b"0123456789"
        calls: list[tuple[int, int]] = []
        original = decode_module._read_http_range

        def fake_read_range(_url: str, start: int, end: int, timeout: int = 60):
            calls.append((start, end))
            if start == 0:
                return payload[:4], 206, len(payload)
            return payload[start : end + 1], 206, len(payload)

        try:
            decode_module._read_http_range = fake_read_range
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "video.mp4"
                decode_module._download_file_by_ranges(
                    "https://example.test/video.mp4",
                    output,
                    expected_size=len(payload),
                    chunk_size=len(payload),
                    max_retries=3,
                )
                self.assertEqual(output.read_bytes(), payload)
        finally:
            decode_module._read_http_range = original

        self.assertEqual(calls, [(0, 9), (4, 9)])


if __name__ == "__main__":
    unittest.main()
