import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadState, saveState } from "../src/state-store.mjs";

test("persists and reloads schema 2 state atomically", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "codex-quota-watcher-"));
  const file = path.join(directory, "nested", "state.json");
  const state = { schemaVersion: 2, lastSnapshot: { status: "available" }, officialSignal: null };
  try {
    await saveState(file, state);
    assert.deepEqual(await loadState(file), state);
    assert.match(await readFile(file, "utf8"), /"schemaVersion": 2/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("migrates a V0.1 state without losing the last observation", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "codex-quota-watcher-"));
  const file = path.join(directory, "state.json");
  try {
    await saveState(file, { schemaVersion: 1, lastSnapshot: { status: "blocked" }, blockedSince: "then", lastEventKey: "old" });
    const migrated = await loadState(file);
    assert.equal(migrated.schemaVersion, 2);
    assert.equal(migrated.lastSnapshot.status, "blocked");
    assert.equal(migrated.officialSignal, null);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
