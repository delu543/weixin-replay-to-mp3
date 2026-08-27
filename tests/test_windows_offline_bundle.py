from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import build_windows_offline_bundle
from tools import install_offline_wheels


ROOT = Path(__file__).resolve().parents[1]


class WindowsOfflineBundleTests(unittest.TestCase):
    def test_runtime_source_zip_is_cross_platform_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "nested" / "payload.txt").write_text("fixed\n", encoding="ascii")
            (root / "VERSION").write_text("fixed\n", encoding="ascii")
            (root / "main.py").write_text("fixed\n", encoding="ascii")
            first = build_windows_offline_bundle.zip_tree(root)
            second = build_windows_offline_bundle.zip_tree(root)
            self.assertEqual(first, second)
            with zipfile.ZipFile(io.BytesIO(first)) as archive:
                self.assertEqual(
                    archive.namelist(), ["VERSION", "main.py", "nested/payload.txt"]
                )
                self.assertTrue(
                    all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
                )

    def test_generated_runtime_files_have_fixed_newline_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_windows_offline_bundle.copy_runtime_source(root, "test-version")
            self.assertEqual(
                (root / "runtime" / build_windows_offline_bundle.MARKER).read_bytes(),
                b"test-version\n",
            )
            self.assertEqual(
                (root / "skill" / build_windows_offline_bundle.MARKER).read_bytes(),
                b"test-version\n",
            )
            self.assertEqual(
                (root / "runtime" / "weixin-replay-to-mp3.cmd").read_bytes(),
                b'@echo off\r\n"%~dp0work\\venv\\Scripts\\python.exe" '
                b'"%~dp0weixin_replay_cli.py" %*\r\n',
            )

    def test_fixed_portable_lock_contains_every_runtime_dependency(self) -> None:
        lock = json.loads(
            (ROOT / "scripts" / "windows-portable.lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lock["architecture"], "x64")
        self.assertEqual(lock["python"]["version"], "3.13.15")
        self.assertEqual(len(lock["python"]["sha256"]), 64)
        distributions = {item["distribution"] for item in lock["wheels"]}
        self.assertEqual(distributions, {"imageio-ffmpeg", "yt-dlp", "yt-dlp-ejs", "deno"})
        self.assertTrue(all(len(item["sha256"]) == 64 for item in lock["wheels"]))

    def test_offline_installer_has_no_network_or_package_manager_dependency(self) -> None:
        template = (ROOT / "scripts" / "install-windows-offline.template.ps1").read_text(
            encoding="ascii"
        )
        self.assertIn('install_mode = "offline_portable"', template)
        self.assertIn("Read-VerifiedManifest", template)
        self.assertIn("Invoke-Preflight", template)
        self.assertIn("'(^|[\\\\/])\\.\\.([\\\\/]|$)'", template)
        self.assertIn('".`r`n..\\Lib\\site-packages`r`n..\\..\\..`r`n"', template)
        for forbidden in (
            "Invoke-WebRequest",
            "Start-BitsTransfer",
            "winget.exe",
            "pip install",
            "git clone",
            "Set-ExecutionPolicy",
        ):
            self.assertNotIn(forbidden, template)

    def test_wheel_expander_creates_the_portable_media_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheel = root / "fixed.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("imageio_ffmpeg/binaries/ffmpeg-test.exe", b"ffmpeg")
                archive.writestr("yt_dlp/__main__.py", b"print('test')\n")
                archive.writestr("yt_dlp_ejs/__init__.py", b"")
                archive.writestr("deno-2.9.5.data/scripts/deno.exe", b"deno")
            site_packages = root / "site-packages"
            scripts = root / "Scripts"
            result = install_offline_wheels.extract_wheels(
                [wheel], site_packages=site_packages, scripts=scripts
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue((scripts / "deno.exe").is_file())
            self.assertTrue((site_packages / "yt_dlp" / "__main__.py").is_file())

    def test_wheel_expander_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheel = root / "unsafe.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("../outside.txt", b"unsafe")
            with self.assertRaisesRegex(RuntimeError, "unsafe wheel path"):
                install_offline_wheels.extract_wheels(
                    [wheel], site_packages=root / "site-packages", scripts=root / "Scripts"
                )


if __name__ == "__main__":
    unittest.main()
