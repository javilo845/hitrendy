import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { axe } from "vitest-axe";

const mocks = vi.hoisted(() => ({
  api: {
    assets: { list: vi.fn() },
    videos: {
      draftStoryboard: vi.fn(),
      preflight: vi.fn(),
      createJob: vi.fn(),
      job: vi.fn(),
      latestJob: vi.fn(),
    },
  },
  keys: 0,
}));
const { api } = mocks;

vi.mock("@/lib/api", () => ({
  api: mocks.api,
  createIdempotencyKey: vi.fn(() => `key-${(mocks.keys += 1)}`),
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

import { VideoGenerationStep } from "@/components/studio/video-generation-step";
import { instagramFlowCopy } from "@/lib/instagram-flow-copy";

const es = instagramFlowCopy.es.video;

const storyboard = {
  hook: "Una pausa que empieza con buen café",
  duration_seconds: 5,
  aspect_ratio: "9:16",
  voiceover: "Descubre una pausa preparada para disfrutarla.",
  music_direction: "Ritmo cálido y optimista, sin cubrir la voz.",
  shots: [
    {
      order: 1,
      duration_seconds: 2,
      visual: "Taza de café junto a una ventana con luz de mañana.",
      camera: "Acercamiento vertical lento y estable.",
      on_screen_text: "Tu pausa empieza aquí",
      voiceover: "Una pausa puede cambiar tu mañana.",
      transition: "Corte suave",
    },
    {
      order: 2,
      duration_seconds: 3,
      visual: "Persona disfrutando el café en la barra del negocio.",
      camera: "Plano medio vertical con movimiento lateral sutil.",
      on_screen_text: "Conócenos hoy",
      voiceover: "Escríbenos y encuentra tu próximo momento favorito.",
      transition: "Fundido breve",
    },
  ],
};

const budget = { remaining: 4, total: 5, next_reset_at: "2026-08-03T00:00:00Z" };
const available = { status: "available", tier: "paid", message: null, fallback: null };

function storyboardDraft(overrides: Record<string, unknown> = {}) {
  return {
    storyboard,
    prompt_preview: "Video vertical 9:16 de una pausa cálida con café.",
    negative_prompt_preview: "Sin texto ilegible ni movimientos bruscos.",
    allowed_durations: [5, 10],
    aspect_ratio: "9:16",
    budget,
    capability: available,
    ...overrides,
  };
}

function preflight(overrides: Record<string, unknown> = {}) {
  return {
    allowed: true,
    aspect_ratio: "9:16",
    duration_seconds: 5,
    storyboard,
    prompt_preview: "Video vertical 9:16 de una pausa cálida con café.",
    negative_prompt_preview: "Sin texto ilegible ni movimientos bruscos.",
    source_asset_id: null,
    estimated_units: 1,
    budget,
    reason_code: null,
    message: null,
    approval_token: "video-approval-1",
    approval_expires_at: "2026-08-02T12:05:00Z",
    capability: available,
    ...overrides,
  };
}

function job(overrides: Record<string, unknown> = {}) {
  return {
    id: "video-job-1",
    status: "queued",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    source_asset_id: null,
    asset_id: null,
    video_url: null,
    video_expires_at: null,
    created_at: "2026-08-02T12:00:00Z",
    completed_at: null,
    safe_error: null,
    safe_error_code: null,
    ...overrides,
  };
}

/** The flow always gives the step its durable parent. */
function renderStep(props: Record<string, unknown> = {}) {
  return render(
    <VideoGenerationStep
      businessId="business-1"
      copy={es}
      publicationText="Caption inicial"
      trendTitle="Café frío local"
      projectId="project-1"
      {...props}
    />
  );
}

async function click(element: HTMLElement) {
  await act(async () => {
    fireEvent.click(element);
  });
}

async function change(element: HTMLElement, value: string) {
  await act(async () => {
    fireEvent.change(element, { target: { value } });
  });
}

function useTimers() {
  vi.useFakeTimers({ shouldAdvanceTime: true });
}

async function tick(times = 1) {
  for (let index = 0; index < times; index += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
  }
}

beforeEach(() => {
  mocks.keys = 0;
  api.assets.list.mockReset().mockResolvedValue([]);
  api.videos.draftStoryboard.mockReset().mockResolvedValue(storyboardDraft());
  api.videos.preflight.mockReset().mockResolvedValue(preflight());
  api.videos.createJob.mockReset().mockResolvedValue(job());
  api.videos.job.mockReset().mockResolvedValue(job());
  api.videos.latestJob.mockReset().mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("VideoGenerationStep", () => {
  test("keeps a useful editable storyboard when video is unavailable", async () => {
    api.videos.draftStoryboard.mockResolvedValue(
      storyboardDraft({
        capability: { status: "disabled", tier: "paid", message: null, fallback: "storyboard" },
      })
    );
    renderStep();

    expect(await screen.findByDisplayValue(storyboard.hook)).toBeInTheDocument();
    expect(screen.getByText(es.reason.disabled)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: es.confirm })).toBeDisabled();
    await change(screen.getByLabelText(es.hook), "Un gancho editado");
    expect(screen.getByDisplayValue("Un gancho editado")).toBeInTheDocument();
    expect(api.videos.createJob).not.toHaveBeenCalled();
  });

  test.each([
    ["disabled", es.reason.disabled],
    ["unconfigured", es.reason.unconfigured],
    ["payment_required", es.reason.payment_required],
    ["quota_exhausted", es.reason.quota_exhausted],
  ] as const)("translates %s and keeps generation disabled", async (status, reason) => {
    api.videos.draftStoryboard.mockResolvedValue(
      storyboardDraft({ capability: { status, tier: "paid", message: null, fallback: "storyboard" } })
    );
    renderStep();
    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: es.confirm })).toBeDisabled();
    expect(api.videos.createJob).not.toHaveBeenCalled();
  });

  test("available capability shows the full preflight before confirmation", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));

    expect(await screen.findByText(es.preflightHeading)).toBeInTheDocument();
    expect(screen.getByLabelText(es.promptPreview)).toHaveValue(preflight().prompt_preview);
    expect(screen.getAllByText(storyboard.hook).length).toBeGreaterThan(0);
    expect(screen.getByText(es.capabilityAvailable)).toBeInTheDocument();
    expect(screen.getByText("1 unidad(es) de tu límite de video")).toBeInTheDocument();
    expect(screen.getByText("4 de 5")).toBeInTheDocument();
    expect(api.videos.createJob).not.toHaveBeenCalled();
  });

  test("duration choices are keyboard navigable radio controls", async () => {
    renderStep();
    const fiveSeconds = await screen.findByRole("radio", { name: es.durationLabels[5] });
    const tenSeconds = screen.getByRole("radio", { name: es.durationLabels[10] });

    fireEvent.keyDown(fiveSeconds, { key: "ArrowRight" });

    await waitFor(() => expect(tenSeconds).toHaveAttribute("aria-checked", "true"));
    expect(fiveSeconds).toHaveAttribute("aria-checked", "false");
  });

  test("uses the duration allowlist returned by the server without inventing options", async () => {
    api.videos.draftStoryboard.mockResolvedValue(
      storyboardDraft({
        allowed_durations: [7],
        storyboard: { ...storyboard, duration_seconds: 7 },
      })
    );
    renderStep();

    const offered = await screen.findAllByRole("radio");
    expect(offered).toHaveLength(1);
    expect(offered[0]).toHaveTextContent("7 segundos");
    expect(offered[0]).toHaveAttribute("aria-checked", "true");
  });

  test("editing any storyboard input after preflight retires the approval", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    expect(await screen.findByRole("button", { name: es.confirm })).toBeInTheDocument();

    await change(screen.getByLabelText(es.hook), "Hook cambiado");
    expect(screen.queryByRole("button", { name: es.confirm })).not.toBeInTheDocument();
    expect(screen.getByText(es.editedAfterPreflight)).toBeInTheDocument();

    await click(screen.getByRole("button", { name: es.preflight }));
    await waitFor(() => expect(api.videos.preflight).toHaveBeenCalledTimes(2));
    expect(api.videos.preflight.mock.calls[1]?.[0]?.storyboard.hook).toBe("Hook cambiado");
  });

  test("requires an explicit confirmation click before creating a job", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    expect(api.videos.createJob).not.toHaveBeenCalled();
    await click(screen.getByRole("button", { name: es.confirm }));
    await waitFor(() => expect(api.videos.createJob).toHaveBeenCalledTimes(1));
  });

  test("does not generate automatically on mount", async () => {
    renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    expect(api.videos.draftStoryboard).toHaveBeenCalledTimes(1);
    expect(api.assets.list).toHaveBeenCalledTimes(1);
    expect(api.videos.preflight).not.toHaveBeenCalled();
    expect(api.videos.createJob).not.toHaveBeenCalled();
  });

  test("polls progress and stops when the job reaches a terminal state", async () => {
    useTimers();
    api.videos.job
      .mockResolvedValueOnce(job({ status: "preparing" }))
      .mockResolvedValueOnce(
        job({
          status: "succeeded",
          asset_id: "asset-video-1",
          video_url: "/api/v1/videos/files/asset-video-1?expires=1790000000&signature=fresh",
          video_expires_at: "2030-01-01T00:00:00Z",
          completed_at: "2026-08-02T12:01:00Z",
        })
      );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    expect(await screen.findByText(es.status.queued)).toBeInTheDocument();
    await tick();
    expect(await screen.findByText(es.status.preparing)).toBeInTheDocument();
    await tick();
    expect(await screen.findByText(es.status.succeeded)).toBeInTheDocument();
    await tick(2);
    expect(api.videos.job).toHaveBeenCalledTimes(2);
  });

  test("cleans polling timers on unmount", async () => {
    useTimers();
    const view = renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    view.unmount();
    await tick(3);
    expect(api.videos.job).not.toHaveBeenCalled();
  });

  test("recovers the latest project job after a remount without creating another one", async () => {
    const view = renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    view.unmount();

    api.videos.latestJob.mockResolvedValue(job({ status: "preparing" }));
    renderStep();
    expect(await screen.findByText(es.recovered)).toBeInTheDocument();
    expect(api.videos.latestJob).toHaveBeenLastCalledWith("project-1");
    expect(screen.getByText(es.status.preparing)).toBeInTheDocument();
    expect(api.videos.createJob).not.toHaveBeenCalled();
  });

  test("renders a signed video URL without autoplay", async () => {
    useTimers();
    api.videos.job.mockResolvedValue(
      job({
        status: "succeeded",
        asset_id: "asset-video-1",
        video_url: "/api/v1/videos/files/asset-video-1?expires=1790000000&signature=fresh",
        video_expires_at: "2030-01-01T00:00:00Z",
        completed_at: "2026-08-02T12:01:00Z",
      })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    await screen.findByText(es.status.queued);
    await tick();

    const video = await screen.findByLabelText(es.videoAlt);
    expect(video.tagName).toBe("VIDEO");
    expect(video).toHaveAttribute(
      "src",
      "/api/v1/videos/files/asset-video-1?expires=1790000000&signature=fresh"
    );
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveAttribute("playsinline");
    expect(video).not.toHaveAttribute("autoplay");
  });

  test("refreshes an expired signed URL by reading the job, never by creating another", async () => {
    const expired = "/api/v1/videos/files/asset-video-1?expires=1&signature=old";
    const fresh = "/api/v1/videos/files/asset-video-1?expires=1790000000&signature=new";
    api.videos.createJob.mockResolvedValue(
      job({ status: "succeeded", asset_id: "asset-video-1", video_url: expired, video_expires_at: "2020-01-01T00:00:00Z" })
    );
    api.videos.job.mockResolvedValue(
      job({ status: "succeeded", asset_id: "asset-video-1", video_url: fresh, video_expires_at: "2030-01-01T00:00:00Z" })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    await waitFor(() => expect(api.videos.job).toHaveBeenCalledWith("video-job-1"));
    const video = await screen.findByLabelText(es.videoAlt);
    expect(video).toHaveAttribute("src", fresh);
    expect(video).not.toHaveAttribute("src", expired);
    expect(api.videos.createJob).toHaveBeenCalledTimes(1);
  });

  test("shows a safe error and retry starts a new preflight and idempotency key", async () => {
    useTimers();
    api.videos.job.mockResolvedValue(
      job({ status: "failed", safe_error: "No pudimos completar el video. Intenta de nuevo.", safe_error_code: "VIDEO_GENERATION_FAILED" })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    await screen.findByText(es.status.queued);
    await tick();
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos completar el video. Intenta de nuevo.");
    await click(screen.getByRole("button", { name: es.retry }));
    await waitFor(() => expect(api.videos.preflight).toHaveBeenCalledTimes(2));
    await click(screen.getByRole("button", { name: es.confirm }));
    await waitFor(() => expect(api.videos.createJob).toHaveBeenCalledTimes(2));
    expect(api.videos.createJob.mock.calls[0]?.[1]).toEqual({ idempotencyKey: "key-1" });
    expect(api.videos.createJob.mock.calls[1]?.[1]).toEqual({ idempotencyKey: "key-2" });
  });

  test("offers only owned image assets as optional source images", async () => {
    api.assets.list.mockResolvedValue([
      { id: "asset-1", asset_type: "image", url: "/image-1", created_at: "2026-08-01T00:00:00Z" },
      { id: "asset-2", asset_type: "document", url: "/document-2", created_at: "2026-08-01T00:00:00Z" },
    ]);
    renderStep();
    const select = await screen.findByLabelText(es.sourceHeading);
    expect(screen.getByRole("option", { name: "Imagen 1" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Imagen 2" })).not.toBeInTheDocument();
    await change(select, "asset-1");
    await click(screen.getByRole("button", { name: es.preflight }));
    await waitFor(() => expect(api.videos.preflight).toHaveBeenCalled());
    expect(api.videos.preflight.mock.calls[0]?.[0]?.source_asset_id).toBe("asset-1");
  });

  test("keeps Spanish, English and Portuguese video copy complete", () => {
    const keys = Object.keys(es);
    for (const locale of ["en", "pt"] as const) {
      const other = instagramFlowCopy[locale].video;
      expect(Object.keys(other)).toEqual(keys);
      expect(Object.keys(other.durationLabels)).toEqual(Object.keys(es.durationLabels));
      expect(Object.keys(other.reason)).toEqual(Object.keys(es.reason));
      expect(Object.keys(other.status)).toEqual(Object.keys(es.status));
      for (const value of Object.values(other)) {
        if (typeof value === "string") expect(value.length).toBeGreaterThan(0);
        else {
          for (const nested of Object.values(value)) expect(nested.length).toBeGreaterThan(0);
        }
      }
    }
  });

  test("has no basic accessibility violations", async () => {
    const { container } = renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    expect(screen.getByRole("radiogroup", { name: es.durationHeading })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: es.durationLabels[5] })).toHaveAttribute("aria-checked", "true");
    const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  test("contains no social publishing or scheduling controls", async () => {
    const { container } = renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    const text = container.textContent?.toLowerCase() ?? "";
    expect(text).not.toMatch(/publicar|programar|publish|schedule/);
    expect(screen.queryByRole("button", { name: /publicar|programar|publish|schedule/i })).not.toBeInTheDocument();
  });

  test("does not expose provider, model or provider job identifiers", async () => {
    const { container } = renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    const html = container.innerHTML.toLowerCase();
    expect(html).not.toContain("provider");
    expect(html).not.toContain("model");
    expect(html).not.toContain("provider_job_id");
  });

  test("does not write jobs, tokens or URLs to browser storage", async () => {
    const localSetItem = vi.spyOn(window.localStorage, "setItem");
    const sessionSetItem = vi.spyOn(window.sessionStorage, "setItem");
    renderStep();
    await screen.findByDisplayValue(storyboard.hook);
    expect(localSetItem).not.toHaveBeenCalled();
    expect(sessionSetItem).not.toHaveBeenCalled();
    localSetItem.mockRestore();
    sessionSetItem.mockRestore();
  });

  test("sends no model or provider fields in preflight or job bodies", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(screen.getByRole("button", { name: es.confirm }));
    const preflightBody = api.videos.preflight.mock.calls[0]?.[0] ?? {};
    const jobBody = api.videos.createJob.mock.calls[0]?.[0] ?? {};
    expect(preflightBody).not.toHaveProperty("model");
    expect(preflightBody).not.toHaveProperty("provider");
    expect(jobBody).not.toHaveProperty("model");
    expect(jobBody).not.toHaveProperty("provider");
    expect(JSON.stringify(preflightBody)).not.toContain("provider");
    expect(JSON.stringify(jobBody)).not.toContain("model");
  });
});
