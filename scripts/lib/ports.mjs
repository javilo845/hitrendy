// Port claiming for the processes `npm run dev` starts.
//
// The three ports in this stack are not interchangeable. Google registers
// http://localhost:8000/api/v1/auth/google/callback as the OAuth redirect, and
// after the callback the backend sends the browser to FRONTEND_URL. So 8000
// and 3000 are the only pair where Google sign-in completes end to end.
// Falling back to 8001/3001 keeps the app usable but breaks that one flow,
// which is why a fallback is announced loudly instead of applied quietly.
//
// A listener left behind by a previous `npm run dev` is ours to reclaim: it is
// the same code, in the same checkout, that we are about to start again.
// Anything else holding the port belongs to another project and is never
// killed -- reclaiming a port must not cost someone their other dev server.

import { spawnSync } from "node:child_process";
import { readFileSync, readlinkSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";

import { backendDir, repoRoot, webDir } from "./python.mjs";

const isWindows = process.platform === "win32";
const isLinux = process.platform === "linux";

// The two packages `npm run dev` launches. Deliberately not the repository
// root: `make demo` runs a second uvicorn out of demo/, and that one is a
// different application that happens to share a checkout.
const OWN_WORKDIRS = [backendDir, webDir];

// The interpreter our Python processes run under. Used as evidence on its own,
// so it has to be a path nothing else in a dev shell resolves to.
const venvDir = path.join(repoRoot, ".venv");

// Command lines we start. `app.main:app` rather than a bare `uvicorn` for the
// same reason -- the demo server is `app:app`, and must not match.
const OWN_SIGNATURES = [
  "app.main:app",
  "app.images.worker",
  "next-server",
  "next dev",
  "next/dist/bin/next",
];

const KILL_GRACE_MS = 4000;
const KILL_POLL_MS = 150;

function capture(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.error || result.status !== 0) return "";
  return result.stdout || "";
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * True when nothing is listening on `port`.
 *
 * Binding is the only honest test. Parsing `ss` output would also miss the
 * case that matters most here -- a socket in TIME_WAIT, or one held by a
 * process we cannot see -- and report a port as free that we cannot take.
 * The bind is on 0.0.0.0 deliberately: it collides with a loopback-only
 * listener too, which is exactly how uvicorn binds.
 */
export function portIsFree(port) {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once("error", () => resolve(false));
    probe.once("listening", () => probe.close(() => resolve(true)));
    probe.listen(port, "0.0.0.0");
  });
}

function listeningPids(port) {
  if (isWindows) {
    const pids = [];
    for (const line of capture("netstat", ["-ano", "-p", "TCP"]).split(/\r?\n/)) {
      const columns = line.trim().split(/\s+/);
      if (columns.length < 5 || columns[3] !== "LISTENING") continue;
      if (!columns[1].endsWith(`:${port}`)) continue;
      const pid = Number(columns[4]);
      if (Number.isInteger(pid) && pid > 0) pids.push(pid);
    }
    return [...new Set(pids)];
  }

  const fromSs = [];
  for (const line of capture("ss", ["-tlnpH"]).split(/\r?\n/)) {
    const columns = line.trim().split(/\s+/);
    // State Recv-Q Send-Q Local:Port Peer:Port users:(("name",pid=N,fd=M))
    if (columns.length < 4 || !columns[3].endsWith(`:${port}`)) continue;
    for (const match of line.matchAll(/pid=(\d+)/g)) fromSs.push(Number(match[1]));
  }
  if (fromSs.length) return [...new Set(fromSs)];

  // macOS has no `ss`, and `ss` hides pids owned by other users.
  const fromLsof = capture("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"])
    .split(/\s+/)
    .filter(Boolean)
    .map(Number)
    .filter((pid) => Number.isInteger(pid) && pid > 0);
  return [...new Set(fromLsof)];
}

function commandOf(pid) {
  if (isWindows) {
    return capture("powershell", [
      "-NoProfile",
      "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`,
    ]).trim();
  }
  if (isLinux) {
    try {
      return readFileSync(`/proc/${pid}/cmdline`, "utf8").replace(/\0/g, " ").trim();
    } catch {
      // Vanished, or owned by another user. `ps` may still answer.
    }
  }
  return capture("ps", ["-p", String(pid), "-o", "args="]).trim();
}

function cwdOf(pid) {
  if (isLinux) {
    try {
      return readlinkSync(`/proc/${pid}/cwd`);
    } catch {
      return "";
    }
  }
  if (isWindows) return "";
  const listed = capture("lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"]);
  const line = listed.split(/\r?\n/).find((entry) => entry.startsWith("n"));
  return line ? line.slice(1) : "";
}

/**
 * Describes every process listening on `port`.
 *
 * There is usually more than one. `uvicorn --reload` keeps a reloader parent
 * and a worker child on the same socket, and killing only the child hands the
 * port straight back to the parent, which respawns it.
 */
