"use client";

import { surfaceCopy, useInterfaceLocale } from "@/lib/i18n";

interface Props {
  steps: readonly string[];
  current: number;
}

export function ProgressBar({ steps, current }: Props) {
  const copy = surfaceCopy[useInterfaceLocale()].onboarding;
  // A single template per locale: the connector word ("de"/"of") is not the
  // same everywhere, so it cannot be concatenated in the markup.
  const summary = copy.progressLabel
    .replace("{current}", String(current + 1))
    .replace("{total}", String(steps.length))
    .replace("{label}", steps[current] ?? "");

  return (
    <nav className="onboarding-progress" aria-label={copy.progress}>
      <ol className="onboarding-progress-list">
        {steps.map((label, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li
              key={label}
              className={active ? "is-active" : done ? "is-complete" : ""}
              title={label}
              aria-current={active ? "step" : undefined}
            >
              <span className="visually-hidden">{label}</span>
            </li>
          );
        })}
      </ol>
      <p className="onboarding-progress-label">{summary}</p>
    </nav>
  );
}
