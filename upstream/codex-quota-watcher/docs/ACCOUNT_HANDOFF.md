# Local Codex account handoff

This feature preserves project continuity when a user intentionally changes between user-owned Codex/ChatGPT profiles. It does not automate account rotation, bypass rate limits, copy credentials, or migrate native Codex sessions between accounts.

## Boundary

The shared unit is the local Git worktree, not the Codex account session.

The local handoff stores only:

- repository name and root
- branch and HEAD
- staged/unstaged summaries
- changed file paths
- recent commit subjects
- profile lifecycle metadata: profile ID, timestamps, fingerprints, and process exit code
- a compact semantic `HANDOFF.md` written by the active Codex profile when possible

It never reads or copies `auth.json`, OAuth tokens, API keys, cookies, native session stores, model cache databases, source-file contents, full chat transcripts, or private reasoning.

A non-zero or missing process exit is recorded only as lifecycle evidence. It is not interpreted as proof that quota was exhausted.

## One-time dual-profile setup on Windows

The Windows bootstrap creates isolated A/B profile homes and installs the handoff rule into both profiles:

```powershell
.\scripts\setup-dual-codex.ps1 -LoginSecondary
```

Profile A preserves the existing/default `CODEX_HOME`. Profile B receives its own isolated `CODEX_HOME`. The optional `-LoginSecondary` flag opens the official Codex login flow inside B's home; credentials are not copied between profiles.

The bootstrap generates:

```text
codex-a
codex-b
```

Use either launcher with the same local workspace. For Git workspaces the launcher automatically performs the handoff lifecycle described below.

## Automatic launcher lifecycle

Before Codex starts, the launcher runs the equivalent of:

```powershell
codex-handoff session-start --profile A .
```

or:

```powershell
codex-handoff session-start --profile B .
```

This writes a fresh factual checkpoint and records the current/previous profile transition.

After the Codex process returns, including a non-zero process exit, the launcher runs `session-end`. That operation takes another Git checkpoint and records the exit code and final fingerprint. Work created during the Codex process is therefore included in the latest factual snapshot whenever the launcher regains control.

This is not an automatic account switch. The user still explicitly chooses `codex-a` or `codex-b`.

## Local handoff files

For a Git workspace the runtime files are:

```text
.codex-handoff/
  FACTS.md
  facts.json
  HANDOFF.md
  SESSION.md
  session.json
```

The directory is added to `.git/info/exclude`, so it is local-only and the repository's tracked `.gitignore` is not changed.

`FACTS.md` / `facts.json` contain factual Git state. `SESSION.md` / `session.json` contain only safe launcher lifecycle metadata. `HANDOFF.md` contains the small amount of semantic context Git cannot reconstruct:

- Objective
- Completed
- Decisions / constraints
- Blockers
- Next action

## Recovery on the next profile

The installed Codex profile rule tells a newly started profile to read `SESSION.md`, `HANDOFF.md`, and `FACTS.md` before changing files.

If the previous profile differs from the current profile, the new profile should continue from:

1. the current Git worktree, which is authoritative;
2. the latest factual checkpoint;
3. the compact semantic handoff when it remains consistent with the repository;
4. project files and tests.

The new profile should not ask the user to repeat information that can be reconstructed from those sources. If the prior profile ended before writing semantic context, unknown intent must be marked as a context gap rather than invented.

A manual consistency check remains available:

```powershell
codex-handoff resume .
```

`fresh` means the current Git worktree matches the saved factual checkpoint. `stale` means the worktree changed after that checkpoint; current files/Git take precedence.

## Manual lifecycle commands

The automatic launchers are the normal path. The underlying commands are available for integration with a future GUI:

```powershell
codex-handoff session-start --profile B "C:\path\to\workspace"
codex-handoff session-end --profile B --exit-code 0 "C:\path\to\workspace"
```

A GUI can invoke the same commands around an explicit profile launch without receiving or transporting any credential data.

## Failure boundary

The final checkpoint can run only if the launcher process regains control. A machine crash, forced process-tree termination, or storage failure can prevent `session-end` from being written. In that case, `SESSION.md` may show no recorded end and the next profile reconstructs from current Git/files plus the last available checkpoint.

Native Codex conversation/session state remains account-specific and is not migrated. The continuity layer aims to preserve project state and recoverable task context, not to impersonate native cross-account thread resume.
