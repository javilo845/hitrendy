"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { api, type DeletionStatus } from "@/lib/api";
import {
  clearDeletionStatusToken,
  readDeletionStatusToken,
} from "@/lib/deletion-status";
import { readStoredLocale, translate, type AppLocale } from "@/lib/i18n";
import { routes } from "@/lib/routes";

type Screen =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "status"; status: DeletionStatus };

const TERMINAL: ReadonlySet<DeletionStatus> = new Set(["completed", "failed"]);

/**
 * Public tracker for an account deletion.
 *
 * It runs outside ProtectedRoute because the session is revoked the moment the
 * deletion is requested. The only credential is the opaque token held in this
 * tab's sessionStorage, which is sent as a header and never appears in the URL.
 * The screen shows the state and nothing else: no internal identifier, no
 * error detail from the purge itself.
 */
export default function AccountDeletionStatusPage() {
  const [locale] = useState<AppLocale>(readStoredLocale);
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [checking, setChecking] = useState(false);

  const t = useCallback(
    (key: string) => translate(locale, `deletionStatus.${key}`),
    [locale]
  );

  const refresh = useCallback(async () => {
    const token = readDeletionStatusToken();
    if (!token) {
      setScreen({ kind: "missing" });
      return;
    }
    setChecking(true);
    try {
      const result = await api.auth.deletionStatus(token);
      setScreen({ kind: "status", status: result.status });
      if (TERMINAL.has(result.status)) {
        // Nothing left to follow: the tracker stops being useful here.
        clearDeletionStatusToken();
      }
    } catch {
      // An unknown, expired or malformed token gets the same neutral answer:
      // the backend message would tell the caller which of them it was.
      setScreen({ kind: "invalid" });
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function close() {
    clearDeletionStatusToken();
    setScreen({ kind: "missing" });
  }

  const body =
    screen.kind === "loading"
      ? t("loading")
      : screen.kind === "missing"
        ? t("missing")
        : screen.kind === "invalid"
          ? t("invalid")
          : t(`state.${screen.status}`);

  return (
    <main className="route-status" aria-labelledby="deletion-status-title">
      <section className="auth-card">
        <div className="auth-brand">
          <Logo />
        </div>
        <h1 id="deletion-status-title">{t("title")}</h1>
        <p className="auth-description">{t("lead")}</p>
        <p role="status" aria-live="polite" data-testid="deletion-status-body">
          {body}
        </p>
        {screen.kind === "status" || screen.kind === "loading" ? (
          <button type="button" onClick={() => void refresh()} disabled={checking}>
            {checking ? t("loading") : t("refresh")}
          </button>
        ) : null}
        {screen.kind === "status" ? (
          <button type="button" onClick={close}>
            {t("close")}
          </button>
        ) : null}
        <p className="auth-register-prompt">
          <Link href={routes.home}>HiTrendy</Link>
        </p>
      </section>
    </main>
  );
}
