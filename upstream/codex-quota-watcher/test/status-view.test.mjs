import assert from "node:assert/strict";
import test from "node:test";
import { localizeEvent } from "../src/status-view.mjs";

test("localizes reset notifications when Chinese is selected", () => {
  const event = localizeEvent({ type: "EXTRA_RESET_CONFIRMED", message: "English" }, "zh");
  assert.equal(event.message, "Codex 额度已提前恢复，额外重置已确认。");
});

test("preserves the original message for English", () => {
  const event = { type: "EXTRA_RESET_CONFIRMED", message: "English" };
  assert.deepEqual(localizeEvent(event, "en"), event);
});
