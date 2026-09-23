/**
 * Opaque tracking token for an account deletion.
 *
 * The client mints the token before asking for the deletion, so a double click,
 * a network retry or a lost 202 all resolve to the same purge job. The backend
 * stores only its hash. The token lives in sessionStorage — it survives a
 * reload of the tab that requested the deletion and never travels in the URL.
 */

export const DELETION_TOKEN_KEY = "hitrendy.deletion_status_token";

/** Matches the backend contract: 43-128 chars of base64url. */
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{43,128}$/;

const TOKEN_BYTES = 32;

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** 32 cryptographically secure bytes, encoded as 43 base64url characters. */
export function createDeletionStatusToken(): string {
  const bytes = new Uint8Array(TOKEN_BYTES);
  crypto.getRandomValues(bytes);
  return toBase64Url(bytes);
}

export function isDeletionStatusToken(value: unknown): value is string {
  return typeof value === "string" && TOKEN_PATTERN.test(value);
}

export function readDeletionStatusToken(): string | null {
  if (typeof window === "undefined") return null;
  let stored: string | null = null;
  try {
    stored = window.sessionStorage.getItem(DELETION_TOKEN_KEY);
  } catch {
    // A tab with storage disabled simply has no tracker.
    return null;
  }
  return isDeletionStatusToken(stored) ? stored : null;
}

/**
 * Return the token already tracking a deletion in this tab, or mint a new one.
 * Reusing it is what makes the request idempotent across retries.
 */
export function ensureDeletionStatusToken(): string {
  const existing = readDeletionStatusToken();
  if (existing) return existing;
  const token = createDeletionStatusToken();
  try {
    window.sessionStorage.setItem(DELETION_TOKEN_KEY, token);
  } catch {
    // Without storage the tracker cannot be resumed, but the request still works.
  }
  return token;
}

export function clearDeletionStatusToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(DELETION_TOKEN_KEY);
  } catch {
    // Nothing to clean up.
  }
}
