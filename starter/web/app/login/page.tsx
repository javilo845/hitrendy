"use client";

import Link from "next/link";
import Image from "next/image";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { PasswordField } from "@/components/auth/password-field";
import { PublicAuthRoute } from "@/components/auth/public-auth-route";
import { RouteSplash } from "@/components/auth/route-splash";
import { api, ApiError } from "@/lib/api";
import { resolveNextPath, routes } from "@/lib/routes";
import { surfaceCopy, useInterfaceLocale } from "@/lib/i18n";

/**
 * "Recordarme" only remembers the address on this device. Session lifetime is
 * owned by the backend cookie, which takes no duration argument, so nothing
 * here changes the authentication contract.
 */
const REMEMBERED_EMAIL_KEY = "hitrendy:remember-email";

function LoginForm() {
  const router = useRouter();
  const copy = surfaceCopy[useInterfaceLocale()].auth;
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const next = resolveNextPath(searchParams.get("next"));
  const oauthError = {
    cancelled: "Cancelaste el acceso con Google. Puedes intentarlo de nuevo.",
    invalid_state:
      "La verificación con Google no pudo completarse. Inténtalo de nuevo.",
    expired_state: "La verificación con Google expiró. Inténtalo de nuevo.",
    used_state: "Este acceso con Google ya fue utilizado. Inténtalo de nuevo.",
    unavailable: "Google no está disponible en este momento.",
    account_exists:
      "Ya existe una cuenta con este correo. Inicia sesión con tu método habitual.",
    failed: "No pudimos completar el acceso con Google. Inténtalo de nuevo.",
  }[searchParams.get("oauth") || ""];

  // Hydrated after mount so the server-rendered markup stays identical.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(REMEMBERED_EMAIL_KEY);
      if (stored) {
        setEmail(stored);
        setRemember(true);
      }
    } catch {
      // Sign-in stays usable when browser storage is unavailable.
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api.auth.login({ email, password });
      try {
        if (remember) {
          window.localStorage.setItem(REMEMBERED_EMAIL_KEY, email.trim());
        } else {
          window.localStorage.removeItem(REMEMBERED_EMAIL_KEY);
        }
      } catch {
        // Remembering the address is a convenience, never a sign-in blocker.
      }
      router.replace(next);
      router.refresh();
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : copy.loginFallback
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-frame">
        <section className="auth-panel" aria-label={copy.demoLabel}>
          <svg
            className="auth-star"
            viewBox="0 0 80 80"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M38 4c5 28 8 31 36 35-28 4-31 7-36 35-5-28-8-31-36-35 28-4 31-7 36-35Z"
              stroke="currentColor"
              strokeWidth="5"
              strokeLinejoin="round"
            />
          </svg>
          <div
            className="auth-social-pill auth-social-pill--engagement"
            aria-hidden="true"
          >
            <span>⌁</span> Interacción
          </div>
          <div
            className="auth-social-pill auth-social-pill--likes"
            aria-hidden="true"
          >
            <span>♥</span> 2.4k me gusta
          </div>
          <Image
            className="auth-visual-image"
            src="/figma/login/source-2.png"
            alt="Ejemplo de HiTrendy mostrando diseños para redes sociales"
            width={640}
            height={900}
            priority
          />
          <div
            className="auth-social-pill auth-social-pill--followers"
            aria-hidden="true"
          >
            <span>✦</span> 10k seguidores
          </div>
        </section>
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-card-topline">
            <div className="auth-brand">
              <Logo />
            </div>
            <p className="auth-register-topline">
              {copy.noAccount}{" "}
              <Link href={routes.register}>{copy.registerLink}</Link>
            </p>
          </div>
          <h1 id="auth-title">{copy.welcome}</h1>
          <p className="auth-description">{copy.loginLead}</p>
          {oauthError ? (
            <p role="alert" className="auth-error">
              {oauthError}
            </p>
          ) : null}
          <GoogleSignInButton />
          <div className="auth-divider" aria-hidden="true">
            <span>{copy.divider}</span>
          </div>
          <form onSubmit={submit} className="auth-form">
            <div className="auth-field">
              <label htmlFor="email">{copy.email}</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <PasswordField
              id="password"
              label={copy.password}
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
              showLabel={copy.showPassword}
              hideLabel={copy.hidePassword}
              required
            />
            <div className="auth-form-row">
              <label className="auth-remember" htmlFor="remember-me">
                <input
                  id="remember-me"
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                />
                <span>{copy.rememberMe}</span>
              </label>
              <Link className="auth-form-link" href={routes.resetPassword}>
                {copy.forgotPassword}
              </Link>
            </div>
            {error ? (
              <p role="alert" className="auth-error">
                {error}
              </p>
            ) : null}
            <button type="submit" disabled={submitting}>
              {submitting ? copy.loggingIn : copy.login}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <PublicAuthRoute onPendingSignup="notice">
      <Suspense fallback={<RouteSplash label={surfaceCopy.es.auth.loginLoading} />}>
        <LoginForm />
      </Suspense>
    </PublicAuthRoute>
  );
}
