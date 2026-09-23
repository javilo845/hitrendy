import { describe, expect, it } from "vitest";

import { detectNiche, suggestCanvaTemplate } from "@/lib/canva-templates";
import type { GeneratedSocialPost } from "@/types/artifact";

function post(overrides: Partial<GeneratedSocialPost> = {}): GeneratedSocialPost {
  return {
    artifact_type: "social_post",
    platform: "instagram",
    hook: "Renueva tu negocio",
    caption: "Una propuesta para tu audiencia.",
    call_to_action: "Escríbenos",
    hashtags: ["#hitrendy", "#contenidoparanegocios"],
    visual_direction: "Composición limpia.",
    format_recommendation: "static_post",
    assumptions: [],
    ...overrides,
  };
}

describe("suggestCanvaTemplate", () => {
  it("takes a technology post to technology templates and hashtags", () => {
    const suggestion = suggestCanvaTemplate(
      post({
        hook: "La nueva laptop para tu oficina",
        caption: "Equipos con inteligencia artificial para trabajar más rápido.",
        hashtags: ["#tecnologia"],
      })
    );

    expect(suggestion.niche).toBe("technology");
    expect(suggestion.query).toContain("tecnologia");
    expect(suggestion.url).toContain("https://www.canva.com/templates/?query=");
    expect(suggestion.hashtags).toContain("#inteligenciaartificial");
  });

  it("recognises the niche through accents and casing", () => {
    expect(detectNiche(post({ hook: "Tecnología para tu Negocio" }))?.id).toBe(
      "technology"
    );
  });

  it("keeps the platform and the format in the search", () => {
    const suggestion = suggestCanvaTemplate(
      post({ platform: "tiktok", format_recommendation: "story", hook: "Nuestro café frío" })
    );

    expect(suggestion.query).toContain("tiktok");
    expect(suggestion.query).toContain("historia");
    expect(suggestion.niche).toBe("gastronomy");
  });

  it("falls back to the post's own words, never to the boilerplate hashtags", () => {
    const suggestion = suggestCanvaTemplate(post({ hook: "Descuentos de temporada" }));

    expect(suggestion.niche).toBe("general");
    expect(suggestion.hashtags).toEqual([]);
    expect(suggestion.query).not.toContain("hitrendy");
    expect(suggestion.query).toContain("Descuentos");
  });
});
