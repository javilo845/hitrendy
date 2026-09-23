import type { Platform } from "@/types/business";

/**
 * Platform names are brands, so they read the same in every interface language
 * and live here instead of in the copy catalog. Languages have the same
 * property and are already covered by `localeLabels` in `lib/i18n`.
 */
export const platformLabels: Record<Platform, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  whatsapp: "WhatsApp",
  youtube: "YouTube",
  x: "X / Twitter",
  linkedin: "LinkedIn",
};

/** Presentation order shared by onboarding and settings. */
export const platformOrder: Platform[] = [
  "instagram",
  "facebook",
  "tiktok",
  "whatsapp",
  "youtube",
  "x",
  "linkedin",
];

/** Human-readable list of the platforms a business selected. */
export function formatPlatforms(platforms: Platform[]): string {
  return platforms.map((platform) => platformLabels[platform]).join(", ");
}
