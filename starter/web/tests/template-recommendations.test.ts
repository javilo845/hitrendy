import { beforeEach, describe, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  api: {
    templates: {
      recommend: vi.fn(),
    },
  },
}));
const { api } = mocks;

vi.mock("@/lib/api", () => ({
  api: mocks.api,
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public code: string,
      message: string,
      public retryable = false
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

import { ApiError } from "@/lib/api";
import {
  loadRecommendedTemplates,
  readBusinessTargeting,
} from "@/lib/template-recommendations";
import type { Template } from "@/types/template";

function template(id: string): Template {
  return {
    id,
    title: `Plantilla ${id}`,
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Anuncios",
    objective: "sales",
    thumbnail_url: `/templates/${id}.png`,
    canva_url: "https://canva.link/xyz",
    aspect_ratio: "4:5",
    editable_slots: ["titulo"],
    description: null,
  };
}

const fallback: Template[] = [
  template("tpl_1"),
  template("tpl_2"),
  template("tpl_3"),
  template("tpl_4"),
  template("tpl_5"),
];

beforeEach(() => {
  api.templates.recommend.mockReset();
});

describe("loadRecommendedTemplates", () => {
  test("calls the recommender when platform and objective are present", async () => {
    const recommended = [
      {
        ...template("tpl_rec_1"),
        rationale: "Encaja con tu objetivo",
        score: 0.9,
      },
    ];
    api.templates.recommend.mockResolvedValueOnce(recommended);

    const result = await loadRecommendedTemplates({
      platform: "instagram",
      objective: "sales",
      fallback,
    });

    expect(api.templates.recommend).toHaveBeenCalledWith({
      platform: "instagram",
      objective: "sales",
      limit: 4,
    });
    expect(result).toEqual(recommended);
  });

  test("falls back to the catalogue slice when the recommender rejects", async () => {
    api.templates.recommend.mockRejectedValueOnce(
      new ApiError(500, "SERVER_ERROR", "Boom", false)
    );

    const result = await loadRecommendedTemplates({
      platform: "instagram",
      objective: "sales",
      fallback,
    });

    expect(result).toEqual(fallback.slice(0, 4));
  });

  test("falls back when the recommender rejects with a non-ApiError", async () => {
    api.templates.recommend.mockRejectedValueOnce(new Error("network down"));

    const result = await loadRecommendedTemplates({
      platform: "instagram",
      objective: "sales",
      fallback,
    });

    expect(result).toEqual(fallback.slice(0, 4));
  });

  test("falls back when the recommender resolves empty", async () => {
    api.templates.recommend.mockResolvedValueOnce([]);

    const result = await loadRecommendedTemplates({
      platform: "instagram",
      objective: "sales",
      fallback,
    });

    expect(result).toEqual(fallback.slice(0, 4));
    expect(result.every((item) => !("rationale" in item))).toBe(true);
  });

  test("falls back when platform is missing, without calling the recommender", async () => {
    const result = await loadRecommendedTemplates({
      platform: null,
      objective: "sales",
      fallback,
    });

    expect(api.templates.recommend).not.toHaveBeenCalled();
    expect(result).toEqual(fallback.slice(0, 4));
  });

  test("falls back when objective is missing, without calling the recommender", async () => {
    const result = await loadRecommendedTemplates({
      platform: "instagram",
      objective: undefined,
      fallback,
    });

    expect(api.templates.recommend).not.toHaveBeenCalled();
    expect(result).toEqual(fallback.slice(0, 4));
  });

  test("respects a custom limit on both the recommender call and the fallback", async () => {
    const recommended = [template("tpl_rec_1"), template("tpl_rec_2")];
    api.templates.recommend.mockResolvedValueOnce(recommended);

    const recommendedResult = await loadRecommendedTemplates({
      platform: "tiktok",
      objective: "awareness",
      limit: 2,
      fallback,
    });

    expect(api.templates.recommend).toHaveBeenCalledWith({
      platform: "tiktok",
      objective: "awareness",
      limit: 2,
    });
    expect(recommendedResult).toEqual(recommended);

    const fallbackResult = await loadRecommendedTemplates({
      platform: null,
      objective: null,
      limit: 2,
      fallback,
    });

    expect(fallbackResult).toEqual(fallback.slice(0, 2));
  });

  test("never throws even when the recommender throws synchronously", async () => {
    api.templates.recommend.mockImplementationOnce(() => {
      throw new Error("synchronous boom");
    });

    await expect(
      loadRecommendedTemplates({
        platform: "instagram",
        objective: "sales",
        fallback,
      })
    ).resolves.toEqual(fallback.slice(0, 4));
  });
});

describe("readBusinessTargeting", () => {
  test("reads the first preferred platform and the primary objective", () => {
    const result = readBusinessTargeting({
      preferred_platforms: ["instagram", "tiktok"],
      primary_objective: "sales",
    });

    expect(result).toEqual({ platform: "instagram", objective: "sales" });
  });

  test("returns nulls when fields are absent", () => {
    expect(readBusinessTargeting({})).toEqual({
      platform: null,
      objective: null,
    });
  });

  test("returns nulls when the business record itself is missing", () => {
    expect(readBusinessTargeting(undefined)).toEqual({
      platform: null,
      objective: null,
    });
    expect(readBusinessTargeting(null)).toEqual({
      platform: null,
      objective: null,
    });
  });

  test("returns nulls when fields have the wrong type", () => {
    const result = readBusinessTargeting({
      preferred_platforms: "instagram",
      primary_objective: 42,
    });

    expect(result).toEqual({ platform: null, objective: null });
  });

  test("returns nulls when preferred_platforms is an empty array", () => {
    const result = readBusinessTargeting({
      preferred_platforms: [],
      primary_objective: "sales",
    });

    expect(result).toEqual({ platform: null, objective: "sales" });
  });
});
