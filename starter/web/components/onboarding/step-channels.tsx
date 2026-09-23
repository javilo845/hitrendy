"use client";

import type { Objective, Platform } from "@/types/business";
import { optionLabel, surfaceCopy, useInterfaceLocale } from "@/lib/i18n";
import { platformLabels, platformOrder } from "@/lib/labels";

interface Props {
  data: { preferred_platforms: Platform[]; primary_objective: Objective | "" };
  onChange: (field: string, value: unknown) => void;
}

const OBJECTIVES: { value: Objective; label: string }[] = [
  { value: "reach", label: "Alcance" },
  { value: "engagement", label: "Interacción" },
  { value: "sales", label: "Ventas" },
  { value: "store_visits", label: "Visitas a la tienda" },
  { value: "launch", label: "Lanzamiento" },
  { value: "brand_awareness", label: "Reconocimiento de marca" },
  { value: "community", label: "Comunidad" },
];

export function StepChannels({ data, onChange }: Props) {
  const locale = useInterfaceLocale();
  const copy = surfaceCopy[locale].onboarding;
  function togglePlatform(p: Platform) {
    const current = data.preferred_platforms;
    const next = current.includes(p)
      ? current.filter((x) => x !== p)
      : [...current, p];
    onChange("preferred_platforms", next);
  }

  return (
    <section
      className="onboarding-question-card"
      aria-labelledby="channels-step-title"
    >
      <h2 id="channels-step-title">{copy.channelsTitle}</h2>
      <p className="onboarding-step-description">{copy.channelsLead}</p>
      <div className="onboarding-choice-sections">
        <fieldset className="onboarding-choice-group">
          <legend>
            {copy.platforms} <span aria-hidden="true">*</span>
            <span className="visually-hidden">({copy.required})</span>
          </legend>
          <div className="onboarding-choice-grid">
            {platformOrder.map((platform) => (
              <label className="onboarding-choice" key={platform}>
                <input
                  className="onboarding-choice-input"
                  type="checkbox"
                  checked={data.preferred_platforms.includes(platform)}
                  onChange={() => togglePlatform(platform)}
                />
                <span>{platformLabels[platform]}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="onboarding-control-field">
          <label htmlFor="obj-primary">
            {copy.objective} <span aria-hidden="true">*</span>
          </label>
          <select
            id="obj-primary"
            value={data.primary_objective}
            onChange={(e) => onChange("primary_objective", e.target.value)}
            required
          >
            <option value="">{copy.select}</option>
            {OBJECTIVES.map((o) => (
              <option key={o.value} value={o.value}>
                {optionLabel(locale, "objective", o.value) || o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </section>
  );
}
