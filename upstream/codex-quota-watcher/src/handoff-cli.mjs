#!/usr/bin/env node

import path from "node:path";
import {
  checkpointWorkspace,
  defaultCodexHome,
  endHandoffSession,
  inspectHandoff,
  installHandoffAgent,
  startHandoffSession,
} from "./handoff.mjs";

function usage() {
  console.log(`Codex local account handoff

Usage:
  codex-handoff checkpoint [WORKSPACE]
  codex-handoff resume [WORKSPACE]
  codex-handoff session-start --profile PROFILE [WORKSPACE]
  codex-handoff session-end --profile PROFILE --exit-code CODE [WORKSPACE]
  codex-handoff install-agent [--codex-home PATH]

Commands:
  checkpoint      Capture local Git facts.
  resume          Check whether the saved handoff still matches the current worktree.
  session-start   Checkpoint and record the active local profile before Codex starts.
  session-end     Final-checkpoint and record process exit status after Codex exits.
  install-agent   One-time install of handoff instructions into a profile CODEX_HOME/AGENTS.md.

This tool never reads or copies auth.json, tokens, cookies, provider credentials, or native session stores.`);
}

function parseInstallArgs(args) {
  let codexHome = defaultCodexHome();
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--codex-home") {
      if (!args[index + 1]) throw new Error("--codex-home requires a path");
      codexHome = path.resolve(args[++index]);
    } else {
      throw new Error(`unknown argument: ${args[index]}`);
    }
  }
  return codexHome;
}

function parseSessionArgs(args, { requireExitCode = false } = {}) {
  let profile = null;
  let exitCode = null;
  let workspace = ".";
  let workspaceSet = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--profile") {
      if (!args[index + 1]) throw new Error("--profile requires a value");
      profile = args[++index];
    } else if (arg === "--exit-code") {
      if (!args[index + 1]) throw new Error("--exit-code requires a value");
      exitCode = args[++index];
    } else if (arg.startsWith("--")) {
      throw new Error(`unknown argument: ${arg}`);
    } else if (!workspaceSet) {
      workspace = arg;
      workspaceSet = true;
    } else {
      throw new Error(`unexpected argument: ${arg}`);
    }
  }

  if (!profile) throw new Error("--profile is required");
  if (requireExitCode && exitCode === null) throw new Error("--exit-code is required");
  if (!requireExitCode && exitCode !== null) throw new Error("--exit-code is only valid for session-end");
  return { profile, exitCode, workspace };
}

async function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command || command === "--help" || command === "-h") {
    usage();
    return;
  }

  if (command === "checkpoint") {
    if (args.length > 1) throw new Error("checkpoint accepts at most one workspace path");
    const result = await checkpointWorkspace(args[0] || ".");
    console.log(`handoff checkpoint ready: ${result.handoffDir}`);
    console.log(`branch: ${result.snapshot.branch}`);
    console.log(`head: ${result.snapshot.head}`);
    console.log(`dirty: ${result.snapshot.dirty ? "yes" : "no"}`);
    return;
  }

  if (command === "resume") {
    if (args.length > 1) throw new Error("resume accepts at most one workspace path");
    const result = await inspectHandoff(args[0] || ".");
    if (!result.exists) {
      console.log("no handoff exists yet; reconstruct from the current repository state");
      process.exitCode = 2;
      return;
    }
    console.log(`handoff: ${result.handoffDir}`);
    console.log(`state: ${result.fresh ? "fresh" : "stale"}`);
    console.log(`current branch: ${result.current.branch}`);
    console.log(`current head: ${result.current.head}`);
    if (result.session?.current) {
      console.log(`recorded profile: ${result.session.current.profile}`);
      console.log(`recorded exit: ${result.session.current.exitCode ?? "not recorded"}`);
    }
    if (!result.fresh) {
      console.log("current repository state differs from the saved checkpoint; current files/Git take precedence");
    }
    return;
  }

  if (command === "session-start") {
    const parsed = parseSessionArgs(args);
    const result = await startHandoffSession(parsed.workspace, parsed.profile);
    console.log(`handoff session started: ${result.session.current.profile}`);
    console.log(`handoff: ${result.handoffDir}`);
    console.log(`fingerprint: ${result.snapshot.fingerprint}`);
    return;
  }

  if (command === "session-end") {
    const parsed = parseSessionArgs(args, { requireExitCode: true });
    const result = await endHandoffSession(parsed.workspace, parsed.profile, parsed.exitCode);
    console.log(`handoff session ended: ${result.session.current.profile}`);
    console.log(`exit code: ${result.session.current.exitCode}`);
    console.log(`fingerprint: ${result.snapshot.fingerprint}`);
    return;
  }

  if (command === "install-agent") {
    const agentsPath = await installHandoffAgent(parseInstallArgs(args));
    console.log(`handoff agent installed: ${agentsPath}`);
    return;
  }

  throw new Error(`unknown command: ${command}`);
}

main().catch((error) => {
  console.error(`codex-handoff failed: ${error.message}`);
  process.exitCode = 1;
});
