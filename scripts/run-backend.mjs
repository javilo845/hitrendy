#!/usr/bin/env node
// Starts the backend for `npm run dev`: migrations first, then uvicorn.
// See scripts/lib/python.mjs for why the interpreter is resolved rather than
// inherited from PATH.

import { existsSync } from "node:fs";

import { apiUrl, localhostUrl, writeRuntimePorts } from "./lib/dev-runtime.mjs";
import { claimPort } from "./lib/ports.mjs";
import {
  createRunner,
  envFile,
  finish,
  reportNoInterpreter,
  resolveInterpreter,
} from "./lib/python.mjs";

// Everything `app.main` reaches at import time, not just what starts it: the
// router chain pulls in jwt (identity.google_oauth) and cryptography
// (social.crypto), so an interpreter without them passes a shallower probe,
// migrates, and only then dies on a raw ModuleNotFoundError.
const REQUIRED_MODULES = [
  "alembic",
  "uvicorn",
  "fastapi",
  "jwt",
  "cryptography",
];
// Google has http://localhost:8000/api/v1/auth/google/callback registered as
// its redirect, and .env points GOOGLE_REDIRECT_URI and
// SOCIAL_PUBLIC_BACKEND_URL at the same place. Serving anywhere else leaves
// both callbacks arriving at a port nothing is listening on.
const DEFAULT_PORT = 8000;

/**
 * The port to serve on.
 *
 * `npm run dev` resolves the API and web ports together and passes them down,
 * because the web proxy has to be told the same number. Started on its own
 * there is nobody to coordinate with, so this claims a port itself: it takes
 * back one held by a backend left over from an earlier run, and steps aside
 * for anything it did not start.
 */
async function resolvePort() {
  const preferred = Number(process.env.BACKEND_PORT) || DEFAULT_PORT;
  if (process.env.HITRENDY_PORTS_RESOLVED) return preferred;

  const { port } = await claimPort({ preferred, label: "api" });

  return port;
}

async function main() {
  const { exe, rejected } = resolveInterpreter(REQUIRED_MODULES);

  if (!exe) {
    reportNoInterpreter("backend", REQUIRED_MODULES, rejected);
    return 1;
  }

  console.log(`[backend] python: ${exe}`);

  if (!existsSync(envFile)) {
    console.error("\n[backend] .env is missing at the repository root:\n");
    console.error("    cp .env.example .env\n");
    return 1;
  }

  const port = await resolvePort();
  const runtime = writeRuntimePorts({ apiPort: port });
  const webPort = Number(process.env.PORT) || runtime.webPort || 3000;
  const backendUrl = localhostUrl(port, "127.0.0.1");
  const frontendUrl = localhostUrl(webPort);

  Object.assign(process.env, {
    BACKEND_PORT: String(port),
    FRONTEND_URL: frontendUrl,
    ALLOWED_ORIGINS: frontendUrl,
    NEXT_PUBLIC_API_URL: apiUrl(port),
  });
  if (process.env.GOOGLE_REDIRECT_URI)
    process.env.GOOGLE_REDIRECT_URI = `${backendUrl}/api/v1/auth/google/callback`;
  if (process.env.SOCIAL_PUBLIC_BACKEND_URL)
    process.env.SOCIAL_PUBLIC_BACKEND_URL = backendUrl;
  if (process.env.INSTAGRAM_REDIRECT_URI)
    process.env.INSTAGRAM_REDIRECT_URI = `${backendUrl}/api/v1/social/instagram/callback`;
  if (process.env.PASSWORD_RESET_URL)
    process.env.PASSWORD_RESET_URL = `${frontendUrl}/reset-password`;
  const { run, state } = createRunner();

  const migration = await run(
    exe,
    ["-m", "alembic", "upgrade", "head"],
    "alembic"
  );

  if (state.stopping) return 0;

  if (migration !== 0) {
    console.error(
      `\n[backend] Migrations failed (exit ${migration}). The API was not started.`
    );
    console.error(
      "[backend] A refused connection on port 5432 means Postgres is down:\n"
    );
    console.error("    docker compose up -d postgres\n");
    return migration;
  }

  return run(
    exe,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--reload",
      "--port",
      String(port),
      "--env-file",
      envFile,
    ],
    "uvicorn"
  );
}

finish(main());
