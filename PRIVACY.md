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

These items remain on the user's Mac and inside that local user's/profile's namespace.
Sensitive values and signed media query strings must not be printed in normal reports
or committed.

## Data the workflow does not read

- WeChat chat or contact databases.
- Unrelated conversations or message history.
- Browser Cookies, Login Data, Web Data, or Keychain secrets.
- Arbitrary account tokens or passwords.
- Global network traffic.

## Storage

- Final MP3: `~/Downloads/WeixinReplayMP3/<opaque-namespace>/` by default.
- Private resumable/runtime evidence:
  `~/Library/Application Support/WeixinReplayToMP3/data/profiles/<opaque-namespace>/`.
- Runtime code and dependencies remain under the current macOS account's
  `~/Library/Application Support/WeixinReplayToMP3/`.

The namespace is a one-way short hash of the local macOS security principal and an
optional validated profile label. Raw usernames and profile labels are not used as
directory names. Different computers and different macOS accounts have no shared
backend or automatic data exchange. A direct source checkout uses the same user-local
data root instead of writing private run data into the Git repository.

Multiple humans sharing one macOS login also share its WeChat desktop session. An
optional `--profile` separates tool files inside that account, but true identity and
credential isolation requires separate macOS accounts.

The project never auto-deletes these files. Legacy v0.1.0 files are left in place and
are not automatically imported into a new namespace. A later cleanup or migration
requires a separate, itemized user decision.

## Model boundary

The conversion itself does not require uploading media to an AI model. Codex sees
commands, sanitized diagnostics, and final paths. If a user later asks Codex to
transcribe or summarize the MP3, that is a separate data-processing decision governed
by the user's Codex account and data settings.
