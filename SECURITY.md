# Security

## Supported security model

- Official desktop WeChat, the current OS account, and one supplied short link.
- macOS: fail-closed File Transfer Assistant verification before input or Return.
- Windows: no automatic WeChat sending/clicking in this release; the bounded recent
  runtime scan requires explicit user-confirmed exact-link playback.
- Same-context encrypted-source proof, resumable download, and full decode before
  completion on both systems.
- User-local installation with no root/administrator privileges.
- Opaque per-user/profile namespace; macOS private modes and Windows LocalAppData/NTFS
  account boundary.

## Explicitly excluded

- Certificate or MITM proxy installation.
- System proxy changes, TUN drivers, or global traffic interception.
- WeChat hooks, injection, package modification, jailbreak, or protection disabling.
- Chat/contact database reads or credential extraction.
- Blind Windows UI coordinates or sending to an unverified chat.
- Opaque third-party downloader executables.
- Silent remote upload or telemetry.
- Cross-user reuse of another namespace's outputs, checkpoints, signed URLs, or decode
  material.

## Credentials

Optional provider routes accept environment variable names documented in source. Never
commit their values. Reports recursively redact cookies, tokens, authorization, signed
URLs, `decodeKey`, numeric keys, and similar fields.

If a secret appears in a report or Git diff, stop publication, preserve the private
original locally, remove the value from the clean package, rotate the affected secret,
and rerun `python scripts/release_check.py`.

## Reporting a vulnerability

Do not open a public issue containing a signed media URL, key, cookie, account detail,
private path, or replay artifact. Send a minimal synthetic reproduction to the
repository owner through a private channel first.

## Limitations

This is source tooling, not a signed/notarized consumer app. Official WeChat UI and
runtime layouts, CDN behavior, OS permissions, and platform policy can change. Safety
gates stop when evidence is missing; they cannot guarantee every external link remains
extractable.

macOS automatic UI/capture has real-machine evidence. Windows path/install routing,
manual-gate behavior, DirectShow command construction, and the shared media core have
offline/CI coverage, but a real Windows WeChat runtime extraction has not yet been
completed for this release. Do not describe that part as fully proven until it passes a
real Windows machine regression.

One OS login is one security principal and one visible WeChat session. `--profile`
provides file separation, not authentication. Use separate OS accounts when different
people must not share WeChat credentials or UI state.
