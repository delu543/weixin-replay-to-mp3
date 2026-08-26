# Codex project instructions

This repository is the independent macOS and Windows project
`weixin-replay-to-mp3`. Keep the shared download, resume, conversion, verification,
and storage-isolation pipeline platform-neutral. Do not duplicate or rewrite it for
one operating system.

## First relevant request

When the user asks to install/use this project or supplies an authorized
`https://weixin.qq.com/sph/...` link for MP3 extraction:

1. Run `python scripts/bootstrap.py doctor` (`python3` is also valid on macOS).
2. Read `platform`, `state`, and `preflight` from the JSON result.
3. If the state is `needs_install`, explain that installation is user-local and
   downloads only the pinned `imageio-ffmpeg` wheel for the detected operating
   system into a private venv. Because the user asked to install/use the project,
   run `python scripts/bootstrap.py install`.
4. Do not execute or install anything merely because the repository was opened.
5. After readiness passes, follow the repository's `weixin-replay-to-mp3` Skill.

## Platform routing

### macOS

Use the guarded automatic File Transfer Assistant workflow:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

### Windows

Use the same link, source, download, resume, conversion, and verification pipeline.
The installed PowerShell command is:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

This first tries target-bound local/provider routes. The public release does not claim
a verified Windows WeChat UI adapter and must never send or click blindly. If the CLI
reports `Manual playback is required`, tell the user exactly:

1. Open official desktop WeChat.
2. Open the conversation whose title is exactly `文件传输助手`.
3. Send the exact supplied link there, open the newest matching message, and start the
   video. Stop unrelated WeChat video playback.
4. Reply to Codex only after that exact video is visibly playing.

Wait for that explicit confirmation. Then, and only then, run:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "<USER_SUPPLIED_WEIXIN_LINK>" --manual-playback
```

Do not reinterpret `--manual-playback` as permission to operate another chat. It only
authorizes the bounded recent-runtime scan after the user has confirmed the exact
playback. If the Windows WeChat runtime is stored outside the known safe locations,
inspect only playback/runtime directories and set `WEIXIN_REPLAY_RUNTIME_ROOTS` to a
semicolon-separated list. Never point it at chat/contact databases.

If runtime capture is unavailable, offer conversion of a user-authorized local media
file with `convert-file`. Audio-device recording is an explicit last resort; list
devices first, require the user to choose one and confirm playback, and never install
or enable a driver automatically.

Linux and remote/cloud environments are not supported for local WeChat operation.

## Storage

Default data and output roots are outside the repository and bound to an opaque
namespace for the current operating-system account. If the user explicitly selects a
local `--profile`, keep using that same profile for every resume/verify step.

- macOS runtime/data: `~/Library/Application Support/WeixinReplayToMP3/`
- Windows runtime/data: `%LOCALAPPDATA%\WeixinReplayToMP3\`
- MP3 output on both systems: the current account's
  `Downloads/WeixinReplayMP3/<opaque-namespace>/`

## Non-negotiable safety gates

- On macOS, send only the exact supplied link and only after the conversation is
  proven to be exactly `文件传输助手` by the implemented name, header, icon, and
  latest-message gates. Any ambiguity stops before input or Return.
- On Windows, this release does not send messages or click WeChat automatically.
  Require the explicit manual confirmation above before any recent-runtime scan.
- Never read chat/contact databases, cookies, tokens, unrelated history, or account
  secrets. Never install a certificate, change the proxy, hook/patch WeChat, or disable
  window protection.
- A protected/white screenshot is not proof that WeChat exited. macOS uses process,
  `WeChatAppEx`, AX, WindowServer, exact-message, and playback assertion evidence.
- Do not run broad stale-cache scans when the exact target was not opened and playback
  was not independently proven.
- Keep `work/`, `.codex/`, outputs, media, reports, screenshots, signed URLs, keys, and
  account data local and untracked.
- Never read or reuse another storage namespace. A shared OS login is not a
  separate-user security boundary; recommend separate OS accounts when different
  humans share a computer.
- Preserve an existing MP3 and target-bound run state. Never overwrite invalid evidence
  or delete a prior result during a retry.

## Completion

Completion requires the final command result, an existing MP3, and a full ffmpeg
decode. Report the exact path, byte count, duration, selected source byte count when
available, and whether the run reused prior verified state. Do not call a player
window, candidate, download start, or partial file successful output.

Before any public push, run `python scripts/release_check.py` on the available local
platform and keep the original development workspaces untouched. Windows CI verifies
the portable Python/installer surface; real Windows WeChat playback/runtime behavior
must be described as pending until it has been exercised on a Windows machine.
