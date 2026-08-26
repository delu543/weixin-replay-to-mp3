# Capability Map

This map separates implemented code, real-machine evidence, and portability.

| Capability | macOS | Windows | Safety contract and evidence |
| --- | --- | --- | --- |
| Codex-first link intake | active | active | Accept only `https://weixin.qq.com/sph/<id>`; CLI validation and tests |
| File Transfer Assistant targeting | active, guarded automatic route | manual user step | macOS verifies left name, right header, icon, and exact newest link before input; Windows never sends/clicks blindly |
| Protected-window fallback | active with limits | not used by the manual route | macOS treats white pixels as unavailable and uses process/AX/WindowServer metadata; it never disables protection |
| Exact-link playback proof | active automatic assertions | explicit user confirmation | Windows recent-runtime scan is disabled until `--manual-playback`; mocked fail-closed regressions cover the gate |
| Causal/recent runtime capture | active | implemented for known safe roots; real-machine validation pending | Exclude chat/contact/cookie/history stores and bind private run state to the short ID |
| Encrypted candidate proof | active | shared platform-neutral code | Pair URL/key from the same context; decrypt a bounded prefix and require MP4 `ftyp`; real macOS runs plus decode tests |
| Resumable source download | active | shared platform-neutral code | Bounded range workers, per-span checksums, declared final byte count; real macOS runs plus range tests |
| MP3 conversion and full verification | active | active | FFmpeg conversion followed by full decode; Windows CI exercises the same Python surface |
| Authorized local media conversion | active | active | `convert-file` preserves an existing output and requires full decode before completion |
| Same-link reuse/resume | active | active | Fixed short-ID output and target-bound private run state; pipeline-state tests |
| Per-user data isolation | active | active | Opaque namespace binds local OS principal + validated profile; macOS modes and Windows LocalAppData/NTFS account boundary |
| Automatic dependency install | active | active | User-requested only; user-local venv; platform-specific pinned `imageio-ffmpeg` hashes; no root/admin |
| Explicit audio-recording fallback | ScreenCaptureKit/AVFoundation | DirectShow device selected by user | Last resort only; never install/enable a driver; implementation tests, Windows real-device validation pending |
| Windows automatic WeChat UI control | n/a | not implemented | Must not be advertised; a missing adapter stops before sending or scanning |
| Linux/local cloud WeChat control | not implemented | not implemented | Unsupported platform fails closed |
| Consumer-grade signed app | not shipped | not shipped | Source + Codex workflow, not signed/notarized GUI software |

## macOS active workflow

1. Validate the supplied link and reuse a verified target-bound MP3 if present.
2. Check authorized local source artifacts and bounded direct routes.
3. Baseline safe WeChat runtime files.
4. Open only the verified File Transfer Assistant conversation, send/reuse the exact
   link, open it, and prove playback.
5. Freeze the causal increment, prove the encrypted MP4 candidate, resume/download,
   convert to MP3, and full-decode verify.

## Windows active workflow

1. Validate the same link and reuse an existing verified output/resumable state.
2. Try the same authorized local source and bounded direct routes.
3. If no source is available, stop before UI control or recent-runtime scanning and
   ask the user to open `文件传输助手`, send/open the exact newest link, and start it.
4. Only after explicit confirmation, run with `--manual-playback` and inspect the
   bounded safe Windows playback/runtime roots.
5. Use the same candidate proof, resume/download, conversion, and full-decode gates.
6. If the runtime layout is not compatible, offer an authorized local media file;
   explicit audio-device recording remains the last resort.

All steps use one local storage namespace. Another namespace cannot reuse its output or
checkpoint. There is no shared service or Git-backed runtime state.

## Evidence boundary

- macOS automatic File Transfer Assistant and causal capture have current-machine real
  run evidence.
- Windows path selection, installer, safe-stop/manual routing, DirectShow command
  construction, and shared media core have offline tests and Windows CI coverage.
- This release has not yet completed a real Windows WeChat playback/cache extraction.
  Until that happens, Windows UI remains manual and Windows runtime capture is marked
  real-machine validation pending rather than “fully proven.”

## Intentionally excluded

- No certificate proxy, system proxy change, app hook, package modification,
  chat/contact database read, opaque downloader binary, or protection-disabling
  mechanism is bundled.
- A small number of provider, Studio, and black-box compatibility modules are retained
  for regression coverage; they do not broaden the one-link authorization scope.
