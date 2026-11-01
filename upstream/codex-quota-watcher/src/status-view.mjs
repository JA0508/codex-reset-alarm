import { weeklyResetAt } from "./state-machine.mjs";

function localeFor(language) {
  if (language === "zh") return "zh-CN";
  if (language === "en") return "en-US";
  return Intl.DateTimeFormat().resolvedOptions().locale || "en-US";
}

function isChinese(locale) {
  return locale.toLowerCase().startsWith("zh");
}

const ZH_EVENT_MESSAGES = {
  SCHEDULED_RESET_CONFIRMED: "Codex 正常额度刷新已确认。",
  EXTRA_RESET_CONFIRMED: "Codex 额度已提前恢复，额外重置已确认。",
  RECOVERY_CONFIRMED: "Codex 额度已经恢复，但无法确认重置类型。",
  RESET_CREDIT_GRANTED: "你获得了一次 Codex 重置机会；额度尚未自动重置。",
  EXTRA_RESET_POSSIBLE: "官方账户消息显示 Codex 可能即将额外重置。",
};

export function localizeEvent(event, language = "auto") {
  const locale = localeFor(language);
  if (!isChinese(locale) || !ZH_EVENT_MESSAGES[event?.type]) return event;
  return { ...event, message: ZH_EVENT_MESSAGES[event.type] };
}

function dateText(epochSeconds, locale) {
  if (!epochSeconds) return isChinese(locale) ? "未知" : "Unknown";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(epochSeconds * 1000));
}

function usageText(snapshot, zh) {
  const windows = [snapshot.primary, snapshot.secondary].filter(Boolean);
  const maximum = windows.length ? Math.max(...windows.map((item) => item.usedPercent)) : null;
  const status = snapshot.status === "blocked" ? (zh ? "受限" : "Limited") : (zh ? "可用" : "Available");
  return maximum === null ? status : `${status} · ${zh ? "最高已用" : "max used"} ${maximum}%`;
}

export function renderStatus(snapshot, state, language = "auto") {
  const locale = localeFor(language);
  const zh = isChinese(locale);
  const signal = state?.officialSignal;
  const extra = signal
    ? (zh ? `可能 · ${signal.confidence === "high" ? "高" : "低"}` : `Possible · ${signal.confidence}`)
    : (zh ? "暂无可靠信号" : "No reliable signal");
  const rows = zh
    ? [["每周刷新", dateText(weeklyResetAt(snapshot), locale)], ["额外重置", extra], ["当前状态", usageText(snapshot, true)]]
    : [["Weekly refresh", dateText(weeklyResetAt(snapshot), locale)], ["Extra reset", extra], ["Current status", usageText(snapshot, false)]];
  const title = zh ? "Codex 额度" : "Codex quota";
  const output = [title, "─".repeat(28)];
  for (const [label, value] of rows) output.push(`${label.padEnd(14)}${value}`);
  return output.join("\n");
}