export function holdersOf(port) {
  return listeningPids(port).map((pid) => ({
    pid,
    command: commandOf(pid),
    cwd: cwdOf(pid),
  }));
}

function isInside(parent, candidate) {
  if (!candidate) return false;
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/** The program being run: argv[0], quoted on Windows. */
function executableOf(command) {
  const trimmed = (command || "").trim();
  const quoted = trimmed.match(/^"([^"]+)"/);
  return quoted ? quoted[1] : trimmed.split(/\s+/)[0] || "";
}

/**
 * True only for a process this checkout started.
 *
 * Recognising the command line is the main test, and it still needs tying to
 * this checkout: a sibling clone runs the same uvicorn. The second branch
 * exists for one process that cannot be recognised -- uvicorn's reload worker
 * re-execs as `python -c from multiprocessing...` -- and identifies it by the
 * interpreter it runs under.
 *
 * That interpreter has to be the venv itself, not merely a path under the
 * repository. npm puts node_modules/.bin on PATH, so any locally installed
 * tool a developer starts here carries a repository path in its arguments;
 * accepting that as evidence would hand `npx <anything>` a death sentence for
 * sharing a port. When nothing can be read at all -- another user's process,
 * or Windows, where a process's cwd is not exposed -- the answer is no.
 */
export function isOwnProcess(holder) {
  if (!holder) return false;
  const { command = "", cwd = "" } = holder;

  const rootedCwd = OWN_WORKDIRS.some((dir) => isInside(dir, cwd));
  const named = OWN_SIGNATURES.some((signature) =>
    command.toLowerCase().includes(signature.toLowerCase())
  );

  if (named) return rootedCwd || command.includes(repoRoot);
  return rootedCwd && isInside(venvDir, executableOf(command));
}

async function freedWithin(port, deadlineMs) {
  const deadline = Date.now() + deadlineMs;
  while (Date.now() < deadline) {
    if (await portIsFree(port)) return true;
    await sleep(KILL_POLL_MS);
  }
  return portIsFree(port);
}

function signal(pid, name) {
  try {
    process.kill(pid, name);
  } catch {
    // Exited between the scan and now, or is not ours to signal. Whether the
    // port actually came free is decided by binding it, not by this call.
  }
}

// Every listener at once. Signalling them one at a time lets a reload parent
// notice its worker died and start a replacement on the socket we are trying
// to take.
async function reclaim(port, pids, log) {
  if (isWindows) {
    for (const pid of pids) {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    }
    return freedWithin(port, KILL_GRACE_MS);
  }

  for (const pid of pids) signal(pid, "SIGTERM");
  if (await freedWithin(port, KILL_GRACE_MS)) return true;

  log(`[dev]   ${pids.join(", ")} ignoró SIGTERM, enviando SIGKILL.`);
  for (const pid of pids) signal(pid, "SIGKILL");
  return freedWithin(port, KILL_GRACE_MS);
}

function summarize(command) {
  const trimmed = (command || "").replace(/\s+/g, " ").trim();
  if (!trimmed) return "proceso desconocido";
  return trimmed.length > 70 ? `${trimmed.slice(0, 69)}…` : trimmed;
}

/**
 * Returns the first usable port at or after `preferred`, reclaiming it from a
 * stale process of our own when necessary.
 *
 * `span` bounds the search so a machine with a wide block of busy ports fails
 * with an explanation instead of scanning forever.
 */
export async function claimPort({ preferred, span = 10, label, log = console.log }) {
  for (let candidate = preferred; candidate < preferred + span; candidate += 1) {
    if (await portIsFree(candidate)) {
      return { port: candidate, reclaimed: false };
    }

    const holders = holdersOf(candidate);

    if (!holders.length) {
      log(`[dev] ${label}: ${candidate} ocupado, sin poder identificar por quién. Se omite.`);
      continue;
    }

    for (const holder of holders) {
      log(`[dev] ${label}: ${candidate} ocupado por PID ${holder.pid} (${summarize(holder.command)}).`);
    }

    // One unrecognised listener is enough to leave the whole port alone. A
    // socket shared with something we did not start is not ours to clear.
    if (!holders.every(isOwnProcess)) {
      log("[dev]   No es de este proyecto, no se toca.");
      continue;
    }

    log("[dev]   Es de este proyecto, se termina para reclamar el puerto.");

    if (await reclaim(candidate, holders.map((holder) => holder.pid), log)) {
      return { port: candidate, reclaimed: true };
    }

    log(`[dev]   No se pudo liberar ${candidate}.`);
  }

  throw new Error(
    `${label}: no hay ningún puerto libre entre ${preferred} y ${preferred + span - 1}.`
  );
}
