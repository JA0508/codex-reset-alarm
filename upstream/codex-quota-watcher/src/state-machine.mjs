const BLOCKED_STATUSES = new Set([
  "rate_limit_reached",
  "workspace_owner_credits_depleted",
  "workspace_member_credits_depleted",
  "workspace_owner_usage_limit_reached",
  "workspace_member_usage_limit_reached",
]);

const WEEK_MINUTES = 7 * 24 * 60;
const SCHEDULE_TOLERANCE_MS = 15 * 60 * 1000;
const WEEK_ROLLOVER_MIN_MS = 5 * 24 * 60 * 60 * 1000;

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeWindow(window) {
  if (!window || typeof window !== "object") return null;
  const usedPercent = finiteNumber(window.usedPercent);
  if (usedPercent === null) return null;
  return {
    usedPercent,
    resetsAt: finiteNumber(window.resetsAt),
    windowDurationMins: finiteNumber(window.windowDurationMins),
  };
}

function safeResetCredits(payload) {
  const value = finiteNumber(payload?.rateLimitResetCredits?.availableCount);
  return value === null ? null : { availableCount: Math.max(0, Math.trunc(value)) };
}

function windowsOf(snapshot) {
  return [snapshot?.primary, snapshot?.secondary].filter(Boolean);
}

export function weeklyResetAt(snapshot) {
  const weekly = windowsOf(snapshot)
    .filter((window) => window.windowDurationMins >= WEEK_MINUTES * 0.85)
    .sort((a, b) => b.windowDurationMins - a.windowDurationMins)[0];
  return weekly?.resetsAt ?? null;
}

export function normalizeRateLimits(payload, limitId = "codex", checkedAt = new Date()) {
  const byId = payload?.rateLimitsByLimitId;
  const raw = byId && typeof byId === "object" && byId[limitId]
    ? byId[limitId]
    : payload?.rateLimits;

  if (!raw || typeof raw !== "object") {
    return { status: "unknown", limitId, checkedAt: checkedAt.toISOString() };
  }

  const primary = safeWindow(raw.primary);
  const secondary = safeWindow(raw.secondary);
  const reachedType = typeof raw.rateLimitReachedType === "string" ? raw.rateLimitReachedType : null;
  const spendControlReached = raw.spendControlReached === true;
  const blockedWindows = [
    primary?.usedPercent >= 100 ? "primary" : null,
    secondary?.usedPercent >= 100 ? "secondary" : null,
  ].filter(Boolean);
  const backendBlocked = reachedType !== null && BLOCKED_STATUSES.has(reachedType);
  const hasEvidence = primary !== null || secondary !== null || backendBlocked || spendControlReached;

  if (!hasEvidence) {
    return { status: "unknown", limitId, checkedAt: checkedAt.toISOString() };
  }

  return {
    status: backendBlocked || spendControlReached || blockedWindows.length > 0 ? "blocked" : "available",
    limitId: typeof raw.limitId === "string" ? raw.limitId : limitId,
    reachedType,
    primary,
    secondary,
    blockedWindows,
    resetCredits: safeResetCredits(payload),
    checkedAt: checkedAt.toISOString(),
  };
}

function expectedBlockedResetAt(snapshot) {
  const named = snapshot?.blockedWindows ?? [];
  const times = named
    .map((name) => snapshot?.[name]?.resetsAt)
    .filter((value) => finiteNumber(value) !== null);
  return times.length ? Math.min(...times) : null;
}

function classifyRecovery(previous, now) {
  const expectedSeconds = expectedBlockedResetAt(previous);
  if (expectedSeconds === null) return "RECOVERY_CONFIRMED";
  const deltaMs = now.getTime() - expectedSeconds * 1000;
  if (Math.abs(deltaMs) <= SCHEDULE_TOLERANCE_MS || deltaMs > 0) return "SCHEDULED_RESET_CONFIRMED";
  return "EXTRA_RESET_CONFIRMED";
}

function weeklyCycleRolledOver(previous, current, now) {
  const before = weeklyResetAt(previous);
  const after = weeklyResetAt(current);
  if (before === null || after === null || after <= before) return false;
  const oldDeadlineMs = before * 1000;
  return now.getTime() >= oldDeadlineMs - SCHEDULE_TOLERANCE_MS
    && after * 1000 - oldDeadlineMs >= WEEK_ROLLOVER_MIN_MS;
}

function stateBase(previousState, currentSnapshot, officialSignal) {
  return {
    schemaVersion: 2,
    lastSnapshot: currentSnapshot,
    blockedSince: previousState?.blockedSince ?? null,
    lastEventKey: previousState?.lastEventKey ?? null,
    officialSignal: officialSignal ?? null,
  };
}

export function evaluateTransition(previousState, currentSnapshot, now = new Date(), officialSignal = null) {
  const previous = previousState?.lastSnapshot ?? null;
  const nextState = stateBase(previousState, currentSnapshot, officialSignal);
  const events = [];

  if (currentSnapshot.status === "blocked" && !nextState.blockedSince) {
    nextState.blockedSince = currentSnapshot.checkedAt;
  }

  const oldCredits = previous?.resetCredits?.availableCount;
  const newCredits = currentSnapshot?.resetCredits?.availableCount;
  if (previous && newCredits !== null && newCredits !== undefined && (oldCredits ?? 0) < newCredits) {
    events.push({
      type: "RESET_CREDIT_GRANTED",
      limitId: currentSnapshot.limitId,
      occurredAt: now.toISOString(),
      message: "An earned Codex reset is available. Your quota has not been reset automatically.",
    });
  }

  if (currentSnapshot.status === "available" && previous?.status === "blocked") {
    const type = classifyRecovery(previous, now);
    events.push({
      type,
      limitId: currentSnapshot.limitId,
      occurredAt: now.toISOString(),
      message: type === "EXTRA_RESET_CONFIRMED"
        ? "Codex quota recovered before its expected window reset."
        : type === "SCHEDULED_RESET_CONFIRMED"
          ? "Codex quota recovered at or after its expected reset time."
          : "Codex quota is available again; reset type could not be proven.",
    });
    nextState.blockedSince = null;
  } else if (previous && weeklyCycleRolledOver(previous, currentSnapshot, now)) {
    events.push({
      type: "SCHEDULED_RESET_CONFIRMED",
      limitId: currentSnapshot.limitId,
      occurredAt: now.toISOString(),
      message: "A new weekly Codex quota window has started.",
    });
  }

  if (officialSignal && previousState?.officialSignal?.detectedAt !== officialSignal.detectedAt) {
    events.push({
      type: "EXTRA_RESET_POSSIBLE",
      limitId: currentSnapshot.limitId,
      occurredAt: now.toISOString(),
      confidence: officialSignal.confidence,
      source: officialSignal.source,
      message: "An official account message indicates a possible upcoming Codex reset.",
    });
  }

  const uniqueEvents = events.filter((event) => {
    const key = `${event.type}:${event.occurredAt}:${currentSnapshot.limitId}`;
    if (previousState?.lastEventKey === key) return false;
    nextState.lastEventKey = key;
    return true;
  });

  return { event: uniqueEvents[0] ?? null, events: uniqueEvents, nextState };
}
