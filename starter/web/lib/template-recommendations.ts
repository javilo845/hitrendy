import { api } from "@/lib/api";
import type { Template } from "@/types/template";

export interface RecommendedTemplate extends Template {
  rationale?: string;
  score?: number;
}

export interface BusinessTargeting {
  platform: string | null;
  objective: string | null;
}

const DEFAULT_LIMIT = 4;

/** Reads the platform/objective pair used to request personalized template
 * recommendations from a business record as returned by
 * `api.businesses.list()`. Never throws; missing or malformed fields become
 * `null`. */
export function readBusinessTargeting(
  business: Record<string, unknown> | undefined | null
): BusinessTargeting {
  if (!business) {
    return { platform: null, objective: null };
  }

  const preferredPlatforms = business.preferred_platforms;
  const platform =
    Array.isArray(preferredPlatforms) &&
    typeof preferredPlatforms[0] === "string" &&
    preferredPlatforms[0].length > 0
      ? preferredPlatforms[0]
      : null;

  const primaryObjective = business.primary_objective;
  const objective =
    typeof primaryObjective === "string" && primaryObjective.length > 0
      ? primaryObjective
      : null;

  return { platform, objective };
}

/** Loads recommended templates for the dashboard's template carousel. Falls
 * back to a slice of the plain catalogue whenever personalized
 * recommendations are unavailable, empty, or the request fails for any
 * reason — this must never throw and must never leave the dashboard section
 * empty. */
export async function loadRecommendedTemplates(params: {
  platform?: string | null;
  objective?: string | null;
  limit?: number;
  fallback: Template[];
}): Promise<RecommendedTemplate[]> {
  const { platform, objective, fallback } = params;
  const limit = params.limit ?? DEFAULT_LIMIT;

  if (
    typeof platform === "string" &&
    platform.length > 0 &&
    typeof objective === "string" &&
    objective.length > 0
  ) {
    try {
      const recommended = await api.templates.recommend({
        platform,
        objective,
        limit,
      });

      if (Array.isArray(recommended) && recommended.length > 0) {
        return recommended as unknown as RecommendedTemplate[];
      }
    } catch {
      // Fall through to the catalogue fallback below — a broken
      // recommender must never break the dashboard.
    }
  }

  return fallback.slice(0, limit);
}
