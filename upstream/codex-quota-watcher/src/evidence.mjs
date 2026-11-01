const SUBJECT = /\b(codex|quota|rate[ -]?limit|usage[ -]?limit)\b/i;
const RESET = /\b(reset|refresh|restore|replenish|renew)\w*\b/i;
const FUTURE = /\b(will|soon|upcoming|scheduled|expect(?:ed)?|next|within|in\s+\d+\s+(?:minute|hour|day)s?)\b/i;
const NEGATED = /\b(no|not|won't|will not|cancel(?:led|ed)?|without)\b.{0,24}\b(reset|refresh|restore|replenish|renew)\w*\b/i;

function messageText(message) {
  if (!message || typeof message !== "object") return "";
  return [message.messageBody, message.title, message.headline]
    .filter((value) => typeof value === "string")
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

export function classifyOfficialResetIntent(text) {
  if (typeof text !== "string" || !SUBJECT.test(text) || !RESET.test(text)) return null;
  if (NEGATED.test(text) || !FUTURE.test(text)) return null;
  return {
    kind: "possible_extra_reset",
    confidence: "high",
    source: "official_account_message",
  };
}

export function analyzeWorkspaceMessages(payload, detectedAt = new Date()) {
  if (payload?.featureEnabled !== true || !Array.isArray(payload.messages)) return null;
  for (const message of payload.messages) {
    const signal = classifyOfficialResetIntent(messageText(message));
    if (signal) {
      const timestamp = typeof message.createdAt === "number"
        ? new Date(message.createdAt * 1000)
        : detectedAt;
      return { ...signal, detectedAt: timestamp.toISOString() };
    }
  }
  return null;
}
