export type Tone =
  | "friendly"
  | "professional"
  | "youthful"
  | "elegant"
  | "fun"
  | "direct"
  | "inspiring";

export interface BrandProfile {
  id: string;
  business_id: string;
  voice_tones: Tone[];
  value_proposition: string;
  preferred_words: string[];
  forbidden_words: string[];
  primary_color: string | null;
  secondary_color: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface UpsertBrandProfileRequest {
  voice_tones: Tone[];
  value_proposition: string;
  preferred_words?: string[];
  forbidden_words?: string[];
  primary_color?: string;
  secondary_color?: string;
}
