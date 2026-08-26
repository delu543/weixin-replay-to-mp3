# Third-Party Notices

No third-party downloader binary, proxy, certificate, driver, or captured user data is
bundled in this repository.

## imageio-ffmpeg

The installer downloads `imageio-ffmpeg==0.6.0` from PyPI using pinned SHA-256 wheel
hashes for macOS arm64/x86_64 or Windows x86/x86_64, selected by the local platform.
The package is distributed under the BSD 2-Clause License. Its bundled ffmpeg
executable remains subject to the license configuration of that binary. See
<https://github.com/imageio/imageio-ffmpeg>.

## FFmpeg

FFmpeg is invoked as an external executable for media conversion and full-decode
verification. This repository does not contain an FFmpeg binary. See
<https://ffmpeg.org/legal.html>.

On Windows, the explicit recording fallback can address an existing DirectShow audio
input. The repository does not bundle, install, or enable a loopback/virtual-audio
driver.

## ISAAC / ISAAC64

The numeric-key compatibility implementation uses the ISAAC64 algorithm. Bob Jenkins'
reference ISAAC implementation was placed in the public domain and may be used for
private, educational, or commercial purposes. See
<https://burtleburtle.net/bob/rand/isaacafa.html>.

The repository does not copy or bundle the `ltaoo/wx_channels_download` application,
its proxy/certificate components, or its Commons-Clause-licensed distribution. That
project was reviewed only as an architecture/compatibility reference.

## Optional Weixin WASM assets

The string `decode_key` compatibility route may download two files at runtime from
`Evil0ctal/WeChat-Channels-Video-File-Decryption`:

- `wasm_video_decode.js`
- `wasm_video_decode.wasm`

That upstream project is MIT licensed, Copyright (c) 2025 Evil0ctal. The assets are not
committed here; they are fetched only if that optional route is used and remain in the
local private work directory. See
<https://github.com/Evil0ctal/WeChat-Channels-Video-File-Decryption>.

## Platform names

WeChat and Weixin are trademarks of their respective owners. This project is not
affiliated with or endorsed by Tencent, WeChat, OpenAI, or the projects listed above.
