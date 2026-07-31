# Capability Map

This map separates implemented code, real-machine evidence, and portability.

| Capability | Status | Safety contract | Evidence |
| --- | --- | --- | --- |
| Codex-first link intake | active | Accept only `https://weixin.qq.com/sph/<id>`; one supplied link is the entire authorization scope | CLI validation and tests |
| File Transfer Assistant targeting | active on supported macOS | Before sending, verify the left name, right header, green icon, and exact latest-link state; any ambiguity stops before input | Current-machine real runs plus mocked regressions |
| Protected-window fallback | active with limits | White screenshots are treated as unavailable pixels, not app exit; use outer WeChat, `WeChatAppEx`, AX, and WindowServer metadata; never disable WeChat protection | Current-machine real runs plus file-helper tests |
| Exact-link playback proof | active | A player window alone is insufficient; require the exact newest link plus `Playing audio` and `Video Wake Lock` | Current-machine real runs |
| Causal runtime delta capture | active | Baseline before playback, freeze only changed safe runtime files, exclude chat/contact/cookie/history stores, bind checkpoint to the short ID | Real runs plus causal-capture tests |
| Encrypted candidate proof | active | Pair URL/key only from the same fresh context; decrypt a bounded prefix and require MP4 `ftyp` before full download | Real runs plus decode/source-pair tests |
| Resumable source download | active | Eight bounded range workers, per-span checksums, resume only missing/invalid spans, verify declared final byte count | Real large-source runs plus range tests |
| MP3 conversion and verification | active | FFmpeg conversion followed by full decode; no completion claim from file existence alone | Real outputs plus tests |
| Same-link reuse/resume | active | Fixed short-ID output and target-bound private run state; valid output skips UI/download, frozen causal capture resumes conversion | Pipeline-state tests and current-machine rerun |
| Optional source/provider route | active when user configures it | Environment variable names only; never print or commit values; reports redact signed URLs and keys | Sanitization and provider tests |
| Automatic dependency install | active | Runs only after a user asks to install/use; user-local venv; pinned `imageio-ffmpeg` hashes; no root | Bootstrap tests |
| Windows/Linux desktop WeChat automation | not implemented | Must not be advertised as supported | Platform doctor fails closed |
| Consumer-grade signed Mac app | not shipped | Repository is source + Codex workflow, not signed/notarized GUI software | Documentation boundary |

## Active workflow

1. Validate the supplied short link and reuse a verified target-bound MP3 if present.
2. Check authorized local source artifacts and bounded direct routes.
3. Baseline safe WeChat runtime files.
4. Open only the verified File Transfer Assistant conversation, send/reuse the exact
   link, open it, and prove playback.
5. Freeze the causal increment, prove the encrypted MP4 candidate, download with
   resume, decrypt the prefix, convert to MP3, and full-decode verify.
6. Return the exact MP3 path, duration, source byte count, and route evidence.

## Changed or intentionally excluded from the source workspace

- This repository exposes only the Weixin Channels replay-to-MP3 product surface.
  A small number of provider, Studio, and black-box compatibility modules are retained
  solely for regression coverage; they are not supported public v1 entry points. The
  complete development workspace remains untouched in its original location.
- Explicit scheme/default-browser opening is not part of the public automatic path.
- No certificate proxy, app hook, package modification, chat/contact database read,
  opaque downloader binary, or cross-process protection-disabling mechanism is bundled.
