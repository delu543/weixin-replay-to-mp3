---
name: weixin-replay-to-mp3
description: Convert one user-authorized Weixin Channels short link into a verified MP3 on macOS or Windows, using guarded macOS automation or explicit Windows manual playback when needed.
---

# Weixin Replay To MP3

Use this Skill when the user supplies an authorized
`https://weixin.qq.com/sph/...` link and asks for MP3 extraction.

## Runtime discovery

Run `python scripts/bootstrap.py doctor` when readiness is unclear and use its
`platform` field. Installed runtimes:

- macOS: `~/Library/Application Support/WeixinReplayToMP3/runtime`
- Windows: `%LOCALAPPDATA%\WeixinReplayToMP3\runtime`

Do not install or run merely because the repository was opened.

## Safety boundary

- The supplied link is the complete authorization scope.
- macOS sending is allowed only to the conversation proven to be exactly
  `文件传输助手` by the implemented gates.
- Windows has no verified automatic WeChat UI adapter in this release. Never guess
  coordinates, click, paste, or send to a chat on Windows.
- Never read chat/contact databases, browser cookies, account tokens, or unrelated
  WeChat history.
- Never install certificates, change the system proxy, hook/patch WeChat, or disable
  protected-window behavior.
- Do not print signed media URLs, decode keys, cookies, or private runtime files.
- Any unknown chat, stale link, absent playback proof/confirmation, or wrong target
  must stop before an unbound runtime scan.

## macOS route

Run:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

A white screenshot means pixels are unavailable. Use the implemented AX,
WindowServer, process, exact-message, and playback-assertion gates. Do not keep retrying
blind screenshots or disable WeChat protection.

## Windows route

First run the normal command so target-bound local/provider sources and an existing
verified output can complete without any manual work:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

If it completes, finish normally. If and only if it reports
`Manual playback is required`, tell the user these exact steps:

1. Open official Windows WeChat.
2. Open the chat whose title is exactly `文件传输助手`.
3. Send the exact supplied link, open the newest matching message, and start the video.
4. Stop unrelated WeChat videos and reply only after this exact link is playing.

Pause for the user's explicit confirmation. Do not treat “WeChat is open” as playback
confirmation. After confirmation, run:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "<USER_SUPPLIED_WEIXIN_LINK>" --manual-playback
```

If the safe runtime layout differs, inspect only known playback/runtime locations. A
semicolon-separated `WEIXIN_REPLAY_RUNTIME_ROOTS` override is allowed only for those
folders, never for chat/contact/message databases.

If no compatible runtime source exists, offer a user-authorized local file:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  convert-file "C:\path\to\authorized-video.mp4"
```

Audio-device recording is the last resort. Run `audio-devices`, let the user choose an
existing DirectShow input, require exact playback confirmation, and never install or
enable an audio driver automatically.

## Output, resume, and duration

The default output is stable for the short ID inside the current local namespace:

```text
<Downloads>/WeixinReplayMP3/<opaque-namespace>/weixin_<short-id>.mp3
```

A valid output is fully decoded and reused. An invalid output is preserved and never
overwritten. Target-bound state resumes a frozen increment without repeating finished
work. Never search, copy, or reuse another namespace's state.

Do not assume every replay is one hour. Correctness comes from exact-link binding,
fresh changes, same-context URL/key proof, decrypted MP4 header, declared source bytes,
largest verified candidate ordering, and final full decode. Add
`--min-duration <SECONDS>` only when the user gives a reliable floor.

If the user explicitly asks for a separate local profile, add
`--profile <validated-name>` and keep it for every step. A profile separates files, not
the shared WeChat login; different people should use different OS accounts.

## Finish gate

Before reporting completion, require final JSON status `completed` (or an explicit
verified reuse result), confirm the MP3 exists, and report exact path, bytes, and
duration. A player window, candidate, download start, or partial MP3 is not completion.

State plainly that Windows WeChat runtime capture still needs real-machine validation
if the task concerns platform support rather than a completed user conversion.
