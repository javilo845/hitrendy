"use client";

import { FormEvent, useState } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { api, ApiError } from "@/lib/api";

export default function FeedbackPage() {
  const [category, setCategory] = useState<"bug" | "idea" | "support" | "other">("support");
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus("");
    setSaving(true);
    try {
      await api.operations.feedback(
        {
          category,
          message: message.trim(),
          ...(rating ? { rating: Number(rating) } : {}),
        },
        { idempotencyKey: crypto.randomUUID() }
      );
      setMessage("");
      setRating("");
      setStatus("Gracias. Recibimos tu mensaje y lo revisaremos.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No pudimos enviar tu mensaje.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <section className="settings-page" aria-labelledby="feedback-title">
        <div className="settings-heading"><p className="eyebrow">SOPORTE BETA</p><h1 id="feedback-title">¿Cómo podemos mejorar?</h1><p>Comparte un problema, una idea o una pregunta. No incluyas contraseñas ni claves.</p></div>
        <form className="settings-card auth-form" onSubmit={submit}>
          <label htmlFor="feedback-category">Tipo de mensaje<select id="feedback-category" value={category} onChange={(event) => setCategory(event.target.value as typeof category)}><option value="support">Soporte</option><option value="bug">Problema</option><option value="idea">Idea</option><option value="other">Otro</option></select></label>
          <label htmlFor="feedback-rating">¿Qué tan útil fue la beta? (opcional)<select id="feedback-rating" value={rating} onChange={(event) => setRating(event.target.value)}><option value="">Sin valoración</option><option value="1">1 — Muy difícil</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5 — Muy útil</option></select></label>
          <label htmlFor="feedback-message">Mensaje<textarea id="feedback-message" value={message} onChange={(event) => setMessage(event.target.value)} required maxLength={2000} rows={7} /></label>
          {status ? <p role="status" className="auth-success">{status}</p> : null}
          {error ? <p role="alert" className="auth-error">{error}</p> : null}
          <button type="submit" disabled={saving || !message.trim()}>{saving ? "Enviando…" : "Enviar feedback"}</button>
        </form>
      </section>
    </AppShell>
  );
}

