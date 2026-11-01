# Codex Quota Watcher v0.2.0

V0.2 makes reset claims more precise and keeps the visible status compact.

## Highlights

- Shows the normal weekly refresh separately from extra-reset evidence.
- Confirms whether a blocked quota recovered near its expected time or substantially early.
- Detects newly granted earned reset credits without redeeming them or persisting their IDs.
- Uses only authenticated official workspace messages for possible-reset warnings.
- Rejects ordinary usage decreases, timestamp drift, negated messages, rumors, and incomplete data.
- Adds a concise Chinese/English status view.
- Migrates V0.1 state automatically.
- Removes repository launch and promotion copy.

The account read path remains private and local through the documented Codex app-server. No telemetry, advertising, credential-file access, model turns, or social-feed scraping is included.
