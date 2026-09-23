// Shared interpreter resolution for the Python processes `npm run dev` starts.
//
// The npm scripts used to call a bare `python`, which resolves to whatever is
// on PATH. Outside an activated virtualenv that is the system interpreter,
// which has none of the backend dependencies, so those processes died on their
// first command while the rest of the stack carried on. Nothing surfaced the
// failure, so the web app kept serving a sign-in form with no API behind it.
// Resolving deliberately, and refusing to start quietly, is the point.

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  ".."
);
export const backendDir = path.join(repoRoot, "starter", "backend");
export const webDir = path.join(repoRoot, "starter", "web");
export const envFile = path.join(repoRoot, ".env");

function venvInterpreter() {
  const relative =
    process.platform === "win32"
      ? path.join(".venv", "Scripts", "python.exe")
      : path.join(".venv", "bin", "python");
  const candidate = path.join(repoRoot, relative);
  return existsSync(candidate) ? candidate : null;
}

// Ordered by how explicit the choice is: an operator override wins, then the
// venv this repository documents, then whatever PATH happens to offer.
function candidates() {
  const ordered = [
    process.env.PYTHON,
    venvInterpreter(),
    process.platform === "win32" ? "python" : "python3",
    "python",
  ];
  return [...new Set(ordered.filter(Boolean))];
}

/**
 * Returns `{ exe }` for the first interpreter that can import every module in
 * `required`, or `{ rejected }` describing why each candidate was unusable.
 *
 * Importing is the only proof that an interpreter can run this code. Presence
 * on disk is not enough: a stale venv passes that test and still dies.
 */
export function resolveInterpreter(required) {
  const rejected = [];

  for (const exe of candidates()) {
    const probe = spawnSync(exe, ["-c", `import ${required.join(", ")}`], {
      encoding: "utf8",
    });

    if (probe.status === 0) return { exe };

    const detail = probe.error
      ? probe.error.code === "ENOENT"
        ? "not found"
        : probe.error.message
      : (probe.stderr || "").trim().split("\n").pop() || "import failed";
    rejected.push({ exe, detail });
  }

  return { rejected };
}

export function reportNoInterpreter(label, required, rejected) {
  console.error(`\n[${label}] No usable Python interpreter found.\n`);
  console.error(`[${label}] Needs to import: ${required.join(", ")}.\n`);

  for (const { exe, detail } of rejected) {
    console.error(`  - ${exe}: ${detail}`);
  }

  const activate =
    process.platform === "win32"
      ? ".venv\\Scripts\\activate"
      : "source .venv/bin/activate";

  console.error("\nCreate and populate the virtualenv:\n");
  console.error("    python3 -m venv .venv");
  console.error(`    ${activate}`);
  console.error(
    "    python -m pip install -r starter/backend/requirements-dev.txt\n"
  );
  console.error("Or set PYTHON to an interpreter that already has them.\n");
}

/**
 * Runs a child in the backend package, forwarding stop signals so Ctrl-C in a
 * `concurrently` stack still shuts the process down cleanly.
 */
export function createRunner() {
  let child = null;
  const state = { stopping: false };

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
      state.stopping = true;
      if (child) child.kill(signal);
    });
  }

  function run(exe, args, label) {
    return new Promise((resolve, reject) => {
      child = spawn(exe, args, { cwd: backendDir, stdio: "inherit" });
      child.on("error", (error) =>
        reject(new Error(`could not run ${label}: ${error.message}`))
      );
      child.on("exit", (code, signal) => {
        child = null;
        // Only a stop we forwarded is clean. A child killed by anything else --
        // the OOM killer, an external kill -- has not done its work, and
        // reporting that as success would let the caller continue past a step
        // that never finished.
        if (signal) {
          resolve(state.stopping ? 0 : 1);
          return;
        }
        resolve(code ?? 1);
      });
    });
  }

  return { run, state };
}

export function finish(promise) {
  promise.then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      console.error(error.message);
      process.exitCode = 1;
    }
  );
}
