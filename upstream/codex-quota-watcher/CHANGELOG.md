# Changelog

## 0.2.1 - 2026-08-13

- Localize desktop, console, and webhook reset-event messages when `--lang zh` is selected.

## 0.2.0 - 2026-08-13

- Separate the normal weekly refresh from possible or confirmed extra resets.
- Classify blocked recovery as scheduled, early/extra, or untyped when evidence is incomplete.
- Recover a missed normal weekly-refresh notification from persisted window rollover evidence.
- Detect newly granted earned reset credits without storing IDs or consuming them.
- Add strict authenticated workspace-message intent warnings with negation handling.
- Add a compact Chinese/English three-line status view.
- Migrate V0.1 state automatically and expand false-positive tests.
- Remove launch copy and repository promotion material.

## 0.1.0 - 2026-08-12

- Read the authenticated Codex quota snapshot through `codex app-server`.
- Detect only persisted blocked-to-available transitions.
- Ignore ordinary decreases in `usedPercent`.
- Add atomic local state and event deduplication.
- Add console, desktop, and opt-in webhook notification adapters.
- Add Windows, macOS, and Linux launch paths with no runtime npm dependencies.
- Document evidence levels, privacy boundaries, limitations, and architecture.
