import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import readline from "node:readline";

export class AppServerError extends Error {}

export class AppServerClient extends EventEmitter {
  constructor({ command = "codex", timeoutMs = 15_000 } = {}) {
    super();
    this.command = command;
    this.timeoutMs = timeoutMs;
    this.process = null;
    this.pending = new Map();
    this.nextId = 1;
    this.stderrTail = "";
  }

  async start() {
    if (this.process) return;

    const useWindowsShim = process.platform === "win32" && this.command === "codex";
    const executable = useWindowsShim ? (process.env.ComSpec || "cmd.exe") : this.command;
    const args = useWindowsShim
      ? ["/d", "/s", "/c", "codex.cmd app-server --listen stdio://"]
      : ["app-server", "--listen", "stdio://"];

    this.process = spawn(executable, args, {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    this.process.once("error", (error) => this.#failAll(error));
    this.process.once("exit", (code, signal) => {
      const detail = this.stderrTail.trim();
      const suffix = detail ? `: ${detail}` : "";
      this.#failAll(new AppServerError(`codex app-server exited (${code ?? signal})${suffix}`));
      this.process = null;
      this.emit("close");
    });

    this.process.stderr.on("data", (chunk) => {
      this.stderrTail = `${this.stderrTail}${chunk.toString("utf8")}`.slice(-4096);
    });

    const lines = readline.createInterface({ input: this.process.stdout });
    lines.on("line", (line) => this.#handleLine(line));

    await this.request("initialize", {
      clientInfo: {
        name: "codex_quota_watcher",
        title: "Codex Quota Watcher",
        version: "0.2.1",
      },
    });
    this.notify("initialized", {});
  }

  async readRateLimits() {
    await this.start();
    return this.request("account/rateLimits/read");
  }

  async readWorkspaceMessages() {
    await this.start();
    return this.request("account/workspaceMessages/read");
  }

  request(method, params) {
    if (!this.process?.stdin?.writable) {
      return Promise.reject(new AppServerError("codex app-server is not writable"));
    }

    const id = this.nextId++;
    const message = params === undefined ? { method, id } : { method, id, params };

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new AppServerError(`${method} timed out after ${this.timeoutMs}ms`));
      }, this.timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      this.process.stdin.write(`${JSON.stringify(message)}\n`);
    });
  }

  notify(method, params = {}) {
    if (!this.process?.stdin?.writable) return;
    this.process.stdin.write(`${JSON.stringify({ method, params })}\n`);
  }

  close() {
    if (!this.process) return;
    this.process.stdin.end();
    this.process.kill();
    this.process = null;
  }

  #handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }

    if (message.id !== undefined && this.pending.has(message.id)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new AppServerError(message.error.message || "app-server request failed"));
      } else {
        pending.resolve(message.result);
      }
      return;
    }

    if (message.method === "account/rateLimits/updated") {
      this.emit("rateLimitsUpdated");
    }
  }

  #failAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }
}
