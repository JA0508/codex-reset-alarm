# Privacy and security

## Data the watcher reads

Through the local Codex app-server only:

- rate-limit bucket name;
- used percentage;
- reset timestamp and window duration;
- backend-classified reached state.
- earned reset-credit count, without credit IDs or descriptions;
- active official workspace message text transiently, only for reset-intent classification.

## Data the watcher does not read

- `~/.codex/auth.json` or other authentication stores;
- API keys, access tokens, cookies, or credentials;
- prompts, conversations, source code, session bodies, or Codex logs;
- account email, workspace name, or opaque reset-credit identifiers.

Authentication remains inside the official Codex CLI process.

## Data stored locally

The state file contains only the normalized snapshot, reset-credit count, the time a blocked state was first observed, a generic official-signal classification, and a deduplication key. Message bodies and opaque message or credit IDs are never persisted. Writes are atomic. On Unix-like systems the file is created with user-only permissions where supported.

## Network behavior

- Account reads are performed by the locally installed Codex CLI.
- No telemetry is added by this project.
- The watcher does not contact X, Reddit, GitHub, third-party trackers, or advertising services.
- Webhook delivery occurs only when the user explicitly enables the `webhook` notifier.
- Webhook URLs are never persisted or printed.

## Non-goals

The watcher does not bypass limits, redeem reset credits, impersonate another account, or automate paid actions.
