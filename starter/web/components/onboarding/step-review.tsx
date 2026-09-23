"use client";

import type { BusinessFormData } from "@/components/onboarding/step-business";
import type { Objective, Platform } from "@/types/business";
import type { Tone } from "@/types/brand";
import {
  localeLabels,
  optionLabel,
  surfaceCopy,
  useInterfaceLocale,
} from "@/lib/i18n";
import { formatPlatforms } from "@/lib/labels";

interface Props {
  business: BusinessFormData;
  channels: {
    preferred_platforms: Platform[];
    primary_objective: Objective | "";
  };
  brand: {
    voice_tones: Tone[];
    value_proposition: string;
    preferred_words: string;
    forbidden_words: string;
    primary_color: string;
    secondary_color: string;
    content_locale: "es" | "en" | "pt";
  };
  confirmed: boolean;
  onConfirm: (confirmed: boolean) => void;
}

export function StepReview({
  business,
  channels,
  brand,
  confirmed,
  onConfirm,
}: Props) {
  const locale = useInterfaceLocale();
  const copy = surfaceCopy[locale].onboarding;
  return (
    <section
      className="onboarding-question-card"
      aria-labelledby="review-step-title"
    >
      <h2 id="review-step-title">{copy.reviewTitle}</h2>
      <p className="onboarding-step-description">{copy.reviewLead}</p>
      <div className="onboarding-review-grid">
        <ReviewCard title={copy.business}>
          <ReviewRow label={copy.businessName} value={business.name} />
          <ReviewRow
            label={copy.category}
            value={optionLabel(locale, "category", business.category)}
          />
          <ReviewRow
            label={copy.location}
            value={[business.city, business.country].filter(Boolean).join(", ")}
          />
          <ReviewRow label={copy.product} value={business.primary_product} />
          <ReviewRow label={copy.audience} value={business.target_audience} />
          <ReviewRow label={copy.website} value={business.website_url || "—"} />
        </ReviewCard>
        <ReviewCard title={copy.channels}>
          <ReviewRow
            label={copy.platforms}
            value={formatPlatforms(channels.preferred_platforms)}
          />
          <ReviewRow
            label={copy.objective}
            value={optionLabel(locale, "objective", channels.primary_objective)}
          />
        </ReviewCard>
        <ReviewCard title={copy.brand}>
          <ReviewRow
            label={copy.tones}
            value={brand.voice_tones
              .map((tone) => optionLabel(locale, "tone", tone))
              .join(", ")}
          />
          <ReviewRow label={copy.proposition} value={brand.value_proposition} />
          <ReviewRow
            label={copy.contentLocale}
            value={localeLabels[brand.content_locale]}
          />
          <ReviewRow
            label={copy.preferred}
            value={brand.preferred_words || "—"}
          />
          <ReviewRow
            label={copy.forbidden}
            value={brand.forbidden_words || "—"}
          />
        </ReviewCard>
      </div>
      <label className="onboarding-confirmation">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => onConfirm(event.target.checked)}
        />
        {copy.confirm}
      </label>
    </section>
  );
}

function ReviewCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="onboarding-review-card">
      <h3>{title}</h3>
      {children}
    </article>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="onboarding-review-row">
      <strong>{label}</strong>
      <span>{value || "—"}</span>
    </div>
  );
}
