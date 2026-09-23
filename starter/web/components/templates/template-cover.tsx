import type { TemplateCoverToken } from "@/types/template";

/**
 * Drawn cover for catalogue entries that have no bitmap of their own. Canva
 * thumbnails are not publicly addressable, so the alternative is an empty card
 * in the middle of the gallery; a cover keeps every entry looking like a
 * finished piece.
 *
 * The whole treatment is CSS: the palette and the motif of each niche live in
 * globals.css under `[data-cover]`, so a niche is retuned there instead of in
 * twelve inline style objects. Nothing here fetches an image or a font.
 */

type CoverKey = TemplateCoverToken | "default";

interface CoverMeta {
  /** Spanish niche name, mirrors the labels in lib/canva-templates.ts. */
  label: string;
  /** Two letters instead of one: Educación/Eventos and Moda/Mascotas collide. */
  monogram: string;
}

const COVER_META: Record<CoverKey, CoverMeta> = {
  technology: { label: "Tecnología", monogram: "Te" },
  gastronomy: { label: "Gastronomía", monogram: "Ga" },
  fashion: { label: "Moda", monogram: "Mo" },
  beauty: { label: "Belleza", monogram: "Be" },
  fitness: { label: "Fitness", monogram: "Fi" },
  health: { label: "Salud", monogram: "Sa" },
  education: { label: "Educación", monogram: "Ed" },
  real_estate: { label: "Inmobiliaria", monogram: "In" },
  automotive: { label: "Automotriz", monogram: "Au" },
  travel: { label: "Viajes", monogram: "Vi" },
  events: { label: "Eventos", monogram: "Ev" },
  pets: { label: "Mascotas", monogram: "Ma" },
  default: { label: "Plantilla", monogram: "HT" },
};

/** Guards against a niche token the backend adds before the web knows it. */
export function templateCoverKey(cover: string | null | undefined): CoverKey {
  return cover && cover in COVER_META ? (cover as CoverKey) : "default";
}

interface Props {
  cover: string | null | undefined;
  title: string;
  /** "4 / 5" or "9 / 16"; only tunes the internal proportions. */
  aspectRatio?: string;
}

export function TemplateCover({ cover, title, aspectRatio }: Props) {
  const key = templateCoverKey(cover);
  const meta = COVER_META[key];

  return (
    // Only <div> inside: `.visual-template-media span` is the category pill and
    // `.review-template-thumb span` is the placeholder glyph, so a <span> here
    // would inherit either treatment. Headings and <strong> are repainted white
    // by the .app-page sweep in the dark shell, which would erase the monogram.
    <div
      className="template-cover"
      data-cover={key}
      data-ratio={aspectRatio === "9 / 16" ? "tall" : "wide"}
      role="img"
      aria-label={`Portada de ${meta.label}: ${title}`}
    >
      <div className="template-cover-art" />
      <div className="template-cover-mark">{meta.monogram}</div>
      <div className="template-cover-caption">
        <div className="template-cover-niche">{meta.label}</div>
        <div className="template-cover-title">{title}</div>
      </div>
    </div>
  );
}
