#!/usr/bin/env node

import { AppServerClient } from "./app-server-client.mjs";
import { dispatchNotifications } from "./notifiers.mjs";
import { normalizeRateLimits, evaluateTransition } from "./state-machine.mjs";
import { defaultStatePath, loadState, saveState } from "./state-store.mjs";
import { analyzeWorkspaceMessages } from "./evidence.mjs";
import { localizeEvent, renderStatus } from "./status-view.mjs";

function parseArgs(argv) {
  const options = {
    once: false,
    intervalSeconds: 60,
    limitId: "codex",
    channels: ["console", "desktop"],
    stateFile: defaultStatePath(),
    json: false,
    language: "auto",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--once") options.once = true;
    else if (arg === "--json") options.json = true;
    else if (arg === "--lang") options.language = argv[++index];
    else if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--interval") options.intervalSeconds = Number(argv[++index]);
    else if (arg === "--limit-id") options.limitId = argv[++index];
    else if (arg === "--notify") options.channels = argv[++index].split(",").map((value) => value.trim()).filter(Boolean);
    else if (arg === "--state-file") options.stateFile = argv[++index];
    else if (arg === "--codex-bin") options.codexBin = argv[++index];
    else throw new Error(`unknown argument: ${arg}`);
  }

  if (!Number.isFinite(options.intervalSeconds) || options.intervalSeconds < 15) {
    throw new Error("--interval must be at least 15 seconds");
  }
  if (!options.limitId) throw new Error("--limit-id cannot be empty");
  if (!["auto", "zh", "en"].includes(options.language)) throw new Error("--lang must be auto, zh, or en");
  return options;
}

function printHelp() {
  console.log(`Codex Quota Watcher 0.2.1

Usage:
  codex-quota-watcher --once [--json]
  codex-quota-watcher [--interval 60] [--notify console,desktop]

Options:
  --once              Read once, persist the baseline, and exit
  --interval SECONDS  Polling interval; minimum 15 (default: 60)
  --limit-id ID       Codex rate-limit bucket (default: codex)
  --notify CHANNELS   console, desktop, webhook (default: console,desktop)
  --state-file PATH   Override the private local state path
  --codex-bin PATH    Override the Codex executable
  --json              Print the safe normalized snapshot as JSON
  --lang LANG         Status language: auto, zh, en (default: auto)
  --help              Show this help

The watcher never reads Codex credential files and never consumes reset credits.`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  let client = null;
  let checking = false;

  const ensureClient = async () => {
    if (client) return client;
    client = new AppServerClient({ command: options.codexBin || "codex" });
    client.on("close", () => { client = null; });
    client.on("rateLimitsUpdated", () => void check());
    await client.start();
    return client;
  };

  const check = async () => {
    if (checking) return;
    checking = true;
    try {
      const activeClient = await ensureClient();
      const payload = await activeClient.readRateLimits();
      const snapshot = normalizeRateLimits(payload, options.limitId);
      if (snapshot.status === "unknown") throw new Error(`no usable '${options.limitId}' rate-limit bucket was returned`);

      let officialSignal = null;
      try {
        officialSignal = analyzeWorkspaceMessages(await activeClient.readWorkspaceMessages());
      } catch {
        // Older app-server versions may not expose workspace messages. Quota reads remain useful.
      }

      const previousState = await loadState(options.stateFile);
      const { events, nextState } = evaluateTransition(previousState, snapshot, new Date(), officialSignal);
      await saveState(options.stateFile, nextState);

      if (options.json) console.log(JSON.stringify({ snapshot, officialSignal }, null, 2));
      else if (options.once) console.log(renderStatus(snapshot, nextState, options.language));
      for (const event of events) {
        const failures = await dispatchNotifications(localizeEvent(event, options.language), options.channels);
        for (const failure of failures) console.error(`notification warning: ${failure}`);
      }
    } catch (error) {
      console.error(`watcher check failed: ${error.message}`);
      client?.close();
      client = null;
      if (options.once) process.exitCode = 1;
    } finally {
      checking = false;
    }
  };

  await check();
  if (options.once) {
    client?.close();
    return;
  }

  const timer = setInterval(() => void check(), options.intervalSeconds * 1000);
  const stop = () => {
    clearInterval(timer);
    client?.close();
    process.exit(0);
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
