"use client";

import { useId, useState, type FormEvent } from "react";

import { TemplateCover } from "@/components/templates/template-cover";

export interface VisualImprovement {
  priority: "high" | "medium" | "low";
  area: string;
  reason: string;
  action: string;
}

export interface CanvaTemplateRec {
  title: string;
  canva_url: string;
  thumbnail_url?: string;
  reason?: string;
  /** Niche token used to draw a cover when Canva gives us no thumbnail. */
  cover?: string | null;
}

export interface VisualAnalysis {
  id: string;
  summary: string;
  strengths: string[];
  improvements: VisualImprovement[];
  revised_copy: string | null;
  accessibility_notes: string[];
  ai_hallmarks?: string[];
  canva_templates?: CanvaTemplateRec[];
  canva_slots_guide?: Record<string, string>;
  /** Seed for the refine field: what the assistant searched Canva for. */
  canva_query?: string;
  /** Extra angles the assistant suggests trying in Canva. */
  canva_query_suggestions?: string[];
}

interface Props {
  analysis: VisualAnalysis;
}

const PRIORITY_LABELS: Record<string, string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

const AREA_LABELS: Record<string, string> = {
  message: "Mensaje",
  hierarchy: "Jerarquía",
  readability: "Legibilidad",
  brand: "Marca",
  cta: "Llamado a la acción",
  platform: "Plataforma",
  accessibility: "Accesibilidad",
};

const CANVA_SEARCH = "https://www.canva.com/templates/";

/** Canva takes the query as a plain search parameter. */
function canvaSearchUrl(query: string) {
  return `${CANVA_SEARCH}?query=${encodeURIComponent(query.trim())}`;
}

function CanvaTemplateCard({
  template,
  index,
}: {
  template: CanvaTemplateRec;
  index: number;
}) {
  const [imgError, setImgError] = useState(false);
  const isLocalMock = !template.thumbnail_url || template.thumbnail_url.startsWith("/templates/");
  const showMockup = isLocalMock || imgError;

  const titleLower = (template.title || "").toLowerCase();
  const isPromo =
    titleLower.includes("promo") ||
    titleLower.includes("oferta") ||
    titleLower.includes("descuento") ||
    titleLower.includes("ventas");
  const isProduct =
    titleLower.includes("producto") ||
    titleLower.includes("foto") ||
    titleLower.includes("destacad") ||
    titleLower.includes("plato");

  const icon = isPromo ? "🏷️" : isProduct ? "📸" : "✨";
  const badgeLabel = isPromo ? "Promocional" : isProduct ? "Producto" : "Marca";

  return (
    <a
      className="review-template canva-template-card"
      href={template.canva_url}
      target="_blank"
      rel="noopener noreferrer"
      title={`Abrir ${template.title} en Canva`}
    >
      <span className="review-template-thumb canva-template-thumb">
        {!showMockup && template.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={template.thumbnail_url}
            alt={template.title}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : template.cover ? (
          <TemplateCover cover={template.cover} title={template.title} />
        ) : (
          <div className="canva-mockup-visual" data-variant={index % 3}>
            <div className="canva-mockup-badge-bar">
              <span className="canva-brand-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.8 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
                </svg>
                Canva
              </span>
              <span className="canva-format-tag">{badgeLabel}</span>
            </div>
            <div className="canva-mockup-canvas">
              <span className="canva-mockup-icon">{icon}</span>
              <div className="canva-mockup-wireframe">
                <div className="canva-wire-line canva-wire-title" />
                <div className="canva-wire-line canva-wire-subtitle" />
                <div className="canva-wire-pill">
                  <span>Plantilla en línea</span>
                </div>
              </div>
            </div>
            <div className="canva-mockup-bottom">
              <span>Abrir en Canva ↗</span>
            </div>
          </div>
        )}
      </span>
      <strong className="canva-template-title">{template.title}</strong>
      {template.reason ? <p className="canva-template-reason">{template.reason}</p> : null}
      <em className="canva-template-cta">
        <span>Abrir en Canva</span>
        <span aria-hidden="true">↗</span>
      </em>
    </a>
  );
}

