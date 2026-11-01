import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";

import {
  AGENT_BLOCK_START,
  checkpointWorkspace,
  endHandoffSession,
  inspectHandoff,
  installHandoffAgent,
  safeDisplayPath,
  startHandoffSession,
} from "../src/handoff.mjs";

const execFileAsync = promisify(execFile);

async function git(root, ...args) {
  await execFileAsync("git", ["-C", root, ...args], { encoding: "utf8" });
}

async function createRepo() {
  const root = await mkdtemp(path.join(os.tmpdir(), "codex-handoff-test-"));
  await git(root, "init", "-q");
  await git(root, "config", "user.name", "Codex Handoff Test");
  await git(root, "config", "user.email", "handoff@example.invalid");
  await writeFile(path.join(root, "app.txt"), "safe source body\n", "utf8");
  await git(root, "add", "app.txt");
  await git(root, "commit", "-qm", "initial");
  return root;
}

test("checkpoint stores Git facts locally without copying source contents", async () => {
  const root = await createRepo();
  await writeFile(path.join(root, "app.txt"), "changed secret-looking source body\n", "utf8");

  const result = await checkpointWorkspace(root);
  const facts = await readFile(path.join(result.handoffDir, "FACTS.md"), "utf8");
  const semantic = await readFile(path.join(result.handoffDir, "HANDOFF.md"), "utf8");
  const exclude = await readFile(path.join(root, ".git", "info", "exclude"), "utf8");

  assert.match(facts, /app\.txt/);
  assert.doesNotMatch(facts, /changed secret-looking source body/);
  assert.match(semantic, /## Objective/);
  assert.match(exclude, /^\.codex-handoff\/$/m);

  const inspection = await inspectHandoff(root);
  assert.equal(inspection.exists, true);
  assert.equal(inspection.fresh, true);
});

test("resume detects a worktree change after the saved checkpoint", async () => {
  const root = await createRepo();
  await checkpointWorkspace(root);
  await writeFile(path.join(root, "app.txt"), "new work after checkpoint\n", "utf8");

  const inspection = await inspectHandoff(root);
  assert.equal(inspection.exists, true);
  assert.equal(inspection.fresh, false);
});

test("session lifecycle records profile transition and final post-Codex worktree", async () => {
  const root = await createRepo();

  const startedA = await startHandoffSession(root, "A");
  assert.equal(startedA.session.current.profile, "A");
  assert.equal(startedA.session.current.endedAt, null);
  assert.equal(startedA.session.previous, null);

  await writeFile(path.join(root, "after-start.txt"), "created while Codex was running\n", "utf8");
  const endedA = await endHandoffSession(root, "A", 7);
  assert.equal(endedA.session.current.exitCode, 7);
  assert.ok(endedA.session.current.endedAt);
  assert.equal(endedA.session.current.endFingerprint, endedA.snapshot.fingerprint);

  const facts = await readFile(path.join(endedA.handoffDir, "FACTS.md"), "utf8");
  const sessionText = await readFile(path.join(endedA.handoffDir, "SESSION.md"), "utf8");
  const sessionJson = JSON.parse(await readFile(path.join(endedA.handoffDir, "session.json"), "utf8"));
  assert.match(facts, /after-start\.txt/);
  assert.match(sessionText, /Current profile: `A`/);
  assert.match(sessionText, /Exit code: `7`/);
  assert.equal(sessionJson.current.exitCode, 7);

  const startedB = await startHandoffSession(root, "B");
  assert.equal(startedB.session.current.profile, "B");
  assert.equal(startedB.session.previous.profile, "A");
  assert.equal(startedB.session.previous.exitCode, 7);

  const inspection = await inspectHandoff(root);
  assert.equal(inspection.session.current.profile, "B");
  assert.equal(inspection.session.previous.profile, "A");
});

test("session lifecycle rejects unsafe profile identifiers and mismatched session end", async () => {
  const root = await createRepo();
  await assert.rejects(() => startHandoffSession(root, "A B"), /profile must be/);
  await startHandoffSession(root, "A");
  await assert.rejects(() => endHandoffSession(root, "B", 0), /active handoff session belongs to A/);
  await assert.rejects(() => endHandoffSession(root, "A", -1), /exit code/);
});

test("sensitive-looking paths are omitted from factual display", () => {
  assert.equal(safeDisplayPath(".env"), "[sensitive path omitted]");
  assert.equal(safeDisplayPath("secrets/token.txt"), "[sensitive path omitted]");
  assert.equal(safeDisplayPath("certs/client.pem"), "[sensitive path omitted]");
  assert.equal(safeDisplayPath("src/app.mjs"), "src/app.mjs");
});

test("agent install preserves existing instructions and is idempotent", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "codex-handoff-home-"));
  const agentsPath = path.join(home, "AGENTS.md");
  await writeFile(agentsPath, "# Existing rules\n\nKeep this.\n", "utf8");

  const installedPath = await installHandoffAgent(home);
  await installHandoffAgent(home);
  const content = await readFile(agentsPath, "utf8");

  assert.equal(installedPath, agentsPath);
  assert.match(content, /# Existing rules/);
  assert.match(content, /Keep this\./);
  assert.equal(content.split(AGENT_BLOCK_START).length - 1, 1);
  assert.match(content, /SESSION\.md/);
  assert.match(content, /profile launcher handles factual checkpoints automatically/);
  assert.doesNotMatch(content, /auth\.json/);
});

test("agent install uses an existing non-empty AGENTS.override.md because Codex gives it precedence", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "codex-handoff-override-"));
  const normalPath = path.join(home, "AGENTS.md");
  const overridePath = path.join(home, "AGENTS.override.md");
  await writeFile(normalPath, "# Normal rules\n", "utf8");
  await writeFile(overridePath, "# Override rules\n\nKeep override.\n", "utf8");

  const installedPath = await installHandoffAgent(home);
  const normal = await readFile(normalPath, "utf8");
  const override = await readFile(overridePath, "utf8");

  assert.equal(installedPath, overridePath);
  assert.equal(normal, "# Normal rules\n");
  assert.match(override, /# Override rules/);
  assert.match(override, /Keep override\./);
  assert.equal(override.split(AGENT_BLOCK_START).length - 1, 1);
});
