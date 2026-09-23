export type CapabilityName =
  | "advisor"
  | "copywriter"
  | "vision_review"
  | "image_generation"
  | "video_generation"
  | "trend_analysis";

export type CapabilityStatus =
  | "available"
  | "unconfigured"
  | "disabled"
  | "restricted"
  | "quota_exhausted"
  | "payment_required"
  | "degraded"
  | "error";

export type QualityLevel = "fast" | "balanced" | "quality";

export type Tier = "free" | "paid" | "mixed" | "unknown";

export interface PublicCapability {
  status: CapabilityStatus;
  tier: Tier;
  quality_levels: QualityLevel[];
  message?: string | null;
  next_reset_at?: string | null;
  fallback?: string | null;
}

export type PublicCapabilities = Record<CapabilityName, PublicCapability>;
