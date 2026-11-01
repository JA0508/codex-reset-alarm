import { spawn } from "node:child_process";

function runDetached(command, args) {
  const child = spawn(command, args, { detached: true, stdio: "ignore", windowsHide: true });
  child.unref();
}

function powershellEncoded(script) {
  return Buffer.from(script, "utf16le").toString("base64");
}

export async function notifyDesktop(event) {
  const title = "Codex Quota Watcher";
  const body = event.message;

  if (process.platform === "win32") {
    const xmlTitle = title.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    const xmlBody = body.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    const script = [
      "$ErrorActionPreference='Stop'",
      "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null",
      "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null",
      `$xml = New-Object Windows.Data.Xml.Dom.XmlDocument`,
      `$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>${xmlTitle}</text><text>${xmlBody}</text></binding></visual></toast>')`,
      "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)",
      "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Codex Quota Watcher').Show($toast)",
    ].join(";");
    runDetached("powershell.exe", ["-NoProfile", "-NonInteractive", "-EncodedCommand", powershellEncoded(script)]);
    return;
  }

  if (process.platform === "darwin") {
    runDetached("osascript", ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run", title, body]);
    return;
  }

  runDetached("notify-send", [title, body]);
}

export async function notifyWebhook(event, url = process.env.CODEX_QUOTA_WATCHER_WEBHOOK_URL) {
  if (!url) throw new Error("CODEX_QUOTA_WATCHER_WEBHOOK_URL is not set");
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source: "codex-quota-watcher",
      type: event.type,
      limitId: event.limitId,
      occurredAt: event.occurredAt,
      confidence: event.confidence,
      source: event.source,
      message: event.message,
    }),
  });
  if (!response.ok) throw new Error(`webhook returned HTTP ${response.status}`);
}

export async function dispatchNotifications(event, channels, output = console.log) {
  const failures = [];
  for (const channel of channels) {
    try {
      if (channel === "console") output(`[${event.type}] ${event.message}`);
      else if (channel === "desktop") await notifyDesktop(event);
      else if (channel === "webhook") await notifyWebhook(event);
      else failures.push(`unknown notification channel: ${channel}`);
    } catch (error) {
      failures.push(`${channel}: ${error.message}`);
    }
  }
  return failures;
}
