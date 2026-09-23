import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  query: "template=tpl_instagram_01",
  replace: vi.fn(), push: vi.fn(),
  api: {
    businesses: { list: vi.fn(), brandProfile: { get: vi.fn() } }, templates: { list: vi.fn() }, capabilities: { get: vi.fn() },
    projects: { startCreationFlow: vi.fn(), completeCreationFlow: vi.fn(), create: vi.fn(), get: vi.fn(), updateArtifactVersion: vi.fn(), duplicate: vi.fn() },
    conversations: { create: vi.fn(), sendMessage: vi.fn() }, artifacts: { createVariation: vi.fn() },
    trends: { detail: vi.fn() },
    assets: { list: vi.fn() }, images: { draftBrief: vi.fn(), preflight: vi.fn(), createJob: vi.fn(), job: vi.fn(), latestJob: vi.fn() },
    videos: { draftStoryboard: vi.fn(), preflight: vi.fn(), createJob: vi.fn(), job: vi.fn(), latestJob: vi.fn() },
  },
}));
const { api, push, replace } = mocks;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
  useSearchParams: () => new URLSearchParams(mocks.query),
}));
vi.mock("next/image", () => ({ default: (props: { alt: string }) => <img alt={props.alt} /> }));
vi.mock("@/lib/api", () => ({
  api: mocks.api,
  createIdempotencyKey: vi.fn(() => "stable-key"),
  ApiError: class ApiError extends Error { constructor(_status: number, _code: string, message: string) { super(message); } },
}));

import { InstagramPostFlow, validateInstagramDraft } from "@/components/studio/instagram-post-flow";
import { instagramFlowCopy } from "@/lib/instagram-flow-copy";

const template = { id: "tpl_instagram_01", title: "Producto destacado", platforms: ["instagram"], formats: ["static_post"], objective: "sales", thumbnail_url: "/template.png", canva_url: "https://canva.link/jxr6r3xdtdx3p18", aspect_ratio: "4:5" };
const post = { artifact_type: "social_post", platform: "instagram", hook: "Café artesanal", caption: "Caption inicial", call_to_action: "Visítanos hoy", hashtags: ["#Cafe"], visual_direction: "Brief 4:5 para Canva", format_recommendation: "static_post", assumptions: [] };

function configure() {
  api.businesses.list.mockResolvedValue([{ id: "business-1", name: "Café", primary_product: "Café", target_audience: "Vecinos" }]);
  api.businesses.brandProfile.get.mockResolvedValue({ value_proposition: "Café local", voice_tones: ["friendly"] });
  api.templates.list.mockResolvedValue([template]);
  api.capabilities.get.mockResolvedValue({ copywriter: { quality_levels: ["fast"] } });
  api.projects.startCreationFlow.mockResolvedValue({ id: "flow-1", flow_started_at: "2026-01-01T00:00:00Z" });
  api.projects.completeCreationFlow.mockResolvedValue({ id: "flow-1" });
  api.conversations.create.mockResolvedValue({ id: "conversation-1" });
  api.conversations.sendMessage.mockResolvedValue({ artifact: post, artifact_id: "artifact-1" });
  api.projects.create.mockResolvedValue({ id: "project-1" });
  api.projects.updateArtifactVersion.mockResolvedValue({});
  api.projects.duplicate.mockResolvedValue({ id: "project-copy" });
  api.artifacts.createVariation.mockResolvedValue({ artifact: { ...post, caption: "Variación" } });
  api.trends.detail.mockResolvedValue(null);
  api.assets.list.mockResolvedValue([]);
  api.images.draftBrief.mockResolvedValue({ brief: { subject: "Taza de café", setting: "Barra de madera", style: "Fotografía natural", palette: "Tonos cálidos", mood: "Cercano", avoid: "Texto sobre la imagen" }, aspect_ratios: ["1:1", "4:5", "9:16"], capability: { status: "disabled", tier: "paid", message: null, fallback: "visual_brief" }, budget: { remaining: 0, total: 0, next_reset_at: "2026-08-01T00:00:00Z" } });
  api.images.latestJob.mockResolvedValue(null);
  api.videos.draftStoryboard.mockResolvedValue({ storyboard: { hook: "Video para Café", duration_seconds: 5, aspect_ratio: "9:16", voiceover: "Descubre el café local.", music_direction: "Ritmo cálido.", shots: [{ order: 1, duration_seconds: 5, visual: "Producto en primer plano.", camera: "Acercamiento estable.", on_screen_text: "Conócenos", voiceover: "Escríbenos hoy.", transition: "Corte suave" }] }, prompt_preview: "Video vertical de café.", negative_prompt_preview: "Sin texto ilegible.", allowed_durations: [5, 10], aspect_ratio: "9:16", budget: { remaining: 0, total: 0, next_reset_at: "2026-08-01T00:00:00Z" }, capability: { status: "disabled", tier: "paid", message: null, fallback: "storyboard" } });
  api.videos.preflight.mockResolvedValue({ allowed: false, aspect_ratio: "9:16", duration_seconds: 5, storyboard: { hook: "Video para Café", duration_seconds: 5, aspect_ratio: "9:16", voiceover: "Descubre el café local.", music_direction: "Ritmo cálido.", shots: [] }, prompt_preview: "", negative_prompt_preview: "", source_asset_id: null, estimated_units: 0, budget: { remaining: 0, total: 0, next_reset_at: "2026-08-01T00:00:00Z" }, reason_code: "disabled", message: null, approval_token: null, approval_expires_at: null, capability: { status: "disabled", tier: "paid", message: null, fallback: "storyboard" } });
  api.videos.latestJob.mockResolvedValue(null);
}

