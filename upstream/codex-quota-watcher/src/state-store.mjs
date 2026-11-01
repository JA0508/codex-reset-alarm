import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export function defaultStatePath() {
  if (process.platform === "win32") {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    return path.join(base, "codex-quota-watcher", "state.json");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "codex-quota-watcher", "state.json");
  }
  return path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"), "codex-quota-watcher", "state.json");
}

export async function loadState(filePath) {
  try {
    const parsed = JSON.parse(await readFile(filePath, "utf8"));
    if (parsed?.schemaVersion === 2) return parsed;
    if (parsed?.schemaVersion === 1) {
      return {
        schemaVersion: 2,
        lastSnapshot: parsed.lastSnapshot ?? null,
        blockedSince: parsed.blockedSince ?? null,
        lastEventKey: parsed.lastEventKey ?? null,
        officialSignal: null,
      };
    }
    return null;
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

export async function saveState(filePath, state) {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  await rename(temporary, filePath);
}
