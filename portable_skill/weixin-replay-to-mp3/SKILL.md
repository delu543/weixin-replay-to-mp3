---
name: weixin-replay-to-mp3
description: Convert user-authorized Weixin Channels, Xiaohongshu, YouTube, X/Twitter, direct-media, Songy, and other supported webpage links into verified MP3 files on macOS or Windows.
---

# Replay Links To MP3

Use this Skill when the user supplies an authorized replay, video, live, course, or
direct-media link and asks for MP3 output. This is media extraction, not text
transcription.

## Runtime discovery

On macOS, run `python3 scripts/bootstrap.py doctor` when readiness is unclear. On
Windows, never require Python before entering setup: run the repository's
`install-windows.ps1 -CheckOnly`, or run `install-windows.ps1` directly when the user
has asked to install/use the product. Installed runtimes:

- macOS: `~/Library/Application Support/WeixinReplayToMP3/runtime`
- Windows: `%LOCALAPPDATA%\WeixinReplayToMP3\runtime`

Do not install or run merely because the repository was opened. Full multi-platform
web-link support requires Python 3.10 or newer. The pinned user-local runtime includes
FFmpeg, yt-dlp, local EJS assets, and Deno for both macOS and Windows.

If Windows lacks Python, the installer uses `winget` to install user-local Python 3.12
and continues. If Git clone or its HTTPS remote helper is missing, download the current
`install-windows.ps1` from the repository's raw `main`; it obtains the GitHub source
ZIP without Git. Do not stop after merely listing missing Python, FFmpeg, or Git, and
do not describe native Windows as `unsupported_platform`. If the agent is running in
WSL/Linux, switch the Codex app's agent environment to Windows native for this tool.

## Safety boundary

- The supplied link is the complete authorization scope. Attempt only content the user
  is authorized to access and convert.
- macOS sending is allowed only to the conversation proven to be exactly
  `文件传输助手` by the implemented gates, and only for a Weixin Channels link.
- Windows has no verified automatic WeChat UI adapter in this release. Never guess
  coordinates, click, paste, or send to a chat on Windows.
- Never read chat/contact databases, browser cookies, account tokens, or unrelated
  WeChat history.
- Never install certificates, change the system proxy, hook/patch WeChat, or disable
  protected-window behavior.
- Do not print signed media URLs, decode keys, cookies, or private runtime files.
- Any unknown chat, stale link, absent playback proof/confirmation, or wrong target
  must stop before an unbound runtime scan.
- YouTube, X/Twitter, and generic webpage routes may try public extraction but never
  import browser cookies automatically. Login-, age-, region-, subscription-, or DRM-
  restricted media must fail clearly or use a user-authorized local file/artifact.

## Link routing

Use the same installed command for every supported URL. It classifies the URL before
choosing a route:

- Xiaohongshu live replay: resolve the share link when needed, read the replay metadata,
  convert the selected media, and fully decode the MP3.
- YouTube: use the pinned yt-dlp + EJS + Deno route without browser cookies.
- X/Twitter: use the same pinned public webpage extractor without browser cookies.
- Direct MP3/M4A/MP4/HLS and other supported public webpages: try the shared media or
  generic extractor.
- Songy: try the bounded direct provider route; otherwise request a user-authorized
  artifact or local media file.
- Weixin Channels: use the guarded platform-specific route below.

macOS:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_LINK>"
```

Windows PowerShell:

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "<USER_SUPPLIED_LINK>"
```

Non-Weixin links must not open, inspect, or operate WeChat on either system.

## Weixin route on macOS

Run:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

A white screenshot means pixels are unavailable. Use the implemented AX,
WindowServer, process, exact-message, and playback-assertion gates. Do not keep retrying
blind screenshots or disable WeChat protection.

## Weixin route on Windows

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
4. Stop unrelated WeChat videos and reply
   `已在文件传输助手打开这个链接，并开始播放` only after this exact link is playing.

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

The default output is stable for the provider target ID inside the current local
namespace, for example:

```text
<Downloads>/WeixinReplayMP3/<opaque-namespace>/weixin_<short-id>.mp3
<Downloads>/WeixinReplayMP3/<opaque-namespace>/youtube_<video-id>.mp3
<Downloads>/WeixinReplayMP3/<opaque-namespace>/x_<status-id>.mp3
<Downloads>/WeixinReplayMP3/<opaque-namespace>/xiaohongshu_<replay-id>.mp3
```

A valid output is fully decoded and reused. An invalid output is preserved and never
overwritten. Target-bound state resumes a frozen increment without repeating finished
work. Never search, copy, or reuse another namespace's state.

Do not assume every replay is one hour. Weixin correctness comes from exact-link
binding, fresh changes, same-context URL/key proof, decrypted MP4 header, declared
source bytes, largest verified candidate ordering, and final full decode. Other
providers require a completed downloader/converter result and the same final full
decode. Add
`--min-duration <SECONDS>` only when the user gives a reliable floor.

If the user explicitly asks for a separate local profile, add
`--profile <validated-name>` and keep it for every step. A profile separates files, not
the shared WeChat login; different people should use different OS accounts.

## Finish gate

Before reporting completion, require final JSON status `completed` (or an explicit
verified reuse result), confirm the MP3 exists, and report exact path, bytes, and
duration. A player window, candidate, download start, or partial MP3 is not completion.

State plainly that Windows WeChat runtime capture still needs real-machine validation
if the task concerns that Weixin-specific route rather than a completed conversion.
Windows/macOS offline tests and CI prove routing and dependency installation, but do
not guarantee every external website, region, account, or individual URL remains
extractable.
