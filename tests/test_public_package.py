from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import weixin_replay_cli as cli
from scripts import bootstrap, release_check


class PublicPackageTests(unittest.TestCase):
    def test_canonical_link_accepts_only_exact_weixin_short_link(self) -> None:
        link, short_id = cli.canonical_link(
            "https://weixin.qq.com/sph/Abc_123-xy?tracking=removed#fragment"
        )
        self.assertEqual(short_id, "Abc_123-xy")
        self.assertEqual(link, "https://weixin.qq.com/sph/Abc_123-xy")

    def test_canonical_link_rejects_wrong_host_and_path(self) -> None:
        rejected = (
            "http://weixin.qq.com/sph/Abc123",
            "https://example.com/sph/Abc123",
            "https://weixin.qq.com/not-sph/Abc123",
            "https://weixin.qq.com/sph/a/b",
        )
        for value in rejected:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cli.canonical_link(value)

    def test_default_output_is_stable_per_short_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cli, "DEFAULT_OUTPUT_ROOT", Path(tmp)):
                first = cli.output_path("Abc123")
                second = cli.output_path("Abc123")
        self.assertEqual(first, second)
        self.assertEqual(first.name, "weixin_Abc123.mp3")

    def test_run_state_is_target_and_mode_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cli, "ROOT", Path(tmp)):
                automatic = cli.run_dir("Abc123", "auto")
                manual = cli.run_dir("Abc123", "manual")
                self.assertNotEqual(automatic, manual)
                self.assertTrue(automatic.is_dir())
                self.assertTrue(manual.is_dir())

    def test_bootstrap_refuses_unmanaged_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "occupied"
            target.mkdir()
            (target / "foreign.txt").write_text("foreign", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                bootstrap.ensure_owned_or_new(target)

    def test_bootstrap_copies_only_release_runtime_and_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime = base / "runtime"
            skill = base / "skill"
            with (
                mock.patch.object(bootstrap, "APP_ROOT", base),
                mock.patch.object(bootstrap, "RUNTIME_ROOT", runtime),
                mock.patch.object(bootstrap, "SKILL_ROOT", skill),
            ):
                bootstrap.copy_runtime()
                bootstrap.copy_skill()
                self.assertTrue((runtime / "weixin_replay_cli.py").is_file())
                self.assertTrue((runtime / "replay_mp3_studio" / "extractors.py").is_file())
                self.assertTrue((runtime / bootstrap.MARKER).is_file())
                self.assertTrue((skill / "SKILL.md").is_file())
                self.assertFalse((runtime / ".codex").exists())
                self.assertFalse((runtime / "tests").exists())

    def test_requirements_pin_both_macos_wheel_hashes(self) -> None:
        text = (bootstrap.SOURCE_ROOT / "requirements-macos.txt").read_text(encoding="utf-8")
        self.assertIn("imageio-ffmpeg==0.6.0", text)
        self.assertEqual(text.count("--hash=sha256:"), 2)

    def test_release_scan_has_no_private_or_generated_files(self) -> None:
        result = release_check.scan()
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
