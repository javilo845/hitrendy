"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { PublicAuthRoute } from "@/components/auth/public-auth-route";
import { RouteSplash } from "@/components/auth/route-splash";
import { api, ApiError } from "@/lib/api";
import { routes } from "@/lib/routes";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [devResetUrl, setDevResetUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setDevResetUrl("");
    setSubmitting(true);
    try {
      if (!token) {
        const response = await api.auth.passwordReset.request(email.trim());
        if (response.dev_reset_url) {
          setMessage("Si existe una cuenta con este correo, se generaron las instrucciones de acceso.");
          setDevResetUrl(response.dev_reset_url);
        } else {
          setMessage("Si el correo está registrado, recibirás instrucciones para recuperar el acceso.");
        }
      } else {
        if (password !== confirmation) {
          setError("Las contraseñas no coinciden.");
          return;
        }
        await api.auth.passwordReset.confirm(token, password);
        setMessage("Tu contraseña fue actualizada con éxito. Ya puedes iniciar sesión.");
      }
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No pudimos completar la recuperación.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page auth-page--single">
      <section className="auth-card" aria-labelledby="reset-title">
        <div className="auth-brand"><Logo /></div>
        <h1 id="reset-title">{token ? "Crea una nueva contraseña" : "Recupera tu acceso"}</h1>
        <p className="auth-description">
          {token
            ? "El enlace es de un solo uso y caduca pronto."
            : "Te enviaremos un enlace si encontramos una cuenta con ese correo."}
        </p>
        <form onSubmit={submit} className="auth-form">
          {!token ? (
            <label htmlFor="reset-email">
              Correo electrónico
              <input id="reset-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
            </label>
          ) : (
            <>
              <label htmlFor="reset-password">
                Nueva contraseña
                <input id="reset-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} autoComplete="new-password" />
              </label>
              <label htmlFor="reset-password-confirmation">
                Repite la contraseña
                <input id="reset-password-confirmation" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required minLength={12} autoComplete="new-password" />
              </label>
            </>
          )}
          {message ? <p role="status" className="auth-success">{message}</p> : null}
          {devResetUrl ? (
            <div style={{ padding: "0.85rem 1rem", background: "rgba(183, 156, 250, 0.15)", borderRadius: "0.8rem", border: "1px solid var(--border)", margin: "0.5rem 0" }}>
              <p style={{ margin: "0 0 0.4rem 0", fontWeight: 700, fontSize: "0.85rem", color: "var(--foreground)" }}>
                Enlace directo de restablecimiento (Modo Demo / Dev):
              </p>
              <Link href={devResetUrl} style={{ wordBreak: "break-all", color: "var(--primary)", fontWeight: 800, fontSize: "0.85rem" }}>
                Haz clic aquí para cambiar tu contraseña
              </Link>
            </div>
          ) : null}
          {error ? <p role="alert" className="auth-error">{error}</p> : null}
          <button type="submit" disabled={submitting}>
            {submitting ? "Procesando…" : token ? "Actualizar contraseña" : "Enviar instrucciones"}
          </button>
        </form>
        <p className="auth-register-prompt"><Link href={routes.login}>Volver a iniciar sesión</Link></p>
        <p className="auth-register-prompt"><Link href={routes.privacy}>Privacidad</Link> · <Link href={routes.terms}>Términos</Link></p>
      </section>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <PublicAuthRoute onPendingSignup="notice">
      <Suspense fallback={<RouteSplash label="Preparando recuperación…" />}>
        <ResetPasswordForm />
      </Suspense>
    </PublicAuthRoute>
  );
}

