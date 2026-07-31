---
name: weixin-replay-to-mp3
description: Convert one user-authorized Weixin Channels short link into a verified MP3 on macOS through the guarded File Transfer Assistant and causal playback-source workflow.
---

# Weixin Replay To MP3

Use this Skill when the user supplies an authorized
`https://weixin.qq.com/sph/...` link and asks for MP3 extraction.

## Runtime

```text
~/Library/Application Support/WeixinReplayToMP3/runtime
```

## Safety boundary

- The supplied link is the complete authorization scope.
- Sending is allowed only to the conversation proven to be exactly `文件传输助手`.
- Never read chat/contact databases, browser cookies, account tokens, or unrelated
  WeChat history.
- Never install certificates, change the system proxy, hook/patch WeChat, or disable
  protected-window behavior.
- Do not print signed media URLs, decode keys, cookies, or private runtime files.
- A white screenshot means pixels are unavailable. Use the implemented AX,
  WindowServer, process, exact-message, and playback-assertion gates; do not keep
  retrying blind screenshots.
- Any wrong/unknown chat, stale link, missing header/icon proof, or absent playback
  assertion must stop before an unbound cache scan.

## Normal command

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>"
```

The default output is stable for the short ID inside the current local isolation
namespace:

```text
~/Downloads/WeixinReplayMP3/<opaque-namespace>/weixin_<short-id>.mp3
```

That stability is intentional. A valid existing output is fully decoded and reused;
an invalid existing output is preserved and never overwritten. Target-bound private
state also resumes a frozen causal increment without reopening WeChat. Never search,
copy, or reuse another namespace's state.

The default namespace is derived locally from the current macOS account. If the user
explicitly asks for a separate local profile, add `--profile <validated-name>` and keep
that same profile for the entire task. A profile separates files, not the shared WeChat
login; different people should use different macOS accounts for a real security boundary.

## Duration handling

Do not assume every replay is one hour. Default correctness comes from exact-link
targeting, fresh causal changes, same-context URL/key proof, decrypted MP4 header,
declared source byte count, largest verified candidate ordering, and final full decode.

If the user explicitly gives a reliable minimum duration, pass it as seconds:

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "<USER_SUPPLIED_WEIXIN_LINK>" --min-duration <SECONDS>
```

## Failure routing

1. If readiness is unclear, run `preflight`; do not operate WeChat on an unsupported
   platform or without ffmpeg/Swift/official Mac WeChat.
2. If the target gate fails, report the exact gate and stop. Never send to another chat.
3. If the exact link opened but playback was not proven, retry only the bounded
   automatic activation. Then stop with the diagnostic path.
4. Use `--manual-playback` only after the user explicitly confirms they started the
   exact target in desktop WeChat. It is a fallback, not the normal workflow.
5. Preserve all prior outputs and private run evidence. Never delete or clean it as
   part of a retry.

## Finish gate

Before reporting completion, require the command's final JSON to show `completed`,
confirm the MP3 exists, and report its exact path, bytes, and duration. A download,
player window, candidate, or partially written MP3 is not completion.
