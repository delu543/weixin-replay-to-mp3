from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import weixin_replay_cli as cli
from replay_mp3_studio import config, fast_pipeline, user_storage
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
            with mock.patch.dict(
                os.environ,
                {user_storage.OUTPUT_ROOT_ENV: str(Path(tmp) / "outputs")},
                clear=False,
            ):
                first = cli.output_path("Abc123", profile="primary")
                second = cli.output_path("Abc123", profile="primary")
                other = cli.output_path("Abc123", profile="secondary")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(first.name, "weixin_Abc123.mp3")
        self.assertNotIn("primary", str(first))

    def test_run_state_is_target_and_mode_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_base = Path(tmp) / "data"
            with mock.patch.dict(
                os.environ,
                {user_storage.DATA_ROOT_ENV: str(data_base)},
                clear=False,
            ):
                automatic = cli.run_dir("Abc123", "auto", "primary")
                manual = cli.run_dir("Abc123", "manual", "primary")
                other = cli.run_dir("Abc123", "auto", "secondary")
                self.assertNotEqual(automatic, manual)
                self.assertNotEqual(automatic, other)
                self.assertTrue(automatic.is_relative_to(data_base.resolve()))
                self.assertFalse(automatic.is_relative_to(cli.ROOT))
                self.assertTrue(automatic.is_dir())
                self.assertTrue(manual.is_dir())

    def test_storage_namespace_is_stable_and_separates_local_principals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_a = Path(tmp) / "home-a"
            home_b = Path(tmp) / "home-b"
            first = user_storage.storage_namespace("primary", home=home_a, uid=501)
            again = user_storage.storage_namespace("primary", home=home_a, uid=501)
            other_profile = user_storage.storage_namespace("secondary", home=home_a, uid=501)
            other_home = user_storage.storage_namespace("primary", home=home_b, uid=501)
            other_uid = user_storage.storage_namespace("primary", home=home_a, uid=502)
        self.assertEqual(first, again)
        self.assertEqual(len({first, other_profile, other_home, other_uid}), 4)

    def test_profile_rejects_path_traversal(self) -> None:
        for value in ("../other", "/tmp/shared", "two people", ""):
            if value == "":
                self.assertEqual(user_storage.profile_name(value), "default")
                continue
            with self.subTest(value=value), self.assertRaises(ValueError):
                user_storage.profile_name(value)

    def test_profile_layout_uses_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                user_storage.DATA_ROOT_ENV: str(Path(tmp) / "data"),
                user_storage.OUTPUT_ROOT_ENV: str(Path(tmp) / "output"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                layout = user_storage.ensure_profile_layout("primary")
            data_mode = stat.S_IMODE(Path(layout["data_root"]).stat().st_mode)
            output_mode = stat.S_IMODE(Path(layout["output_root"]).stat().st_mode)
        self.assertEqual(data_mode, 0o700)
        self.assertEqual(output_mode, 0o700)

    def test_explicit_output_does_not_change_existing_parent_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "user-chosen"
            parent.mkdir(mode=0o755)
            parent.chmod(0o755)
            cli.prepare_output_parent(parent / "result.mp3", managed_default=False)
            mode = stat.S_IMODE(parent.stat().st_mode)
        self.assertEqual(mode, 0o755)

    def test_active_runtime_work_roots_are_outside_source_checkout(self) -> None:
        self.assertTrue(config.WORK_ROOT.is_relative_to(config.USER_DATA_ROOT))
        self.assertTrue(config.LIBRARY_ROOT.is_relative_to(config.USER_DATA_ROOT))
        self.assertFalse(config.WORK_ROOT.is_relative_to(config.PROJECT_ROOT))
        self.assertTrue(fast_pipeline.DIRECT_LINK_PROBE_REPORT.is_relative_to(config.WORK_ROOT))
        for root in fast_pipeline.DEFAULT_SOURCE_ARTIFACT_ROOTS:
            self.assertTrue(root.is_relative_to(config.WORK_ROOT))

    def test_activated_profile_is_inherited_by_child_processes(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            previous = os.environ.pop(user_storage.PROFILE_ENV, None)
            try:
                resolved = user_storage.activate_profile("secondary")
                self.assertEqual(resolved, "secondary")
                self.assertEqual(os.environ[user_storage.PROFILE_ENV], "secondary")
            finally:
                if previous is None:
                    os.environ.pop(user_storage.PROFILE_ENV, None)
                else:
                    os.environ[user_storage.PROFILE_ENV] = previous

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
