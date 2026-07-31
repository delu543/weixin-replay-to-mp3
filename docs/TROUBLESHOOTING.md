# Troubleshooting

## `unsupported_platform`

The automatic File Transfer Assistant path is macOS-only. A Windows or Linux adapter
would need separate official WeChat process/window/runtime implementations; changing a
path string is not enough.

## Screenshot is white or WeChat is missing from capture

Do not relaunch WeChat repeatedly and do not attempt to turn off protection. The runtime
already treats this as a branch:

1. Confirm outer `com.tencent.xinWeChat` and `WeChatAppEx`.
2. Raise the window through Accessibility.
3. Read AX window metadata.
4. Fall back to WindowServer title and geometry without protected pixels.
5. Continue only if the File Transfer Assistant target gates still pass.

If the target cannot be proven, the correct result is a safe stop before sending.

## It selected another chat or reports target mismatch

Do not retry by blindly clicking a row. Keep WeChat open, make `文件传输助手` visible in
the pinned list, and rerun. The workflow must verify the left name, right header, green
icon signature, and newest-message state together. A mismatch is not bypassable.

## The link was sent but no playback proof appeared

A player window is not enough. The automatic path performs at most two bounded
metadata-guided canvas activations and requires both WeChatAppEx `Playing audio` and
`Video Wake Lock` assertions. Check VPN/network state and retry the same link; the exact
verified message is reused rather than sent again.

Use `--manual-playback` only after the user explicitly opens and starts that exact link.

## It found a small MP4 but the video should be longer

The candidate must be from this run's causal increment and pass MP4-prefix decryption.
The converter orders verified candidates by declared source bytes and checks the final
download length. If the user knows a reliable floor, add `--min-duration <seconds>`.
Do not hard-code one hour for all future links.

## Download is slow or interrupted

The downloader uses bounded parallel ranges with per-span checksums. Rerun the same
short link and output path; it resumes only missing or invalid spans. Do not delete the
target-bound `work/` state or rename a partial download during recovery.

## Existing MP3 is rejected

The file is preserved. The CLI refuses to overwrite an existing output that fails full
decode or the requested minimum duration. Inspect it, choose an explicit new
`--output`, or move it yourself after deciding it is not needed.

## `ffmpeg not found`

Run `python3 scripts/bootstrap.py install`. It installs pinned macOS wheels into a
user-private venv. If using a system ffmpeg, set `FFMPEG` to its exact executable path.

## Codex does not recognize the Skill immediately

The same repository task can run `weixin_replay_cli.py` directly after installation.
For new Codex tasks, restart Codex once so it reloads user-level Skills.

## The same Mac is used by more than one person

Use separate macOS accounts for a real security boundary because the WeChat login and
desktop UI belong to the macOS session. If one person only needs separate local tool
workspaces inside their own account, pass the same validated `--profile <name>` on each
run. Different profiles never reuse each other's MP3 or resumable state.

Do not point `WEIXIN_REPLAY_DATA_ROOT`, `WEIXIN_REPLAY_OUTPUT_ROOT`,
`REPLAY_MP3_LIBRARY`, `REPLAY_MP3_WORK_ROOT`, or an explicit `--output` at a shared
directory unless sharing is an intentional user decision.
