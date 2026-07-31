# Privacy

This project is local-first. Its automatic scope is one user-supplied Weixin Channels
short link at a time.

## Data the workflow may use locally

- The supplied `weixin.qq.com/sph/...` link.
- Process, accessibility, WindowServer, and power-assertion metadata needed to prove
  the official WeChat target and playback state.
- Newly changed files from bounded WeChat playback/runtime roots.
- Encrypted media bytes, a same-context decode value, resumable download checksums,
  the decrypted MP4 working file, and the final MP3.

These items remain on the user's Mac. Sensitive values and signed media query strings
must not be printed in normal reports or committed.

## Data the workflow does not read

- WeChat chat or contact databases.
- Unrelated conversations or message history.
- Browser Cookies, Login Data, Web Data, or Keychain secrets.
- Arbitrary account tokens or passwords.
- Global network traffic.

## Storage

- Final MP3: `~/Downloads/WeixinReplayMP3/` by default.
- Private resumable/runtime evidence: the installed runtime's `work/` directory.
- User-level application files: `~/Library/Application Support/WeixinReplayToMP3/`.

The project never auto-deletes these files. A later cleanup requires a separate,
itemized user decision.

## Model boundary

The conversion itself does not require uploading media to an AI model. Codex sees
commands, sanitized diagnostics, and final paths. If a user later asks Codex to
transcribe or summarize the MP3, that is a separate data-processing decision governed
by the user's Codex account and data settings.