export function VisualReviewCard({ analysis }: Props) {
  const titleId = useId();
  const searchId = useId();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [query, setQuery] = useState(analysis.canva_query || "");

  const handleCopy = (text: string, key: string) => {
    void navigator.clipboard?.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const templates = analysis.canva_templates ?? [];
  const headline = analysis.canva_slots_guide?.headline;
  // The "what still reads as AI / off-the-shelf" list. When the provider does
  // not send one, the improvement reasons say the same thing.
  const weakPoints =
    analysis.ai_hallmarks && analysis.ai_hallmarks.length > 0
      ? analysis.ai_hallmarks
      : analysis.improvements.map((item) => item.reason);
  const suggestions = analysis.canva_query_suggestions ?? [];

  function openCanvaSearch(event: FormEvent) {
    event.preventDefault();
    const term = query.trim();
    if (!term) return;
    window.open(canvaSearchUrl(term), "_blank", "noopener,noreferrer");
  }

  return (
    <article className="review-card" aria-labelledby={titleId}>
      <div className="review-card-head">
        <span className="review-eyebrow">Auditoría visual</span>
        <h3 id={titleId}>Diagnóstico del diseño</h3>
      </div>
      <p className="review-summary">{analysis.summary}</p>

      {/* The reference puts the verdict in two facing columns, so the good news
          and the work to do are read together instead of one after the other. */}
      {(analysis.strengths.length > 0 || weakPoints.length > 0) && (
        <div className="review-split" data-columns="2">
          <div className="review-split-column" data-tone="positive">
            <h4>Haz hecho bien en:</h4>
            <ul>
              {analysis.strengths.length > 0 ? (
                analysis.strengths.map((item, index) => (
                  <li key={index}>{item}</li>
                ))
              ) : (
                <li>Aún no encontramos puntos fuertes claros en esta pieza.</li>
              )}
            </ul>
          </div>
          <span className="review-split-divider" aria-hidden="true" />
          <div className="review-split-column" data-tone="critical">
            <h4>Puntos a mejorar:</h4>
            <ul>
              {weakPoints.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {analysis.improvements.length > 0 && (
        <section className="review-section">
          <h4>Cómo mejorarlo</h4>
          <ul className="review-improvements">
            {analysis.improvements.map((item, index) => (
              <li key={index} className="review-improvement">
                <div className="review-improvement-head">
                  <strong>{AREA_LABELS[item.area] || item.area}</strong>
                  <span className="review-priority" data-priority={item.priority}>
                    Prioridad {PRIORITY_LABELS[item.priority] || item.priority}
                  </span>
                </div>
                <p className="review-improvement-reason">{item.reason}</p>
                <p className="review-improvement-action">{item.action}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis.accessibility_notes.length > 0 && (
        <section className="review-section">
          <h4>Accesibilidad</h4>
          <div className="review-split">
            <div className="review-split-column">
              <ul>
                {analysis.accessibility_notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {(headline || analysis.revised_copy) && (
        <section className="review-section">
          <h4>Textos listos para pegar</h4>
          <dl className="review-copy">
            {headline && (
              <div className="review-copy-row">
                <dt>Titular</dt>
                <dd>{headline}</dd>
                <button
                  type="button"
                  className="review-copy-button"
                  onClick={() => handleCopy(headline, "headline")}
                  data-copied={copiedKey === "headline" || undefined}
                >
                  {copiedKey === "headline" ? "Copiado" : "Copiar"}
                </button>
              </div>
            )}
            {analysis.revised_copy && (
              <div className="review-copy-row">
                <dt>Copy sugerido</dt>
                <dd>{analysis.revised_copy}</dd>
                <button
                  type="button"
                  className="review-copy-button"
                  onClick={() => handleCopy(analysis.revised_copy!, "copy")}
                  data-copied={copiedKey === "copy" || undefined}
                >
                  {copiedKey === "copy" ? "Copiado" : "Copiar"}
                </button>
              </div>
            )}
          </dl>
        </section>
      )}

      <section className="review-section">
        <div className="review-templates-head">
          <div className="review-templates-title-group">
            <h4>Plantillas recomendadas en Canva</h4>
            <span className="canva-online-indicator">En línea</span>
          </div>
          <p>Sugerencias personalizadas por IA para rediseñar en Canva en vivo</p>
        </div>

        {templates.length > 0 && (
          <div className="review-template-grid">
            {templates.map((template, index) => (
              <CanvaTemplateCard key={index} template={template} index={index} />
            ))}
          </div>
        )}

        {/* Refining the search is the usual next move after seeing the picks,
            so it happens here instead of asking again in the composer. */}
        <form className="review-template-search" onSubmit={openCanvaSearch}>
          <label className="visually-hidden" htmlFor={searchId}>
            Buscar otras plantillas en Canva
          </label>
          <input
            id={searchId}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar otro estilo en Canva…"
          />
          <button type="submit" disabled={!query.trim()}>
            Buscar en Canva
          </button>
        </form>

        {suggestions.length > 0 && (
          <div className="review-template-chips">
            {suggestions.map((item) => (
              <button
                key={item}
                type="button"
                className="review-template-chip"
                onClick={() => {
                  setQuery(item);
                  window.open(
                    canvaSearchUrl(item),
                    "_blank",
                    "noopener,noreferrer"
                  );
                }}
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </section>
    </article>
  );
}
