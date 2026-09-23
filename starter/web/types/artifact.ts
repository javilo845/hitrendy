export type Platform =
  | "instagram"
  | "facebook"
  | "tiktok"
  | "whatsapp"
  | "youtube"
  | "x"
  | "linkedin";

export interface GeneratedSocialPost {
  artifact_type: "social_post";
  platform: Platform;
  hook: string;
  caption: string;
  call_to_action: string;
  hashtags: string[];
  visual_direction: string;
  format_recommendation:
    "static_post" | "carousel" | "story" | "reel" | "short_video" | "text_post";
  assumptions: string[];
}

export interface VideoScene {
  order: number;
  duration_seconds: number;
  visual: string;
  on_screen_text: string;
  voiceover: string;
}

export interface GeneratedShortVideoScript {
  artifact_type: "short_video_script";
  platform: Platform;
  hook: string;
  duration_seconds: number;
  scenes: VideoScene[];
  call_to_action: string;
  caption: string;
  assumptions: string[];
}

export type GeneratedArtifact = GeneratedSocialPost | GeneratedShortVideoScript;

export type VariationKind =
  | "shorter"
  | "more_youthful"
  | "more_professional"
  | "more_friendly";
