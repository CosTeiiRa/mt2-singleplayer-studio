# Security reports

The small beta is a local, single-owner application. Keep Studio bound to
`127.0.0.1`; do not expose its port through your router, a proxy or a tunnel.
Session/origin checks reduce unintended local-browser requests. They do not make
Studio suitable as a shared or internet-facing administration service.

Add-ons execute Python with the game client's permissions. Capabilities describe
integration needs; they are not a security sandbox. Install only code and sources
you trust. Studio does not certify publishers or claim that checksums establish
that code is harmless.

## Report privately

Until a public repository and a private reporting channel are announced, report
potential credential disclosure, unsafe file writes or untrusted-code execution
through the private conversation used to obtain this beta. Do not publish an
exploit, a token or a private game file in a bug report or Discord message.
Provide affected versions and a minimal reproduction with invented data.

This package does not declare an invented contact address or response deadline.
Before public release, the maintainer must establish and test a private reporting
route and update this document with it. A public GitHub issue is not that route.

## Private material

Keep game `.env` files, Studio settings/state, database backups, credentials and
session tokens out of source control and reports. Configuration backups can
contain the original `.env` in full. The release allowlist excludes private state;
it does not establish that an existing Git history or CI log is clean. Follow the
[publication checklist](docs/BETA_REVIEW.md#before-making-a-repository-public).
