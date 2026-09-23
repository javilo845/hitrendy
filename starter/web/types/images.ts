import type { CapabilityStatus, Tier } from "@/types/capabilities";

/**
 * The only three formats the product offers. The server enforces the same
 * three; anything else is rejected before a provider is reached.
 */
export type ImageAspectRatio = "1:1" | "4:5" | "9:16";

export const imageAspectRatios: readonly ImageAspectRatio[] = ["1:1", "4:5", "9:16"];

export function isImageAspectRatio(value: unknown): value is ImageAspectRatio {
  return imageAspectRatios.includes(value as ImageAspectRatio);
}

/** What the image should show. Every field is editable by the user. */
export interface VisualBrief {
  subject: string;
  setting: string;
  style: string;
  palette: string;
  mood: string;
  avoid: string;
}

export const visualBriefFields: ReadonlyArray<keyof VisualBrief> = [
  "subject",
  "setting",
  "style",
  "palette",
  "mood",
  "avoid",
];

/**
 * The server's own per-field ceilings, mirrored so the textarea stops the user
 * where the API would. One shared limit would let two of these fields overflow
 * and be refused after the fact.
 */
export const visualBriefLimits: Readonly<Record<keyof VisualBrief, number>> = {
  subject: 240,
  setting: 240,
  style: 200,
  palette: 160,
  mood: 120,
  avoid: 240,
};

/** Daily allowance, in images. Never a currency amount and never a balance. */
export interface ImageBudget {
  remaining: number;
  total: number;
  next_reset_at: string;
}

/**
 * The capability as the server reports it. `fallback` is `"visual_brief"`
 * whenever generation is unavailable: the brief is still the deliverable.
 */
export interface ImageCapabilityState {
  status: CapabilityStatus;
  tier: Tier;
  message: string | null;
  fallback: string | null;
}

/** `POST /images/brief`. Free, provider-free, and answers even when disabled. */
export interface ImageBriefDraft {
  brief: VisualBrief;
  aspect_ratios: ImageAspectRatio[];
  capability: ImageCapabilityState;
  budget: ImageBudget;
}

/**
 * `POST /images/preflight`. Nothing is spent here. `approval_token` is a
 * short-lived signature over this exact brief, format and reference: editing
 * any of them invalidates it and the user must preflight again.
 */
export interface ImagePreflight {
  allowed: boolean;
  aspect_ratio: ImageAspectRatio;
  brief: VisualBrief;
  prompt_preview: string;
  /**
   * What the provider is told to keep out of the image, shown separately
   * because it is sent separately. It is part of the signed approval, so the
   * user approves everything that will be generated, not only the positive half.
   */
  negative_prompt_preview: string | null;
  reference_asset_id: string | null;
  budget: ImageBudget;
  reason_code: string | null;
  message: string | null;
  approval_token: string | null;
  approval_expires_at: string | null;
  capability: ImageCapabilityState;
}

/**
 * `provider_started` means the request already left for the provider and may
 * have been billed. It is not terminal and it is not retryable from here: the
 * server decides how it ends, and the client only keeps watching.
 */
export type ImageJobStatus =
  | "queued"
  | "running"
  | "provider_started"
  | "succeeded"
  | "failed"
  | "cancelled";

export const terminalImageJobStatuses: readonly ImageJobStatus[] = [
  "succeeded",
  "failed",
  "cancelled",
];

export function isTerminalImageJob(status: ImageJobStatus): boolean {
  return terminalImageJobStatuses.includes(status);
}

/**
 * A durable job. `image_url` is minted per read and expires, so it is only
 * present on a successful poll and must never be cached or stored.
 */
export interface ImageJob {
  id: string;
  status: ImageJobStatus;
  aspect_ratio: ImageAspectRatio;
  asset_id: string | null;
  reference_asset_id: string | null;
  error: string | null;
  error_code: string | null;
  created_at: string | null;
  completed_at: string | null;
  image_url?: string | null;
  image_expires_at?: string | null;
}

/** One image the workspace already owns, offered as an optional reference. */
export interface ImageReference {
  id: string;
  original_name: string;
}
