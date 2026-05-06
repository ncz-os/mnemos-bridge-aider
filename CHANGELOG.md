# Changelog

## [0.2.0] — 2026-05-05

### Added

- Path B: slash-command shim for `aider-chat==0.86.2`, adding `/mnemos-search` and `/mnemos-create` by patching `aider.commands.Commands` at startup.

## 0.1.0

- Initial Aider adapter package.
- Added Path A `mnemos-aider` sidecar CLI for search, create, get, list, and config.
- Added Path B `MnemosAiderAdapter` for OpenAI-shaped Aider tools and best-effort coder registration.
- Added offline CLI and adapter tests plus a skipped live Path A integration workflow.
