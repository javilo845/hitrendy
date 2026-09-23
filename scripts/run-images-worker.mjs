#!/usr/bin/env node
// Starts the image generation worker for `npm run dev`.
// It shares the backend's interpreter problem, so it shares the resolution:
// see scripts/lib/python.mjs.

import {
  createRunner,
  finish,
  reportNoInterpreter,
  resolveInterpreter,
} from "./lib/python.mjs";

// The worker reaches the image providers at import time, which pull in httpx
// and Pillow. Probing sqlalchemy alone would let an incomplete interpreter
// through and reproduce the silent death this launcher exists to prevent.
const REQUIRED_MODULES = ["sqlalchemy", "httpx", "PIL.Image"];
const interval = process.env.IMAGES_WORKER_INTERVAL || "3";

async function main() {
  const { exe, rejected } = resolveInterpreter(REQUIRED_MODULES);

  if (!exe) {
    reportNoInterpreter("images", REQUIRED_MODULES, rejected);
    return 1;
  }

  console.log(`[images] python: ${exe}`);

  const { run } = createRunner();

  return run(
    exe,
    ["-m", "app.images.worker", "--interval", interval],
    "images worker"
  );
}

finish(main());
