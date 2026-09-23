"use client";

import Image from "next/image";
import { useDeferredValue, useState } from "react";

import {
  matchesTemplate,
  templateCategories,
  toTemplatePresentation,
  type TemplateCategory,
  type TemplatePresentation,
} from "@/lib/template-catalog";
import type { Template, TemplateSource } from "@/types/template";
import type { AppLocale } from "@/lib/i18n";
import { surfaceCopy } from "@/lib/i18n";
import { TemplateCover } from "./template-cover";

/** Product names, so they read the same in every locale. */
const SOURCE_BADGE: Record<TemplateSource, string> = {
  custom: "HiTrendy",
  canva: "Canva",
};

/** Canva entries ship no editable slots, so the studio would open empty. */
function openInCanva(url: string) {
  const target = window.open(url, "_blank", "noopener,noreferrer");
  if (target) target.opener = null;
}

interface Props {
  templates: Template[];
  onUse: (template: Template) => Promise<void>;
  compact?: boolean;
  copy: (typeof surfaceCopy)[AppLocale]["templates"];
}

export function TemplateLibrary({ templates, onUse, compact = false, copy }: Props) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<TemplateCategory>("all");
  const [usingTemplateId, setUsingTemplateId] = useState<string | null>(null);
  const deferredQuery = useDeferredValue(query);
  const matching = templates
    .map(toTemplatePresentation)
    .filter((template) => matchesTemplate(template, deferredQuery, category));

  async function startTemplate(template: Template) {
    setUsingTemplateId(template.id);
    try {
      await onUse(template);
    } finally {
      setUsingTemplateId(null);
    }
  }

  return (
    <section
      className={`template-library ${compact ? "template-library--compact" : ""}`}
      aria-label={copy.library}
    >
      {!compact ? (
        <>
          <div className="template-library-heading">
            <div>
              <p className="eyebrow">{copy.eyebrow}</p>
              <h1>{copy.title}</h1>
              <p>{copy.lead}</p>
            </div>
            <span className="template-count" role="status">
              {matching.length}{" "}
              {matching.length === 1 ? copy.singular : copy.plural}
            </span>
          </div>
          <div className="template-toolbar">
            <label className="template-search" htmlFor="template-search">
              <span aria-hidden="true">⌕</span>
              <span className="visually-hidden">{copy.search}</span>
              <input
                id="template-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={copy.searchPlaceholder}
              />
            </label>
            <div
              className="template-filter-row"
              aria-label={copy.categories}
            >
              {templateCategories.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="template-filter"
                  aria-pressed={category === item.id}
                  onClick={() => setCategory(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </>
      ) : null}

      {matching.length ? (
        <div className="template-visual-grid">
          {matching.map((template) => (
            <article className="visual-template-card" key={template.id}>
              <div
                className="visual-template-media"
                style={{ aspectRatio: template.aspectRatio }}
              >
                <TemplateThumbnail template={template} compact={compact} copy={copy} />
                <span>{template.displayCategory}</span>
                <div
                  className="template-source-badge"
                  data-source={template.source}
                >
                  <div className="visually-hidden">
                    {template.source === "canva"
                      ? copy.originCanva
                      : copy.originCustom}
                  </div>
                  <div aria-hidden="true">{SOURCE_BADGE[template.source]}</div>
                </div>
              </div>
              <div className="visual-template-copy">
                <h2>{template.title}</h2>
                <p>
                  {template.displayCategory} ·{" "}
                  {template.aspectRatio.replaceAll(" / ", ":")}
                </p>
                {template.source === "canva" ? (
                  <button
                    type="button"
                    data-source="canva"
                    onClick={() => openInCanva(template.canva_url as string)}
                    disabled={!template.canva_url}
                  >
                    {template.canva_url
                      ? copy.openInCanva
                      : copy.canvaUnavailable}{" "}
                    <span aria-hidden="true">↗</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void startTemplate(template)}
                    disabled={usingTemplateId !== null}
                  >
                    {usingTemplateId === template.id
                      ? copy.preparing
                      : copy.use}{" "}
                    <span aria-hidden="true">→</span>
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="template-empty" role="status">
          <strong>{copy.empty}</strong>
          <span>
            {copy.emptyHint}
          </span>
        </div>
      )}
    </section>
  );
}

function TemplateThumbnail({
  template,
  compact,
  copy,
}: {
  template: TemplatePresentation;
  compact: boolean;
  copy: (typeof surfaceCopy)[AppLocale]["templates"];
}) {
  const [failed, setFailed] = useState(false);

  // No bitmap at all: a Canva entry, whose thumbnails are not public. Its niche
  // cover is a real design, so it is the card's image rather than a fallback.
  if (!template.thumbnail_url) {
    return (
      <TemplateCover
        cover={template.cover}
        title={template.title}
        aspectRatio={template.aspectRatio}
      />
    );
  }

  if (failed) {
    return (
      <div
        className="template-thumbnail-fallback"
        role="img"
        aria-label={`${copy.unavailable}: ${template.title}`}
      >
        <span aria-hidden="true">HT</span>
        <small>{copy.unavailable}</small>
      </div>
    );
  }

  return (
    <Image
      src={template.thumbnail_url}
      alt={`${copy.preview}: ${template.title}`}
      fill
      onError={() => setFailed(true)}
      sizes={
        compact
          ? "(max-width: 639px) 45vw, 180px"
          : "(max-width: 639px) 45vw, (max-width: 1024px) 30vw, 220px"
      }
    />
  );
}
