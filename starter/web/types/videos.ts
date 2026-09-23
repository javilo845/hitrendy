import type { CapabilityStatus, Tier } from "@/types/capabilities";

/** WAVE-013 is vertical-only until another aspect ratio is explicitly enabled. */
export const videoAspectRatios = ["9:16"] as const;
export type VideoAspectRatio = (typeof videoAspectRatios)[number];

export function isVideoAspectRatio(value: string): value is VideoAspectRatio {
  return videoAspectRatios.includes(value as VideoAspectRatio);
}

export interface VideoShot {
  order: number;
  duration_seconds: number;
  visual: string;
  camera: string;
  on_screen_text: string;
  voiceover: string;
  transition: string;
}

export interface VideoStoryboard {
  hook: string;
  duration_seconds: number;
  aspect_ratio: VideoAspectRatio;
  voiceover: string;
  music_direction: string;
  shots: VideoShot[];
}

export const videoShotFields = [
  "visual",
  "camera",
  "on_screen_text",
  "voiceover",
  "transition",
] as const;

export const videoStoryboardLimits = {
  hook: 160,
  voiceover: 600,
  music_direction: 160,
  visual: 240,
  camera: 120,
  on_screen_text: 120,
  shot_voiceover: 240,
  transition: 60,
} as const;

/** Allowance in generation units. This is never a monetary balance. */
export interface VideoBudget {
  remaining: number;
  total: number;
  next_reset_at: string;
}

export interface VideoCapabilityState {
  status: CapabilityStatus;
  tier: Tier;
  message: string | null;
  fallback: string | null;
}

export interface VideoStoryboardDraft {
  storyboard: VideoStoryboard;
  prompt_preview: string;
  negative_prompt_preview: string;
  allowed_durations: number[];
  aspect_ratio: VideoAspectRatio;
  budget: VideoBudget;
  capability: VideoCapabilityState;
}

export interface VideoPreflight {
  allowed: boolean;
  aspect_ratio: VideoAspectRatio;
  duration_seconds: number;
  storyboard: VideoStoryboard;
  prompt_preview: string;
  negative_prompt_preview: string;
  source_asset_id: string | null;
  estimated_units: number;
  budget: VideoBudget;
  reason_code: string | null;
  message: string | null;
  approval_token: string | null;
  approval_expires_at: string | null;
  capability: VideoCapabilityState;
}

export type VideoJobStatus =
  | "queued"
  | "preparing"
  | "submitting"
  | "provider_pending"
  | "downloading"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "execution_unknown";

export const terminalVideoJobStatuses = [
  "succeeded",
  "failed",
  "cancelled",
  "execution_unknown",
] as const;

export function isTerminalVideoJob(status: VideoJobStatus): boolean {
  return terminalVideoJobStatuses.some((terminal) => terminal === status);
}

export interface VideoJob {
  id: string;
  status: VideoJobStatus;
  aspect_ratio: VideoAspectRatio;
  duration_seconds: number;
  source_asset_id: string | null;
  asset_id: string | null;
  video_url: string | null;
  video_expires_at: string | null;
  created_at: string;
  completed_at: string | null;
  safe_error: string | null;
  safe_error_code: string | null;
}

export interface VideoSourceImage {
  id: string;
  url: string | null;
  created_at: string;
}
