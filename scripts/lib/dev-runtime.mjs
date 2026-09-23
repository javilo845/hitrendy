// Shared hand-off for developers that run the API and web in separate shells.
// The normal `npm run dev` path passes these values directly through env.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { repoRoot } from "./python.mjs";

export const runtimeFile = path.join(repoRoot, ".hitrendy-dev-ports.json");

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function readRuntimePorts() {
  if (!existsSync(runtimeFile)) return {};

  try {
    const value = JSON.parse(readFileSync(runtimeFile, "utf8"));
    if (!processIsAlive(Number(value.ownerPid))) return {};

    return {
      apiPort: Number.isInteger(value.apiPort) ? value.apiPort : undefined,
      webPort: Number.isInteger(value.webPort) ? value.webPort : undefined,
    };
  } catch {
    return {};
  }
}

export function writeRuntimePorts(ports) {
  const current = readRuntimePorts();
  const next = {
    apiPort: ports.apiPort ?? current.apiPort,
    webPort: ports.webPort ?? current.webPort,
    ownerPid: process.pid,
  };

  writeFileSync(runtimeFile, `${JSON.stringify(next)}\n`, "utf8");
  return next;
}

export function localhostUrl(port, host = "localhost") {
  return `http://${host}:${port}`;
}

export function apiUrl(port) {
  return `${localhostUrl(port, "127.0.0.1")}/api/v1`;
}
