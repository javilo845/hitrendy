export type Platform =
  | "instagram"
  | "facebook"
  | "tiktok"
  | "whatsapp"
  | "youtube"
  | "x"
  | "linkedin";

export type Objective =
  | "reach"
  | "engagement"
  | "sales"
  | "store_visits"
  | "launch"
  | "brand_awareness"
  | "community";

export type Category =
  | "fashion"
  | "art"
  | "lifestyle"
  | "health"
  | "gastronomy"
  | "services"
  | "retail"
  | "technology"
  | "other";

/** Language new generations start from; independent of the interface language. */
export type ContentLocale = "es" | "en" | "pt";

export interface BusinessProfile {
  id: string;
  workspace_id: string;
  name: string;
  category: Category;
  country: string;
  city: string;
  description: string | null;
  primary_product: string;
  target_audience: string;
  preferred_platforms: Platform[];
  primary_objective: Objective;
  content_locale: ContentLocale;
  created_at: string;
  updated_at: string;
}

export interface CreateBusinessRequest {
  name: string;
  category: Category;
  country: string;
  city: string;
  description?: string;
  primary_product: string;
  target_audience: string;
  preferred_platforms: Platform[];
  primary_objective: Objective;
}

export interface UpdateBusinessRequest {
  name?: string;
  category?: Category;
  country?: string;
  city?: string;
  description?: string;
  primary_product?: string;
  target_audience?: string;
  preferred_platforms?: Platform[];
  primary_objective?: Objective;
  content_locale?: ContentLocale;
}