beforeEach(() => { mocks.query = "template=tpl_instagram_01"; replace.mockReset(); push.mockReset(); Object.values(api).forEach((group) => Object.values(group).forEach((value) => { if (typeof value === "function" && "mockReset" in value) value.mockReset(); })); configure(); });

describe("InstagramPostFlow", () => {
  test("loads authorized context, preselects an approved template, generates and saves once", async () => {
    render(<InstagramPostFlow />);
    await screen.findByText("Producto destacado");
    expect(api.projects.startCreationFlow).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("option", { name: "Equilibrado" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("2. Objetivo o tema"), { target: { value: "Promoción" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar post" }));
    await screen.findByDisplayValue("Caption inicial");
    fireEvent.change(screen.getByLabelText("Texto del post"), { target: { value: "Caption editado" } });
    const save = screen.getByRole("button", { name: "Guardar post" });
    fireEvent.click(save); fireEvent.click(save);
    await waitFor(() => expect(api.projects.create).toHaveBeenCalledTimes(1));
    expect(api.projects.create.mock.calls[0]?.[1]).toEqual({ idempotencyKey: "stable-key" });
    expect(api.projects.updateArtifactVersion).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/studio/new?project=project-1");
  });

  test("restores a saved project without starting telemetry again", async () => {
    mocks.query = "project=project-1";
    api.projects.get.mockResolvedValue({ id: "project-1", artifact_id: "artifact-1", source_template_id: template.id, artifact_snapshot: { ...post, caption: "Caption editado" } });
    render(<InstagramPostFlow />);
    await screen.findByDisplayValue("Caption editado");
    expect(api.projects.startCreationFlow).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue("Brief 4:5 para Canva")).toBeInTheDocument();
  });

  test("validates the editor, preserves a failed draft, warns before unload and reuses duplicate key", async () => {
    expect(validateInstagramDraft({ caption: "", call_to_action: "CTA", hashtags: ["#ok"], visual_direction: "brief" }, instagramFlowCopy.es)).toContain("caption");
    expect(validateInstagramDraft({ caption: "ok", call_to_action: "CTA", hashtags: ["", "#a", "#b", "#c", "#d", "#e"], visual_direction: "brief" }, instagramFlowCopy.es)).toContain("hashtags");
    render(<InstagramPostFlow />);
    await screen.findByText("Producto destacado");
    fireEvent.change(screen.getByLabelText("2. Objetivo o tema"), { target: { value: "Promoción" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar post" }));
    await screen.findByDisplayValue("Caption inicial");
    fireEvent.change(screen.getByLabelText("Texto del post"), { target: { value: "Borrador local" } });
    const unload = new Event("beforeunload", { cancelable: true });
    expect(window.dispatchEvent(unload)).toBe(false);
    api.projects.create.mockRejectedValueOnce(new Error("save failed"));
    fireEvent.click(screen.getByRole("button", { name: "Guardar post" }));
    await screen.findByRole("alert");
    expect(screen.getByDisplayValue("Borrador local")).toBeInTheDocument();
  });

  test("replays duplicate safely and marks a generation failure as terminal telemetry", async () => {
    mocks.query = "project=project-1";
    api.projects.get.mockResolvedValue({ id: "project-1", artifact_id: "artifact-1", source_template_id: template.id, artifact_snapshot: post });
    render(<InstagramPostFlow />);
    await screen.findByRole("button", { name: "Duplicar proyecto" });
    const duplicate = screen.getByRole("button", { name: "Duplicar proyecto" });
    fireEvent.click(duplicate); fireEvent.click(duplicate);
    await waitFor(() => expect(api.projects.duplicate).toHaveBeenCalledTimes(1));
    expect(api.projects.duplicate.mock.calls[0]?.[1]).toEqual({ idempotencyKey: "stable-key" });
    expect(push).toHaveBeenCalledWith("/studio/new?project=project-copy");
  });

  test("marks the started flow as failed when generation errors", async () => {
    api.conversations.sendMessage.mockRejectedValueOnce(new Error("provider error"));
    render(<InstagramPostFlow />);
    await screen.findByText("Producto destacado");
    fireEvent.change(screen.getByLabelText("2. Objetivo o tema"), { target: { value: "Promoción" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar post" }));
    await waitFor(() => expect(api.projects.completeCreationFlow).toHaveBeenCalledWith("flow-1", "failed"));
  });

  test("loads an authorized trend ID into an editable draft without generating", async () => {
    mocks.query = "trend=trend-visible-1";
    api.trends.detail.mockResolvedValue({
      id: "trend-visible-1",
      title: "Café frío local",
      summary: "Interés observado esta semana.",
      region: "HN",
      category: "gastronomy",
      observed_at: "2026-07-30T10:00:00Z",
      freshness_score: 0.9,
      scoring_version: "trend-v1",
      component_scores: {
        freshness: 0.9,
        evidence: 0.33,
        source_diversity: 0.5,
      },
      total_score: 0.8,
      calculated_at: "2026-07-30T10:05:00Z",
      workspace_relevance: {
        score: 1,
        component_scores: {
          business_category: 1,
          regional_match: 1,
        },
        calculated_at: "2026-07-30T10:05:00Z",
      },
      evidence: [
        {
          source: "rss-local",
          source_url: "https://example.test/trends/cafe-frio",
          observed_at: "2026-07-30T10:00:00Z",
          region: "HN",
          confidence: 0.8,
        },
      ],
    });
    render(<InstagramPostFlow />);
    expect(await screen.findByText("Contexto de tendencia")).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Café frío local/)).toBeInTheDocument();
    expect(api.trends.detail).toHaveBeenCalledWith("trend-visible-1");
    expect(api.conversations.sendMessage).not.toHaveBeenCalled();
    expect(api.images.draftBrief).not.toHaveBeenCalled();
  });

  test("offers the image step only once a post exists, and never generates on its own", async () => {
    mocks.query = "project=project-1";
    api.projects.get.mockResolvedValue({ id: "project-1", artifact_id: "artifact-1", source_template_id: template.id, artifact_snapshot: post });
    render(<InstagramPostFlow />);
    expect(await screen.findByRole("heading", { name: "4. Imagen del post" })).toBeInTheDocument();
    await waitFor(() => expect(api.images.draftBrief).toHaveBeenCalledWith({ business_id: "business-1", publication_text: "Caption inicial", trend_title: undefined }));
    expect(api.images.preflight).not.toHaveBeenCalled();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });
});
