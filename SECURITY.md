# Security

## Supported security model

- Official macOS WeChat, current logged-in user, and one supplied link.
- Fail-closed File Transfer Assistant verification before any input or Return.
- Causal, bounded runtime-file observation after exact-link playback proof.
- Prefix decryption proof before a full download and full decode before completion.
- User-local installation with no root privileges.

## Explicitly excluded

- Certificate or MITM proxy installation.
- System proxy changes, TUN drivers, or global traffic interception.
- WeChat hooks, injection, package modification, jailbreak, or protection disabling.
- Chat/contact database reads or credential extraction.
- Opaque third-party downloader executables.
- Silent remote upload or telemetry.

## Credentials

Optional provider routes accept environment variable names documented in source. Never
commit their values. Normal reports recursively redact cookies, tokens, authorization,
signed URLs, `decodeKey`, numeric keys, and similar fields.

If a secret appears in a report or Git diff, stop publication, preserve the private
original locally, remove the value from the clean package, rotate the affected secret,
and rerun `python3 scripts/release_check.py`.

## Reporting a vulnerability

Do not open a public issue containing a signed media URL, key, cookie, account detail,
private path, or replay artifact. Send a minimal reproduction with synthetic data to the
repository owner through a private channel first.

## Limitations

This is source tooling, not a signed or notarized consumer app. macOS permissions,
official WeChat UI changes, CDN behavior, and platform policy can change. The target
gates are designed to stop safely when evidence is missing; they cannot guarantee that
every external link remains extractable forever.
