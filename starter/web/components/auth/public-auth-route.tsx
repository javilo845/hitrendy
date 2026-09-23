"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { RouteSplash } from "@/components/auth/route-splash";
import { api, ApiError } from "@/lib/api";
import { resolveNextPath, routes } from "@/lib/routes";

type RouteState = "checking" | "ready";

/**
 * What to do when the browser still carries an unfinished registration.
 *
 * `resume` sends the visitor back into the wizard, which is what `/register`
 * wants: starting the same registration twice is rejected by the backend.
 * `notice` keeps the page and only offers the way back, which is what every
 * page an existing account holder needs — sign in, password reset — requires.
 */
type PendingSignupBehavior = "resume" | "notice";

function isExpectedUnauthenticated(error: unknown) {
  return error instanceof ApiError && error.status === 401;
}

/**
 * Where an already-signed-in visitor belongs.
 *
 * ProtectedRoute sends anyone it cannot verify to `/login?next=<page>`, so a
 * session that turns out to be valid after all has to be handed back to the
 * page that was asked for. Sending everyone to the dashboard instead made any
 * bounce through here look like the app refusing to open the page.
 *
 * Read from `window` rather than `useSearchParams` on purpose: this component
 * also wraps /register and /reset-password, and that hook would force a
 * Suspense boundary into both. The effect this serves is client-only.
 */
function requestedDestination() {
  if (typeof window === "undefined") return routes.dashboard;
  return resolveNextPath(new URLSearchParams(window.location.search).get("next"));
}

export function PublicAuthRoute({
  children,
  onPendingSignup = "resume",
}: {
  children: ReactNode;
  onPendingSignup?: PendingSignupBehavior;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<RouteState>("checking");
  const [resumeSignup, setResumeSignup] = useState(false);
  const [unreachable, setUnreachable] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;

    async function check() {
      try {
        await api.auth.me();
        if (active) router.replace(requestedDestination());
        return;
      } catch (error) {
        // These pages guard nothing, so they fail open on purpose: when the
        // session check itself breaks -- API down, proxy error, no network --
        // the useful answer is the form, not a dead end the visitor cannot
        // leave. Only a clean 401 is knowledge; anything else is ignorance.
        if (!isExpectedUnauthenticated(error)) {
          // Failing open must not mean failing silently. Without this the
          // page is indistinguishable from a healthy one, so a dead API
          // reads as a rejected password and the visitor retypes forever.
          if (active) {
            setUnreachable(true);
            setState("ready");
          }
          return;
        }
        // A clean 401 proves the API answered, so any earlier warning is stale.
        if (active) setUnreachable(false);
      }

      try {
        await api.auth.signup.get();
        if (!active) return;
        if (onPendingSignup === "resume") {
          router.replace(routes.onboarding);
          return;
        }
        // An abandoned draft is an offer, never a detour: the signup cookie
        // lives for a day, and redirecting on it would lock the account holder
        // out of sign-in for exactly that long.
        setResumeSignup(true);
        setState("ready");
      } catch {
        if (active) setState("ready");
      }
    }

    void check();
    return () => {
      active = false;
    };
  }, [attempt, onPendingSignup, pathname, router]);

  if (state === "checking") {
    return <RouteSplash />;
  }

  return (
    <>
      {unreachable ? (
        <div className="route-notice" role="alert">
          <span>No pudimos contactar con el servidor.</span>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Reintentar
          </button>
        </div>
      ) : null}
      {resumeSignup ? (
        <div className="route-resume" role="status">
          <span>Tienes un registro sin terminar.</span>
          <Link href={routes.onboarding}>Continuar registro</Link>
        </div>
      ) : null}
      {children}
    </>
  );
}
