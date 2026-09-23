"use client";

import { useId, useState } from "react";

interface Props {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Native autocomplete token: "current-password" on login, "new-password" on register. */
  autoComplete: "current-password" | "new-password";
  showLabel: string;
  hideLabel: string;
  required?: boolean;
  minLength?: number;
  /** Rendered under the field and wired through aria-describedby, never inside the label. */
  hint?: string;
}

/**
 * Password input with a reveal toggle, shared by login and register so both
 * surfaces keep the same markup, accessible name and focus behavior.
 *
 * The toggle and the hint deliberately live outside <label>: any text nested in
 * a label folds into the input's accessible name, which would turn "Contraseña"
 * into "Contraseña Mostrar contraseña" for assistive tech and for tests.
 */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  showLabel,
  hideLabel,
  required,
  minLength,
  hint,
}: Props) {
  const [revealed, setRevealed] = useState(false);
  const hintId = `${useId()}-hint`;

  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className="auth-input-shell">
        <input
          id={id}
          type={revealed ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          required={required}
          minLength={minLength}
          autoComplete={autoComplete}
          aria-describedby={hint ? hintId : undefined}
        />
        <button
          type="button"
          className="auth-input-toggle"
          onClick={() => setRevealed((current) => !current)}
          aria-pressed={revealed}
          aria-label={revealed ? hideLabel : showLabel}
        >
          <EyeIcon crossed={revealed} />
        </button>
      </div>
      {hint ? (
        <p id={hintId} className="auth-field-hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M2.5 12s3.6-6 9.5-6 9.5 6 9.5 6-3.6 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.7" />
      {crossed ? <path d="m4 20 16-16" /> : null}
    </svg>
  );
}
