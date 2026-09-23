"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Logo } from "@/components/brand/logo";

/**
 * A session check usually resolves in a few milliseconds. Showing anything at
 * all in that window reads as a flash, so the splash stays invisible until the
 * wait is long enough to be worth explaining — and when it does appear it is
 * the dark shell the app already uses, never a blank white page.
 */
const REVEAL_DELAY_MS = 400;

export function RouteSplash({
  label = "Preparando tu espacio…",
  tone = "loading",
  children,
}: {
  label?: string;
  tone?: "loading" | "error";
  children?: ReactNode;
}) {
  const [visible, setVisible] = useState(tone === "error");

  useEffect(() => {
    if (tone === "error") return;
    const timer = window.setTimeout(() => setVisible(true), REVEAL_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [tone]);

  return (
    <main
      className="route-splash"
      data-theme="dark-shell"
      data-tone={tone}
      data-visible={visible || undefined}
      role={tone === "error" ? "alert" : "status"}
      aria-busy={tone === "loading" || undefined}
    >
      <div className="route-splash-inner">
        <Logo inverse />
        {tone === "loading" ? (
          <div className="route-splash-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        <p className="route-splash-label">{children || label}</p>
      </div>
    </main>
  );
}
