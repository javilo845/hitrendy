"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { RouteSplash } from "@/components/auth/route-splash";
import { api, ApiError } from "@/lib/api";
import { loginPath, routes } from "@/lib/routes";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<"checking" | "ready" | "error">(
    "checking"
  );

  useEffect(() => {
    let active = true;

    async function check() {
      try {
        await api.auth.me();
        if (active) setState("ready");
        return;
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) {
          if (active) setState("error");
          return;
        }
      }

      try {
        await api.auth.signup.get();
        if (active) router.replace(routes.onboarding);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && [404, 410].includes(error.status)) {
          router.replace(loginPath(pathname));
        } else {
          setState("error");
        }
      }
    }

    void check();

    return () => {
      active = false;
    };
  }, [pathname, router]);

  if (state === "checking") {
    return <RouteSplash />;
  }

  if (state === "error") {
    return (
      <RouteSplash tone="error">
        No pudimos comprobar tu sesión. Actualiza la página para intentarlo de
        nuevo.
      </RouteSplash>
    );
  }

  return <>{children}</>;
}
