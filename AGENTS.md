# Codex project instructions

This repository is the independent macOS project `weixin-replay-to-mp3`.

## First relevant request

When the user asks to install/use this project or supplies an authorized
`https://weixin.qq.com/sph/...` link for MP3 extraction:

1. Run `python3 scripts/bootstrap.py doctor`.
2. If the state is `needs_install`, explain that installation is user-local and
   downloads only pinned `imageio-ffmpeg` macOS wheels into a private venv. Then,
   because the user asked to install/use the project, run
   `python3 scripts/bootstrap.py install`.
3. Do not execute or install anything merely because the repository was opened.
4. After readiness passes, follow the repository's `weixin-replay-to-mp3` Skill.

## One-link workflow

The supplied short link is the complete authorization scope. Invoke:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

If working directly in this checked-out repository before installation, the equivalent
command is `python3 weixin_replay_cli.py run "<link>"`, but only when `preflight`
already reports ready.

## Non-negotiable safety gates

- Automatic operation supports macOS with official desktop WeChat only. Do not claim
  Windows/Linux or Codex cloud support for local WeChat automation.
- Send only the exact supplied link and only after the conversation is proven to be
  exactly `文件传输助手` by the implemented name, header, icon, and latest-message
  gates. Any ambiguity stops before input or Return.
- Never read chat/contact databases, cookies, tokens, unrelated history, or account
  secrets. Never install a certificate, change the proxy, hook/patch WeChat, or disable
  window protection.
- A protected/white screenshot is not proof that WeChat exited. Use process,
  `WeChatAppEx`, AX, WindowServer, exact-message, and playback assertion evidence.
- Do not run broad stale-cache scans when the exact target was not opened and playback
  was not independently proven.
- Keep `work/`, `.codex/`, outputs, media, reports, screenshots, signed URLs, keys, and
  account data local and untracked.
- Preserve an existing MP3 and target-bound run state. Never overwrite invalid evidence
  or delete a prior result during a retry.

## Completion

Completion requires the final command result, an existing MP3, and a full ffmpeg decode.
Report the exact path, byte count, duration, selected source byte count when available,
and whether the run reused prior verified state. Do not call a player window, candidate,
download start, or partial file successful output.

Before any public push, run `python3 scripts/release_check.py` and keep the original
development workspaces untouched.
