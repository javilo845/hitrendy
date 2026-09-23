/**
 * Niche tokens the catalogue sends for entries it has no bitmap for. The web
 * draws these with CSS instead of requesting an image from Canva, whose
 * thumbnails are not public and would leave the card blank.
 */
export type TemplateCoverToken =
  | "technology"
  | "gastronomy"
  | "fashion"
  | "beauty"
  | "fitness"
  | "health"
  | "education"
  | "real_estate"
  | "automotive"
  | "travel"
  | "events"
  | "pets";

/** Where the entry comes from: our own catalogue or the Canva catalogue. */
export type TemplateSource = "custom" | "canva";

export interface Template {
  id: string;
  title: string;
  platforms: string[];
  formats: string[];
  category: string;
  objective: string;
  /** Null for Canva entries, which are drawn from `cover` instead. */
  thumbnail_url: string | null;
  canva_url?: string;
  aspect_ratio?: "4:5";
  editable_slots: string[];
  description: string | null;
  /**
   * The API always sends this; it stays optional so seeded demo fixtures and
   * older stored payloads still type-check. Absent means "custom".
   */
  source?: TemplateSource;
  cover?: string | null;
}
