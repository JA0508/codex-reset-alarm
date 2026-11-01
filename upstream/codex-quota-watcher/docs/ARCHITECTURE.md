# Architecture

```text
Authenticated Codex app-server
  ├─ account/rateLimits/read ──> normalizer ──> reset classifier
  ├─ rateLimits/updated ───────> authoritative re-read
  └─ workspaceMessages/read ───> strict intent classifier
                                           │
                  atomic redacted state <──┤
                                           v
                           console / desktop / webhook
```

## Trust model

- **Confirmation:** a persisted account transition from blocked to available.
- **Classification:** compare the recovery time with the reset timestamp that was saved while blocked.
- **Reset credit:** compare only the authoritative available count; never store credit IDs or redeem credits.
- **Warning:** require an authenticated official account message containing Codex/quota, reset language, and future intent. Negated and ambiguous messages are rejected.
- **Unknown:** malformed, missing, unsupported, or disconnected inputs fail closed.

Public social sources are deliberately outside the V0.2 runtime. They can be useful to a human, but scraping, mirrors, reposts, and keyword matches do not provide a stable identity or enough semantics for a high-confidence alert.

## State machine

```text
UNKNOWN ──valid read──> AVAILABLE or BLOCKED       no event
AVAILABLE ────────────> AVAILABLE                  no reset event
AVAILABLE ────────────> BLOCKED                    remember timing
BLOCKED ──────────────> BLOCKED                    no reset event
BLOCKED ──────────────> AVAILABLE before deadline  extra reset confirmed
BLOCKED ──────────────> AVAILABLE near/after time  scheduled reset confirmed
old weekly window ────> new weekly window           missed refresh confirmed
credit count N ───────> credit count > N           reset credit granted
ANY ─────────────────> UNKNOWN                    fail closed
```

The early-reset boundary is 15 minutes before the previously observed deadline. This absorbs normal polling and clock skew without turning ordinary usage changes into reset claims.

## Compatibility

- Prefer `rateLimitsByLimitId[limitId]`, then fall back to `rateLimits`.
- Choose the weekly display window by duration, not by assuming primary or secondary.
- Preserve V0.1 state through an automatic in-memory schema migration.
- Treat unsupported workspace messages as optional; account monitoring continues.
