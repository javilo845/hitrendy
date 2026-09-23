"use client";

import { useEffect, useState } from "react";

import type { Tone } from "@/types/brand";
import {
  localeLabels,
  optionLabel,
  supportedLocales,
  surfaceCopy,
  useInterfaceLocale,
} from "@/lib/i18n";
import { defaultBrandColors } from "@/lib/brand-defaults";

interface Props {
  data: {
    voice_tones: Tone[];
    value_proposition: string;
    preferred_words: string;
    forbidden_words: string;
    primary_color: string;
    secondary_color: string;
    content_locale?: "es" | "en" | "pt";
  };
  onChange: (field: string, value: unknown) => void;
  showContentLocale?: boolean;
}

const TONES: { value: Tone; label: string }[] = [
  { value: "friendly", label: "Amigable" },
  { value: "professional", label: "Profesional" },
  { value: "youthful", label: "Juvenil" },
  { value: "elegant", label: "Elegante" },
  { value: "fun", label: "Divertido" },
  { value: "direct", label: "Directo" },
  { value: "inspiring", label: "Inspirador" },
];

/** The exact value the brand already owns, as it is written down elsewhere. */
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

/**
 * A swatch alone cannot express "this is our brand blue, code 0F62FE": picking
 * it by eye lands one shade off. The text field is the authoritative input and
 * the picker mirrors it, so a brand book value can be typed in verbatim.
 */
function BrandColorField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const [draft, setDraft] = useState(value);

  // The parent still owns the value: a change coming from anywhere else (a
  // restored draft, the other step) has to win over what is displayed here.
  useEffect(() => {
    setDraft(value);
  }, [value]);

  const valid = HEX_COLOR.test(draft);

  function editText(raw: string) {
    const cleaned = raw.replace(/[^0-9a-fA-F]/g, "").slice(0, 6);
    const next = `#${cleaned.toUpperCase()}`;
    setDraft(next);
    // Only a complete code is committed; a half-typed one would be rejected by
    // the API, so the last valid colour stays in force until this one is whole.
    if (HEX_COLOR.test(next)) onChange(next);
  }

  return (
    <div className="onboarding-color-field">
      <label htmlFor={id}>{label}</label>
      <div className="onboarding-color-inputs">
        <input
          id={id}
          type="color"
          value={valid ? draft : value}
          onChange={(event) => {
            setDraft(event.target.value.toUpperCase());
            onChange(event.target.value.toUpperCase());
          }}
        />
        <input
          type="text"
          className="onboarding-color-hex"
          value={draft}
          maxLength={7}
          spellCheck={false}
          autoComplete="off"
          placeholder="#RRGGBB"
          aria-label={`${label} (hex)`}
          aria-invalid={valid ? undefined : true}
          onChange={(event) => editText(event.target.value)}
          onBlur={() => {
            if (!valid) setDraft(value);
          }}
        />
      </div>
    </div>
  );
}

export function StepBrand({
  data,
  onChange,
  showContentLocale = false,
}: Props) {
  const locale = useInterfaceLocale();
  const copy = surfaceCopy[locale].onboarding;
  function toggleTone(t: Tone) {
    const current = data.voice_tones;
    const next = current.includes(t)
      ? current.filter((x) => x !== t)
      : [...current, t];
    onChange("voice_tones", next.slice(0, 3));
  }

  return (
    <section
      className="onboarding-question-card"
      aria-labelledby="brand-step-title"
    >
      <h2 id="brand-step-title">{copy.brandTitle}</h2>
      <p className="onboarding-step-description">{copy.brandLead}</p>
      <div className="onboarding-choice-sections">
        <fieldset className="onboarding-choice-group">
          <legend>
            {copy.tones} <span aria-hidden="true">*</span>
            <span className="visually-hidden">({copy.required})</span>
          </legend>
          <div className="onboarding-choice-grid">
            {TONES.map((t) => (
              <label className="onboarding-choice" key={t.value}>
                <input
                  className="onboarding-choice-input"
                  type="checkbox"
                  checked={data.voice_tones.includes(t.value)}
                  onChange={() => toggleTone(t.value)}
                  disabled={
                    !data.voice_tones.includes(t.value) &&
                    data.voice_tones.length >= 3
                  }
                />
                <span>{optionLabel(locale, "tone", t.value) || t.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="onboarding-control-field">
          <label htmlFor="brand-value-prop">
            {copy.proposition} <span aria-hidden="true">*</span>
          </label>
          <textarea
            id="brand-value-prop"
            value={data.value_proposition}
            onChange={(e) => onChange("value_proposition", e.target.value)}
            required
            maxLength={500}
            rows={3}
            placeholder={copy.propositionPlaceholder}
          />
        </div>
        <div className="onboarding-control-field">
          <label htmlFor="brand-preferred">{copy.preferred}</label>
          <input
            id="brand-preferred"
            type="text"
            value={data.preferred_words}
            onChange={(e) => onChange("preferred_words", e.target.value)}
            placeholder={copy.wordsPlaceholder}
          />
        </div>
        <div className="onboarding-control-field">
          <label htmlFor="brand-forbidden">{copy.forbidden}</label>
          <input
            id="brand-forbidden"
            type="text"
            value={data.forbidden_words}
            onChange={(e) => onChange("forbidden_words", e.target.value)}
            placeholder={copy.wordsPlaceholder}
          />
        </div>
        <div className="onboarding-color-row">
          <BrandColorField
            id="brand-primary-color"
            label={copy.primaryColor}
            value={data.primary_color || defaultBrandColors.primary}
            onChange={(next) => onChange("primary_color", next)}
          />
          <BrandColorField
            id="brand-secondary-color"
            label={copy.secondaryColor}
            value={data.secondary_color || defaultBrandColors.secondary}
            onChange={(next) => onChange("secondary_color", next)}
          />
        </div>
        {showContentLocale ? (
          <label htmlFor="brand-content-locale">
            {copy.contentLocale}
            <select
              id="brand-content-locale"
              value={data.content_locale || "es"}
              onChange={(e) => onChange("content_locale", e.target.value)}
            >
              {supportedLocales.map((value) => (
                <option key={value} value={value}>
                  {localeLabels[value]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
    </section>
  );
}
