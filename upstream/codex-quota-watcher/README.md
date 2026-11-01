# Codex Quota Watcher

Know the difference between a normal Codex refresh, an early recovery, and an earned reset credit.

Codex Quota Watcher reads the authenticated local `codex app-server`. It does not scrape the Codex UI, inspect credentials or private logs, start model turns, redeem reset credits, collect telemetry, or display advertising.

> V0.2 is intentionally conservative. Account changes can confirm what happened. A possible future reset is shown only when the authenticated account receives an explicit official message about an upcoming Codex reset. Social posts and community reports are not treated as proof.

## What you see

```text
Codex 额度
────────────────────────────
每周刷新      8月19日 23:31
额外重置      暂无可靠信号
当前状态      可用 · 最高已用 42%
```

The three lines deliberately have different meanings:

- **Weekly refresh** is the next reset timestamp of a weekly-sized account window.
- **Extra reset** is a separate warning, never inferred from an ordinary usage decrease.
- **Current status** is the server-classified account state and maximum observed usage.

## Reset classification

| Result | Required evidence |
|---|---|
| `SCHEDULED_RESET_CONFIRMED` | A previously blocked bucket becomes available at or after its expected reset time. |
| `EXTRA_RESET_CONFIRMED` | A previously blocked bucket becomes available more than 15 minutes before its expected reset time. |
| `RECOVERY_CONFIRMED` | The bucket recovers, but the prior response did not include enough timing evidence to prove the reset type. |
| `RESET_CREDIT_GRANTED` | `rateLimitResetCredits.availableCount` increases. This does **not** mean quota was automatically restored. |
| `EXTRA_RESET_POSSIBLE` | An authenticated official workspace message explicitly refers to a future Codex quota reset. |

These never count as a reset: a lower `usedPercent` by itself, a moving `resetsAt` value, first launch, network failure, a community rumor, or an unrelated OpenAI Status recovery.

If the watcher was offline during a normal weekly boundary, it can report the refresh after restart when the persisted old window has ended and the account exposes a new weekly window. If it had previously persisted a blocked state, it can likewise report recovery after restart. It cannot prove an unobserved extra reset when no prior baseline exists.

## Requirements

- Node.js 20 or newer.
- A recent Codex CLI with `codex app-server` and ChatGPT-backed authentication.
- Windows, macOS, or Linux.

API-key-only and Bedrock authentication do not expose the ChatGPT account rate-limit endpoint.

## Install

```bash
git clone https://github.com/sui-ni2/codex-quota-watcher.git
cd codex-quota-watcher
npm install
npm link
```

There are no runtime npm dependencies.

## Run

Show the current status and establish a baseline:

```bash
codex-quota-watcher --once
```

Use Chinese or English explicitly:

```bash
codex-quota-watcher --once --lang zh
codex-quota-watcher --once --lang en
```

Watch continuously and notify once per meaningful event:

```bash
codex-quota-watcher --interval 60
```

Useful options:

```text
--once              Read once, save the baseline, and exit
--interval SECONDS  Poll interval, minimum 15 seconds
--limit-id ID       Rate-limit bucket, default: codex
--notify CHANNELS   console, desktop, webhook
--state-file PATH   Override the local state file
--codex-bin PATH    Override the Codex executable
--lang LANG         auto, zh, or en
--json              Print the redacted normalized result
```

The optional webhook URL comes only from `CODEX_QUOTA_WATCHER_WEBHOOK_URL` and is never written to state or logs.

## Evidence boundary

The official [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server) defines the read-only `account/rateLimits/read` method, the `account/rateLimits/updated` notification, earned reset credits, and authenticated workspace messages.

The watcher uses those account-scoped signals as follows:

1. Account state confirms actual recovery.
2. Earned reset count confirms a reset credit was granted, not consumed.
3. Official workspace messages can warn about a possible future reset.
4. Public staff posts, GitHub reports, Reddit, and third-party trackers are not ingested in V0.2 because no stable, unauthenticated source proves their identity and meaning reliably enough.

This boundary is a feature: the tool prefers “unknown” over a confident-looking false alert.

## Platform setup

See [Platform setup](docs/PLATFORMS.md) for Windows Task Scheduler, macOS `launchd`, Linux, absolute path handling, and state locations.

## Privacy and security

See [Privacy and security](docs/PRIVACY.md). The watcher never calls `account/rateLimitResetCredit/consume`.

## Test

```bash
npm test
npm run check
```

CI covers Node.js 20 and 22 on Windows, macOS, and Ubuntu. A real authenticated quota read has been verified on Windows; macOS and Linux account behavior still needs independent real-account verification.

## Limitations

- The app-server protocol can evolve with Codex releases.
- The watcher cannot reconstruct an account transition that happened while it was offline.
- An early recovery proves that quota returned before the recorded deadline; it cannot prove the organizational reason OpenAI chose to restore it.
- Official intent warnings depend on the account actually receiving a matching workspace message.
- This is an independent community project, not an OpenAI product.

## License

MIT
