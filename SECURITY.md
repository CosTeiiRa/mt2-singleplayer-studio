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

Use the repository's [private vulnerability reporting](https://github.com/CosTeiiRa/mt2-singleplayer-studio/security/advisories/new)
when **Security → Report a vulnerability** is available. If that option is
unavailable, contact the maintainer through the private channel where you
received the beta to arrange a private report. Do not open a public issue with
security details, tokens, private game files or exploit instructions.

Provide affected versions and a minimal reproduction with invented data. The
maintainer must enable and test GitHub private vulnerability reporting when the
repository becomes public; the private beta uses its existing private contact
channel. No response deadline is promised.

## Private material

Keep game `.env` files, Studio settings/state, database backups, credentials and
session tokens out of source control and reports. Configuration backups can
contain the original `.env` in full. The release allowlist excludes private state;
it does not establish that an existing Git history or CI log is clean. Follow the
[publication checklist](docs/BETA_REVIEW.md#before-making-a-repository-public).
