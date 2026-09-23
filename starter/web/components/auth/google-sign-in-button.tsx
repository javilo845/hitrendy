"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { surfaceCopy, useInterfaceLocale } from "@/lib/i18n";

type GoogleButtonState = "checking" | "ready" | "unavailable" | "starting";

export function GoogleSignInButton() {
  const [state, setState] = useState<GoogleButtonState>("checking");
  const [error, setError] = useState("");
  const copy = surfaceCopy[useInterfaceLocale()].auth;

  useEffect(() => {
    let active = true;
    void api.auth.google
      .status()
      .then((status) => {
        if (active) setState(status.configured ? "ready" : "unavailable");
      })
      .catch(() => {
        if (active) setState("unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  async function startGoogleSignIn() {
    if (state !== "ready") return;
    setError("");
    setState("starting");
    try {
      const { authorization_url } = await api.auth.google.start();
      window.location.assign(authorization_url);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : copy.googleFallback
      );
      setState("ready");
    }
  }

  const unavailable = state === "unavailable";
  const starting = state === "starting";

  return (
    <div className="google-sign-in">
      <button
        type="button"
        className="google-sign-in__button"
        onClick={startGoogleSignIn}
        disabled={state === "checking" || unavailable || starting}
        aria-busy={starting}
      >
        <span aria-hidden="true" className="google-sign-in__mark">
          G
        </span>
        {starting
          ? copy.googleOpening
          : state === "checking"
            ? copy.googleChecking
            : copy.googleContinue}
      </button>
      {unavailable ? (
        <p className="google-sign-in__hint">{copy.googleUnavailable}</p>
      ) : null}
      {error ? (
        <p role="alert" className="auth-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
