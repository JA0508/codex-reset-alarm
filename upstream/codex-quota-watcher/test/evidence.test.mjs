import assert from "node:assert/strict";
import test from "node:test";
import { analyzeWorkspaceMessages, classifyOfficialResetIntent } from "../src/evidence.mjs";

test("accepts explicit future Codex reset language", () => {
  assert.deepEqual(classifyOfficialResetIntent("Codex quota will reset within 1 hour"), {
    kind: "possible_extra_reset",
    confidence: "high",
    source: "official_account_message",
  });
});

test("rejects negation, unrelated messages, and past-tense ambiguity", () => {
  assert.equal(classifyOfficialResetIntent("Codex quota will not reset today"), null);
  assert.equal(classifyOfficialResetIntent("Workspace maintenance starts soon"), null);
  assert.equal(classifyOfficialResetIntent("Codex quota reset"), null);
});

test("uses official message creation time as a stable deduplication time", () => {
  const signal = analyzeWorkspaceMessages({
    featureEnabled: true,
    messages: [{ messageBody: "Codex usage limit will reset soon", createdAt: 1_781_395_200 }],
  }, new Date("2030-01-01T00:00:00Z"));
  assert.equal(signal.detectedAt, new Date(1_781_395_200_000).toISOString());
});
