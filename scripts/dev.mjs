#!/usr/bin/env node
// Single entry point for `npm run dev`.
//
// The three processes are not independent. The web proxies /api/v1 to the API
// port, and after the Google callback the API sends the browser back to the web
// port. A fallback port is only usable if all three agree on it, and no
// process-runner can arrange that: each command resolves its own ports, after
// the others have already committed to theirs. So the ports are resolved once,
// here, and passed down.

import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

import { apiUrl, localhostUrl, writeRuntimePorts } from "./lib/dev-runtime.mjs";
import { claimPort } from "./lib/ports.mjs";
import { envFile, repoRoot } from "./lib/python.mjs";

// The only pair where Google sign-in completes end to end: Google has
// http://localhost:8000/api/v1/auth/google/callback registered as the redirect,
// and the callback hands the browser to http://localhost:3000.
const DEFAULT_API_PORT = 8000;
const DEFAULT_WEB_PORT = 3000;

const isWindows = process.platform === "win32";
const npm = isWindows ? "npm.cmd" : "npm";

const STYLE = {
  web: "\u001b[36m",
  api: "\u001b[35m",
  images: "\u001b[33m",
  warn: "\u001b[33m",
  reset: "\u001b[0m",
};

function readEnvFile() {
  if (!existsSync(envFile)) return {};
  const values = {};
  for (const line of readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;
    values[match[1]] = match[2].trim().replace(/^["'](.*)["']$/, "$1");
  }
  return values;
}

function warn(lines) {
  for (const line of lines) console.log(`${STYLE.warn}[dev] ${line}${STYLE.reset}`);
}

/**
 * Environment the children need to agree on the ports we actually got.
 *
 * The ports themselves are always passed down -- the web proxy has to be told
 * where the API ended up, whatever port that is. The values .env owns are a
 * different matter: on the canonical pair they are left exactly as written, and
 * only a fallback rewrites them, as far as it must and no further.
 */
function sharedEnv({ apiPort, webPort }) {
  const fileValues = readEnvFile();
  const frontendUrl = localhostUrl(webPort);
  const backendUrl = localhostUrl(apiPort, "127.0.0.1");
  const localOrigins = (fileValues.ALLOWED_ORIGINS || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(
      (origin) =>
        origin &&
        !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)
    );
  const shared = {
    HITRENDY_PORTS_RESOLVED: "1",
    BACKEND_PORT: String(apiPort),
    PORT: String(webPort),
    NEXT_PUBLIC_API_URL: apiUrl(apiPort),
    FRONTEND_URL: frontendUrl,
    ALLOWED_ORIGINS: [...new Set([...localOrigins, frontendUrl])].join(","),
  };

  if (fileValues.GOOGLE_REDIRECT_URI)
    shared.GOOGLE_REDIRECT_URI = `${backendUrl}/api/v1/auth/google/callback`;
  if (fileValues.SOCIAL_PUBLIC_BACKEND_URL)
    shared.SOCIAL_PUBLIC_BACKEND_URL = backendUrl;
  if (fileValues.INSTAGRAM_REDIRECT_URI)
    shared.INSTAGRAM_REDIRECT_URI = `${backendUrl}/api/v1/social/instagram/callback`;
  if (fileValues.PASSWORD_RESET_URL)
    shared.PASSWORD_RESET_URL = `${frontendUrl}/reset-password`;

  return shared;
}

const children = new Map();
let shuttingDown = false;

// How long a child gets to stop on its own before it is killed outright.
const SHUTDOWN_GRACE_MS = 5000;

function stopChild(child, signalName) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (isWindows) {
    // spawnSync, not spawn: a failed spawn emits an 'error' event, and an
    // unhandled one here would take the orchestrator down mid-shutdown and
    // orphan every child it had not signalled yet.
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  // Negative pid: the whole group. `npm run` execs its own children, and
  // signalling only npm leaves next-server and uvicorn holding their ports --
  // exactly the stale listeners this launcher then has to reclaim next run.
  try {
    process.kill(-child.pid, signalName);
  } catch {
    // Group already gone.
  }
}

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children.keys()) stopChild(child, "SIGTERM");

  // Pressing Ctrl-C again cannot help: the children run in their own process
  // groups, so the terminal's signal reaches this process and nothing else. If
  // SIGTERM is not enough -- a stuck migration, a request that will not close
  // -- this is the only thing left that frees the ports they hold.
  const escalation = setTimeout(() => {
    for (const child of children.keys()) stopChild(child, "SIGKILL");
  }, SHUTDOWN_GRACE_MS);
  escalation.unref();
}

// Progress output (pip, webpack) redraws a single line with \r and may never
// send a newline, so \r ends a line too. The cap is the backstop for output
// that does neither: without it a long-running spinner grows one string until
// the process runs out of memory.
const MAX_BUFFERED_CHARS = 64 * 1024;

function pipe(stream, name) {
  let buffered = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buffered += chunk;
    const lines = buffered.split(/\r\n|[\r\n]/);
    buffered = lines.pop() ?? "";
    if (buffered.length > MAX_BUFFERED_CHARS) {
      lines.push(buffered);
      buffered = "";
    }
    for (const line of lines) {
      console.log(`${STYLE[name]}[${name}]${STYLE.reset} ${line}`);
    }
  });
  stream.on("end", () => {
    if (buffered) console.log(`${STYLE[name]}[${name}]${STYLE.reset} ${buffered}`);
  });
}

function start({ name, args, env, critical }) {
  const child = spawn(npm, args, {
    cwd: repoRoot,
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
    detached: !isWindows,
  });

  children.set(child, { name, critical });
  pipe(child.stdout, name);
  pipe(child.stderr, name);

  child.on("exit", (code, signal) => {
    children.delete(child);
    if (shuttingDown) return;

    if (code === 0) {
      console.log(`${STYLE[name]}[${name}]${STYLE.reset} terminó.`);
    } else {
      warn([`${name} terminó con ${signal ? `señal ${signal}` : `código ${code}`}.`]);
    }

    // A dead API behind a live web server is what makes a broken backend look
    // like a rejected password. If something essential stops, the whole stack
    // stops, and the reason stays on screen.
    if (critical) {
      if (code !== 0) warn(["Se detiene el resto del stack."]);
      process.exitCode = code === 0 ? 0 : (code ?? 1);
      shutdown();
    } else if (code !== 0) {
      warn([`${name} no es esencial; web y api siguen corriendo.`]);
    }
  });

  return child;
}

async function main() {
  for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, shutdown);

  const api = await claimPort({ preferred: DEFAULT_API_PORT, label: "api" });
  const web = await claimPort({ preferred: DEFAULT_WEB_PORT, label: "web" });
  writeRuntimePorts({ apiPort: api.port, webPort: web.port });

  console.log(`[dev] api  -> http://127.0.0.1:${api.port}`);
  console.log(`[dev] web  -> http://localhost:${web.port}`);

  const env = sharedEnv({ apiPort: api.port, webPort: web.port });

  start({ name: "web", args: ["run", "web:dev"], env, critical: true });
  start({ name: "api", args: ["run", "backend:dev"], env, critical: true });
  start({ name: "images", args: ["run", "images:worker"], env, critical: false });
}

main().catch((error) => {
  console.error(`[dev] ${error.message}`);
  process.exitCode = 1;
  shutdown();
});
