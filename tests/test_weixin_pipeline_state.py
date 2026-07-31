from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from replay_mp3_studio.weixin_pipeline_state import (
    load_or_create_pipeline_state,
    mark_pipeline_phase_complete,
    mark_pipeline_phase_failure,
    mark_existing_pipeline_phase,
    pipeline_phase_completed,
    pipeline_resume_action,
)


class WeixinPipelineStateTests(unittest.TestCase):
    URL = "https://weixin.qq.com/sph/A1TN6kx8js"

    def test_state_is_target_bound_and_does_not_store_full_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, state = load_or_create_pipeline_state(
                Path(tmp),
                url=self.URL,
                mode="open_then_watch",
            )
            encoded = path.read_text(encoding="utf-8")

        self.assertEqual(state["target_short_uri"], "A1TN6kx8js")
        self.assertNotIn(self.URL, encoded)
        self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())

    def test_resume_actions_distinguish_message_retry_and_frozen_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, state = load_or_create_pipeline_state(
                Path(tmp),
                url=self.URL,
                mode="open_then_watch",
            )
            mark_pipeline_phase_complete(path, state, "target_opened")
            self.assertEqual(pipeline_resume_action(state), "reuse_verified_message")
            mark_pipeline_phase_complete(path, state, "causal_capture_complete")
            self.assertEqual(pipeline_resume_action(state), "resume_frozen_conversion")
            mark_pipeline_phase_complete(path, state, "source_converted")
            mark_pipeline_phase_complete(path, state, "output_verified")
            self.assertEqual(pipeline_resume_action(state), "reuse_verified_output")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["current_phase"], "complete")

    def test_state_rejects_a_different_target_or_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            load_or_create_pipeline_state(artifacts, url=self.URL, mode="open_then_watch")
            with self.assertRaisesRegex(RuntimeError, "different short link"):
                load_or_create_pipeline_state(
                    artifacts,
                    url="https://weixin.qq.com/sph/AWbb8Gxj9X",
                    mode="open_then_watch",
                )
            with self.assertRaisesRegex(RuntimeError, "different execution mode"):
                load_or_create_pipeline_state(artifacts, url=self.URL, mode="manual_playback")

    def test_phase_completion_is_idempotent_and_failure_budget_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, state = load_or_create_pipeline_state(
                Path(tmp),
                url=self.URL,
                mode="open_then_watch",
            )
            mark_pipeline_phase_complete(path, state, "source_vault_checked")
            mark_pipeline_phase_complete(path, state, "source_vault_checked")
            self.assertTrue(pipeline_phase_completed(state, "source_vault_checked"))
            self.assertEqual(state["completed_phases"].count("source_vault_checked"), 1)
            self.assertEqual(
                mark_pipeline_phase_failure(path, state, "target_opened", error_code="network_unavailable"),
                1,
            )
            self.assertEqual(
                mark_pipeline_phase_failure(path, state, "target_opened", error_code="network_unavailable"),
                2,
            )
            reloaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(reloaded["status"], "blocked")
        self.assertEqual(reloaded["blocked_reason"], "network_unavailable")

    def test_existing_phase_helper_never_creates_or_retargets_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            self.assertFalse(
                mark_existing_pipeline_phase(
                    artifacts,
                    target_short_uri="A1TN6kx8js",
                    phase="causal_capture_complete",
                )
            )
            path, state = load_or_create_pipeline_state(
                artifacts,
                url=self.URL,
                mode="open_then_watch",
            )
            self.assertFalse(
                mark_existing_pipeline_phase(
                    artifacts,
                    target_short_uri="different",
                    phase="causal_capture_complete",
                )
            )
            self.assertTrue(
                mark_existing_pipeline_phase(
                    artifacts,
                    target_short_uri="A1TN6kx8js",
                    phase="causal_capture_complete",
                )
            )
            reloaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("causal_capture_complete", reloaded["completed_phases"])


if __name__ == "__main__":
    unittest.main()
