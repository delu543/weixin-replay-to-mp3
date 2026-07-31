#!/usr/bin/env python3
"""Codex-facing CLI for one authorized Weixin Channels replay link."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from replay_mp3_studio.user_storage import (
    activate_profile,
    ensure_private_dir,
    ensure_profile_layout,
    private_umask,
    storage_namespace,
    user_data_root,
    user_output_root,
)


ROOT = Path(__file__).resolve().parent
SHORT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{5,80}$")


def canonical_link(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "weixin.qq.com":
        raise ValueError("Only https://weixin.qq.com/sph/<id> links are accepted.")
    match = re.fullmatch(r"/sph/([^/]+)", parsed.path.rstrip("/"))
    if not match or not SHORT_ID_RE.fullmatch(match.group(1)):
        raise ValueError("Invalid Weixin Channels short link.")
    short_id = match.group(1)
    return urlunsplit(("https", "weixin.qq.com", f"/sph/{short_id}", "", "")), short_id


def output_path(short_id: str, explicit: str = "", profile: str = "") -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (user_output_root(profile) / f"weixin_{short_id}.mp3").resolve()


def run_dir(short_id: str, mode: str, profile: str = "") -> Path:
    suffix = "" if mode == "auto" else f"-{mode}"
    return ensure_private_dir(
        user_data_root(profile) / "runs" / "weixin-link" / f"{short_id}{suffix}"
    )


def prepare_output_parent(output: Path, *, managed_default: bool) -> Path:
    if managed_default:
        return ensure_private_dir(output.parent)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output.parent


def preflight_payload(profile: str = "") -> dict[str, Any]:
    resolved_profile = activate_profile(profile)
    wechat_running = (
        subprocess.run(
            ["pgrep", "-x", "WeChat"], capture_output=True, text=True, check=False
        ).returncode
        == 0
        if platform.system() == "Darwin"
        else False
    )
    wechat_paths = (
        Path("/Applications/WeChat.app"),
        Path("/Applications/微信.app"),
        Path.home() / "Applications/WeChat.app",
        Path.home() / "Applications/微信.app",
    )
    checks: dict[str, Any] = {
        "macos": platform.system() == "Darwin",
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "python_supported": sys.version_info >= (3, 9),
        "swift": bool(shutil.which("swift")),
        "node_optional": bool(shutil.which("node")),
        "wechat_installed": wechat_running or any(path.exists() for path in wechat_paths),
        "wechat_running": wechat_running,
    }
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from replay_mp3_studio.utils import find_ffmpeg

        checks["ffmpeg"] = find_ffmpeg()
        checks["ffmpeg_ready"] = True
    except Exception:
        checks["ffmpeg"] = ""
        checks["ffmpeg_ready"] = False
    checks["ready"] = all(
        checks[key]
        for key in ("macos", "python_supported", "swift", "wechat_installed", "ffmpeg_ready")
    )
    checks["accessibility"] = "verified_on_first_guarded_ui_use"
    checks["data_isolation"] = {
        "schema": "v1",
        "namespace": storage_namespace(resolved_profile),
        "data_root": str(user_data_root(resolved_profile)),
        "output_root": str(user_output_root(resolved_profile)),
        "boundary": "local_macos_account_plus_optional_profile",
    }
    return checks


def cmd_preflight(args: argparse.Namespace) -> int:
    payload = preflight_payload(args.profile)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 2


def cmd_verify(args: argparse.Namespace) -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from replay_mp3_studio.utils import verify_mp3

    result = verify_mp3(
        Path(args.path).expanduser().resolve(), print, min_duration_seconds=args.min_duration
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    with private_umask():
        return _cmd_run_private(args)


def _cmd_run_private(args: argparse.Namespace) -> int:
    link, short_id = canonical_link(args.url)
    mode = "manual" if args.manual_playback else "auto"
    resolved_profile = activate_profile(args.profile)
    isolation = ensure_profile_layout(resolved_profile)
    output = output_path(short_id, args.output, resolved_profile)
    artifacts = run_dir(short_id, mode, resolved_profile)
    prepare_output_parent(output, managed_default=not bool(args.output))

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from replay_mp3_studio.extractors import run_weixin_link
    from replay_mp3_studio.utils import verify_mp3

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    run_weixin_link(
        link,
        output,
        artifacts,
        lambda message: print(message, flush=True),
        duration=args.capture_window,
        manual_playback=args.manual_playback,
        min_duration=args.min_duration,
    )
    verification = verify_mp3(
        output, lambda message: print(message, flush=True), min_duration_seconds=args.min_duration
    )
    result = {
        "status": "completed",
        "target_short_id": short_id,
        "target_sha256_12": hashlib.sha256(link.encode("utf-8")).hexdigest()[:12],
        "storage_namespace": isolation["namespace"],
        "output": str(output),
        "output_bytes": int(verification.get("bytes") or 0),
        "duration_seconds": verification.get("duration_seconds"),
        "artifacts": str(artifacts),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    result_path = artifacts / "public-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        result_path.chmod(0o600)
    except OSError:
        pass
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    check = commands.add_parser("preflight", help="Read-only prerequisite check")
    check.add_argument("--profile", default="")
    check.set_defaults(func=cmd_preflight)
    run = commands.add_parser("run", help="Convert one authorized Weixin link")
    run.add_argument("url")
    run.add_argument("--output", default="")
    run.add_argument("--min-duration", type=float, default=1.0)
    run.add_argument("--capture-window", type=int, default=300)
    run.add_argument("--manual-playback", action="store_true")
    run.add_argument("--profile", default="")
    run.set_defaults(func=cmd_run)
    verify = commands.add_parser("verify", help="Full-decode an MP3")
    verify.add_argument("path")
    verify.add_argument("--min-duration", type=float, default=0.0)
    verify.set_defaults(func=cmd_verify)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
