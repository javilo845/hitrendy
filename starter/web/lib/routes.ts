export const routes = {
  home: "/",
  login: "/login",
  register: "/register",
  resetPassword: "/reset-password",
  privacy: "/privacy",
  terms: "/terms",
  feedback: "/feedback",
  onboarding: "/onboarding",
  dashboard: "/dashboard",
  trends: "/trends",
  templates: "/templates",
  library: "/library",
  studioNew: "/studio/new",
  settings: "/settings",
  // Public on purpose: it is reached after the session has been revoked.
  accountDeletionStatus: "/account-deletion-status",
} as const;

const protectedExactPaths = new Set<string>([
  routes.dashboard,
  routes.trends,
  routes.templates,
  routes.studioNew,
  routes.settings,
  routes.feedback,
]);

export function isSafeNextPath(
  value: string | null | undefined
): value is string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return false;

  if (protectedExactPaths.has(value)) return true;

  return (
    /^\/studio\/[A-Za-z0-9_-]+$/.test(value) ||
    /^\/projects\/[A-Za-z0-9_-]+$/.test(value)
  );
}

export function loginPath(next: string): string {
  return `${routes.login}?next=${encodeURIComponent(next)}`;
}

export function resolveNextPath(value: string | null | undefined): string {
  return isSafeNextPath(value) ? value : routes.dashboard;
}
