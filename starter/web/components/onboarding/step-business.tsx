"use client";

import type { Category } from "@/types/business";
import { optionLabel, surfaceCopy, useInterfaceLocale } from "@/lib/i18n";

export interface BusinessFormData {
  name: string;
  category: Category | "";
  country: string;
  city: string;
  description: string;
  primary_product: string;
  target_audience: string;
  website_url: string;
}

interface Props {
  data: BusinessFormData;
  onChange: (field: keyof BusinessFormData, value: string) => void;
}

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "fashion", label: "Moda" },
  { value: "art", label: "Arte" },
  { value: "lifestyle", label: "Estilo de vida" },
  { value: "health", label: "Salud" },
  { value: "gastronomy", label: "Gastronomía" },
  { value: "services", label: "Servicios" },
  { value: "retail", label: "Comercio" },
  { value: "technology", label: "Tecnología" },
  { value: "other", label: "Otro" },
];

export function StepBusiness({ data, onChange }: Props) {
  const locale = useInterfaceLocale();
  const copy = surfaceCopy[locale].onboarding;
  return (
    <section
      className="onboarding-question-card"
      aria-labelledby="business-step-title"
    >
      <h2 id="business-step-title">{copy.businessTitle}</h2>
      <p className="onboarding-step-description">{copy.businessLead}</p>
      <div className="onboarding-fields">
        <label>
          {copy.businessName} <span aria-hidden="true">*</span>
          <input
            name="business-name"
            type="text"
            value={data.name}
            onChange={(event) => onChange("name", event.target.value)}
            required
            maxLength={120}
            autoComplete="organization"
          />
        </label>
        <label>
          {copy.category} <span aria-hidden="true">*</span>
          <select
            name="business-category"
            value={data.category}
            onChange={(event) => onChange("category", event.target.value)}
            required
          >
            <option value="">{copy.select}</option>
            {CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>
                {optionLabel(locale, "category", category.value) ||
                  category.label}
              </option>
            ))}
          </select>
        </label>
        <div className="onboarding-field-grid">
          <label>
            {copy.country} <span aria-hidden="true">*</span>
            <input
              name="business-country"
              type="text"
              value={data.country}
              onChange={(event) => onChange("country", event.target.value)}
              required
              maxLength={80}
              autoComplete="country-name"
            />
          </label>
          <label>
            {copy.city} <span aria-hidden="true">*</span>
            <input
              name="business-city"
              type="text"
              value={data.city}
              onChange={(event) => onChange("city", event.target.value)}
              required
              maxLength={100}
              autoComplete="address-level2"
            />
          </label>
        </div>
        <label>
          {copy.product} <span aria-hidden="true">*</span>
          <input
            name="business-product"
            type="text"
            value={data.primary_product}
            onChange={(event) =>
              onChange("primary_product", event.target.value)
            }
            required
            maxLength={240}
          />
        </label>
        <label>
          {copy.audience} <span aria-hidden="true">*</span>
          <textarea
            name="business-audience"
            value={data.target_audience}
            onChange={(event) =>
              onChange("target_audience", event.target.value)
            }
            required
            maxLength={500}
            rows={3}
            placeholder={copy.audiencePlaceholder}
          />
        </label>
        <label>
          {copy.description}
          <textarea
            name="business-description"
            value={data.description}
            onChange={(event) => onChange("description", event.target.value)}
            maxLength={1000}
            rows={3}
          />
        </label>
        <label>
          {copy.website}{" "}
          <span className="onboarding-optional">{copy.optional}</span>
          <input
            name="business-website"
            type="url"
            value={data.website_url}
            onChange={(event) => onChange("website_url", event.target.value)}
            maxLength={500}
            placeholder="https://tu-negocio.com"
            autoComplete="url"
          />
        </label>
      </div>
    </section>
  );
}
