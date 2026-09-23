import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { axe } from "vitest-axe";

const mocks = vi.hoisted(() => ({
  api: {
    assets: { list: vi.fn() },
    images: {
      draftBrief: vi.fn(),
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

import { ImageGenerationStep } from "@/components/studio/image-generation-step";
import { instagramFlowCopy } from "@/lib/instagram-flow-copy";

const es = instagramFlowCopy.es.image;

/**
 * Fixtures copied from the backend contracts, field for field.
 *
 * `POST /images/brief`, `POST /images/preflight`, `POST /images/jobs` and
 * `GET /images/jobs/{id}` each have exactly these keys; a job only carries
 * `image_url` and `image_expires_at` when it was read back, never when created.
 */
const brief = {
  subject: "Taza de café de altura",
  setting: "Barra de madera junto a la ventana",
  style: "Fotografía natural",
  palette: "Tonos cálidos y madera",
  mood: "Cercano y matinal",
  avoid: "Texto sobre la imagen",
};

const budget = { remaining: 4, total: 5, next_reset_at: "2026-08-01T00:00:00Z" };
const available = { status: "available", tier: "paid", message: null, fallback: null };

function briefDraft(overrides: Record<string, unknown> = {}) {
  return {
    brief,
    aspect_ratios: ["1:1", "4:5", "9:16"],
    capability: available,
    budget,
    ...overrides,
  };
}

function preflight(overrides: Record<string, unknown> = {}) {
  return {
    allowed: true,
    aspect_ratio: "4:5",
    brief,
    prompt_preview: "Taza de café de altura. Barra de madera junto a la ventana.",
    negative_prompt_preview: "Texto sobre la imagen",
    reference_asset_id: null,
    budget,
    reason_code: null,
    message: null,
    approval_token: "approval-token-1",
    approval_expires_at: "2026-07-31T12:05:00Z",
    capability: available,
    ...overrides,
  };
}

function job(overrides: Record<string, unknown> = {}) {
  return {
    id: "img_job_1",
    status: "queued",
    aspect_ratio: "4:5",
    asset_id: null,
    reference_asset_id: null,
    error: null,
    error_code: null,
    created_at: "2026-07-31T12:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

/**
 * The step as the flow mounts it: with a saved post behind it.
 *
 * The project id is not decoration. It is the durable parent a generation is
 * recovered through, and the component refuses to spend without one, so a suite
 * that omitted it would only ever exercise the blocked path.
 */
function renderStep(props: Record<string, unknown> = {}) {
  return render(
    <ImageGenerationStep
      businessId="business-1"
      copy={es}
      publicationText="Caption inicial"
      projectId="project-1"
      {...props}
    />
  );
}

/**
 * Click, and let the request it starts settle inside `act`.
 *
 * Every button here begins an async call, so the state it produces lands after
 * the click returns. Awaiting within `act` keeps that update inside the scope
 * React was told about, which is what keeps the suite free of `act(...)`
 * warnings instead of merely quiet about them.
 */
async function click(element: HTMLElement) {
  await act(async () => {
    fireEvent.click(element);
  });
}

/** The same, for a typed edit that retires an approval. */
async function change(element: HTMLElement, value: string) {
  await act(async () => {
    fireEvent.change(element, { target: { value } });
  });
}

/**
 * Fake timers that still tick in real time.
 *
 * The poller sleeps two seconds between reads, which no suite should sit
 * through, but Testing Library's own waiting helpers need the clock to keep
 * moving. `shouldAdvanceTime` gives us both: `tick` jumps the poll forward and
 * `findBy*` still resolves normally.
 */
function useTimers() {
  vi.useFakeTimers({ shouldAdvanceTime: true });
}

/** Drive the bounded poller forward one tick at a time. */
async function tick(times = 1) {
  for (let index = 0; index < times; index += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
  }
}

beforeEach(() => {
  mocks.keys = 0;
  api.assets.list.mockReset().mockResolvedValue([]);
  api.images.draftBrief.mockReset().mockResolvedValue(briefDraft());
  api.images.preflight.mockReset().mockResolvedValue(preflight());
  api.images.createJob.mockReset().mockResolvedValue(job());
  api.images.job.mockReset().mockResolvedValue(job());
  // Nothing to recover unless a test says so: a fresh post has no earlier job.
  api.images.latestJob.mockReset().mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ImageGenerationStep", () => {
  test("draws the editable visual brief without generating anything", async () => {
    renderStep({ trendTitle: "Café frío local" });
    expect(await screen.findByDisplayValue(brief.subject)).toBeInTheDocument();
    expect(api.images.draftBrief).toHaveBeenCalledWith({
      business_id: "business-1",
      publication_text: "Caption inicial",
      trend_title: "Café frío local",
    });
    for (const value of Object.values(brief)) {
      expect(screen.getByDisplayValue(value)).toBeInTheDocument();
    }
    expect(api.images.preflight).not.toHaveBeenCalled();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("a trend title only supplies context and never starts a generation", async () => {
    renderStep({ trendTitle: "Café frío local" });
    await screen.findByDisplayValue(brief.subject);
    expect(api.images.draftBrief.mock.calls[0]?.[0]?.trend_title).toBe("Café frío local");
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("edits to the brief travel to preflight and retire an earlier approval", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await screen.findByRole("button", { name: es.confirm });

    await change(screen.getByLabelText(es.subject), "Latte con arte");
    expect(screen.queryByRole("button", { name: es.confirm })).not.toBeInTheDocument();
    expect(screen.getByText(es.editedAfterPreflight)).toBeInTheDocument();

    await click(screen.getByRole("button", { name: es.preflight }));
    await waitFor(() => expect(api.images.preflight).toHaveBeenCalledTimes(2));
    expect(api.images.preflight.mock.calls[1]?.[0]?.brief.subject).toBe("Latte con arte");
  });

  test.each([
    ["1:1", es.ratioLabels["1:1"]],
    ["4:5", es.ratioLabels["4:5"]],
    ["9:16", es.ratioLabels["9:16"]],
  ])("offers %s and preflights exactly that format", async (ratio, label) => {
    renderStep();
    const option = await screen.findByRole("radio", { name: label });
    await click(option);
    expect(option).toHaveAttribute("aria-checked", "true");
    await click(screen.getByRole("button", { name: es.preflight }));
    await waitFor(() => expect(api.images.preflight).toHaveBeenCalled());
    expect(api.images.preflight.mock.calls[0]?.[0]?.aspect_ratio).toBe(ratio);
  });

  test("only offers the three formats the server allows", async () => {
    renderStep();
    await screen.findByDisplayValue(brief.subject);
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  test("sends a reference by id only, chosen from images the workspace already owns", async () => {
    api.assets.list.mockResolvedValue([
      { id: "asset-1", original_name: "fachada.jpg", asset_type: "image" },
      { id: "asset-2", original_name: "guion.txt", asset_type: "document" },
    ]);
    renderStep();
    const select = await screen.findByLabelText(es.referenceHeading);
    expect(screen.getByRole("option", { name: "fachada.jpg" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "guion.txt" })).not.toBeInTheDocument();

    await change(select, "asset-1");
    await click(screen.getByRole("button", { name: es.preflight }));
    await waitFor(() => expect(api.images.preflight).toHaveBeenCalled());
    const sent = api.images.preflight.mock.calls[0]?.[0];
    expect(sent?.reference_asset_id).toBe("asset-1");
    expect(JSON.stringify(sent)).not.toContain("http");
  });

  test("preflight shows the cost and the remaining budget before anything is spent", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    expect(await screen.findByText(es.costValue)).toBeInTheDocument();
    expect(screen.getByText("4 de 5")).toBeInTheDocument();
    expect(screen.getByDisplayValue(preflight().prompt_preview)).toBeInTheDocument();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("only an explicit confirmation enqueues the job, and a double click enqueues one", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    const confirm = await screen.findByRole("button", { name: es.confirm });
    // Both clicks land before the first request can answer, which is exactly the
    // impatient double click that must not buy two images.
    await act(async () => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });
    await waitFor(() => expect(api.images.createJob).toHaveBeenCalledTimes(1));
    const [payload, options] = api.images.createJob.mock.calls[0] ?? [];
    expect(payload).toMatchObject({
      aspect_ratio: "4:5",
      approval_token: "approval-token-1",
      confirmed: true,
      reference_asset_id: null,
      project_id: "project-1",
    });
    expect(options).toEqual({ idempotencyKey: "key-1" });
  });

  test("what will be avoided is shown for approval, not only what will be drawn", async () => {
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await screen.findByRole("button", { name: es.confirm });
    // The negative half is signed with the rest, so it has to be visible before
    // the confirmation, in its own field and not buried in the prompt.
    const avoidPreview = screen.getByLabelText(es.avoidPreview);
    expect(avoidPreview).toHaveValue("Texto sobre la imagen");
    expect(avoidPreview).toHaveAttribute("readonly");
    expect(screen.getByText(es.avoidPreview)).toBeInTheDocument();
  });

  test("an empty avoid field says so instead of showing a blank approval", async () => {
    api.images.preflight.mockResolvedValue(preflight({ negative_prompt_preview: null }));
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await screen.findByRole("button", { name: es.confirm });
    const avoidPreview = screen.getByLabelText(es.avoidPreview);
    expect(avoidPreview).toHaveValue(es.avoidPreviewNone);
    expect(avoidPreview).toHaveAttribute("readonly");
  });

  test("an unsaved post cannot be charged for an image", async () => {
    renderStep({ projectId: null });
    await click(await screen.findByRole("button", { name: es.preflight }));
    const confirm = await screen.findByRole("button", { name: es.confirm });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(es.savePostFirst)).toBeInTheDocument();

    await click(confirm);
    // No durable parent means no way back after a reload, so nothing is spent.
    expect(api.images.createJob).not.toHaveBeenCalled();
    expect(api.images.latestJob).not.toHaveBeenCalled();
  });

  test("a disabled capability keeps the brief and hides the paid path", async () => {
    api.images.draftBrief.mockResolvedValue(
      briefDraft({
        capability: { status: "disabled", tier: "paid", message: null, fallback: "visual_brief" },
      })
    );
    renderStep();
    expect(await screen.findByText(es.reason.disabled)).toBeInTheDocument();
    expect(screen.getByText(es.fallbackHint)).toBeInTheDocument();
    expect(screen.getByDisplayValue(brief.subject)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: es.preflight })).not.toBeInTheDocument();
  });

  test("an unconfigured provider is explained instead of failing later", async () => {
    api.images.draftBrief.mockResolvedValue(
      briefDraft({
        capability: {
          status: "unconfigured",
          tier: "paid",
          message: null,
          fallback: "visual_brief",
        },
      })
    );
    renderStep();
    expect(await screen.findByText(es.reason.unconfigured)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: es.preflight })).not.toBeInTheDocument();
  });

  test("an exhausted daily budget blocks the generation and says when it returns", async () => {
    api.images.draftBrief.mockResolvedValue(
      briefDraft({ budget: { remaining: 0, total: 5, next_reset_at: "2026-08-01T00:00:00Z" } })
    );
    renderStep();
    expect(await screen.findByText(es.reason.quota_exhausted)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: es.preflight })).not.toBeInTheDocument();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("a provider payment failure is reported as a provider state, not as a user error", async () => {
    api.images.draftBrief.mockResolvedValue(
      briefDraft({
        capability: {
          status: "payment_required",
          tier: "paid",
          message: null,
          fallback: "visual_brief",
        },
      })
    );
    renderStep();
    expect(await screen.findByText(es.reason.payment_required)).toBeInTheDocument();
    expect(screen.getByText(es.fallbackHeading)).toBeInTheDocument();
  });

  test("a refused preflight explains itself and offers no confirmation", async () => {
    api.images.preflight.mockResolvedValue(
      preflight({
        allowed: false,
        reason_code: "quota_exhausted",
        message: "Alcanzaste el límite de imágenes de hoy.",
        approval_token: null,
        approval_expires_at: null,
      })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    expect(await screen.findByText("Alcanzaste el límite de imágenes de hoy.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: es.confirm })).not.toBeInTheDocument();
  });

  test("a queued job is announced and polled at a calm pace", async () => {
    useTimers();
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    expect(await screen.findByText(es.statusQueued)).toBeInTheDocument();
    expect(api.images.job).not.toHaveBeenCalled();
    await tick();
    expect(api.images.job).toHaveBeenCalledWith("img_job_1");
    expect(api.images.job).toHaveBeenCalledTimes(1);
  });

  test("a running job reports progress and keeps polling", async () => {
    useTimers();
    api.images.job.mockResolvedValue(job({ status: "running" }));
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    expect(await screen.findByText(es.statusRunning)).toBeInTheDocument();
    await tick();
    expect(api.images.job).toHaveBeenCalledTimes(2);
  });

  test("a completed job shows the signed image and describes it without a fake editor", async () => {
    useTimers();
    api.images.job.mockResolvedValue(
      job({
        status: "succeeded",
        asset_id: "asset-generated-1",
        completed_at: "2026-07-31T12:01:00Z",
        image_url:
          "/api/v1/images/files/asset-generated-1?workspace=ws_1&expires=1785000000&signature=abc",
        image_expires_at: "2026-07-31T12:10:00Z",
      })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    expect(await screen.findByText(es.statusSucceeded)).toBeInTheDocument();

    const image = screen.getByRole("img");
    expect(image).toHaveAttribute(
      "src",
      "/api/v1/images/files/asset-generated-1?workspace=ws_1&expires=1785000000&signature=abc"
    );
    expect(image).toHaveAttribute("alt", `${brief.subject}. ${brief.setting}`);
    // The description comes from the brief and is stated as such. No contract
    // stores a second one, so there is no field pretending to save it.
    expect(screen.getByText(es.altNote)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: es.altNote })).not.toBeInTheDocument();
    expect(screen.getByText(es.linkExpires)).toBeInTheDocument();

    // Editing the brief moves the description with it, because it is the source.
    await change(screen.getByLabelText(es.subject), "Café servido");
    expect(screen.getByRole("img")).toHaveAttribute(
      "alt",
      `Café servido. ${brief.setting}`
    );

    // The link is never a provider URL and never inline bytes.
    const src = image.getAttribute("src") || "";
    expect(src.startsWith("/api/v1/images/files/")).toBe(true);
    expect(src).not.toContain("data:");
  });

  test("an expired link is renewed by re-reading the job, never by generating again", async () => {
    useTimers();
    const succeeded = job({
      status: "succeeded",
      asset_id: "asset-generated-1",
      completed_at: "2026-07-31T12:01:00Z",
      image_url: "/api/v1/images/files/asset-generated-1?expires=1785000000&signature=old",
      image_expires_at: "2026-07-31T12:10:00Z",
    });
    api.images.job.mockResolvedValue(succeeded);
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    await screen.findByText(es.statusSucceeded);

    api.images.job.mockResolvedValue({
      ...succeeded,
      image_url: "/api/v1/images/files/asset-generated-1?expires=1785000600&signature=new",
    });
    await click(screen.getByRole("button", { name: es.refreshLink }));
    await waitFor(() =>
      expect(screen.getByRole("img")).toHaveAttribute(
        "src",
        "/api/v1/images/files/asset-generated-1?expires=1785000600&signature=new"
      )
    );
    // A fresh link is a read. It never re-enqueues and never re-preflights.
    expect(api.images.createJob).toHaveBeenCalledTimes(1);
    expect(api.images.preflight).toHaveBeenCalledTimes(1);
  });

  test("remounting after a reload recovers the job instead of buying a second image", async () => {
    useTimers();
    const view = renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    expect(api.images.createJob).toHaveBeenCalledTimes(1);

    // The page goes away with the job id; the job stays on the server.
    view.unmount();

    api.images.latestJob.mockResolvedValue(job({ status: "running" }));
    renderStep();
    expect(await screen.findByText(es.recovered)).toBeInTheDocument();
    expect(api.images.latestJob).toHaveBeenLastCalledWith("project-1");
    expect(screen.getByText(es.statusRunning)).toBeInTheDocument();
    // Recovery is a read: no second confirmation and no second charge.
    expect(api.images.createJob).toHaveBeenCalledTimes(1);

    // And the recovered job resumes its poll rather than sitting frozen.
    api.images.job.mockResolvedValue(
      job({
        status: "succeeded",
        asset_id: "asset-generated-1",
        image_url: "/api/v1/images/files/asset-generated-1?signature=abc",
      })
    );
    await tick();
    expect(await screen.findByText(es.statusSucceeded)).toBeInTheDocument();
    expect(api.images.createJob).toHaveBeenCalledTimes(1);
  });

  test("a job still inside the provider is announced as paid-for and offers no retry", async () => {
    useTimers();
    api.images.latestJob.mockResolvedValue(job({ status: "provider_started" }));
    renderStep();
    expect(await screen.findByText(es.statusProviderStarted)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: es.retry })).not.toBeInTheDocument();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("a failed recovery leaves the step usable and still spends nothing", async () => {
    const { ApiError } = await import("@/lib/api");
    api.images.latestJob.mockRejectedValue(
      new ApiError(503, "SERVICE_UNAVAILABLE", "No pudimos consultar el trabajo.", true)
    );
    renderStep();
    expect(await screen.findByDisplayValue(brief.subject)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: es.preflight })).toBeInTheDocument();
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("polling stops once the job is finished", async () => {
    useTimers();
    api.images.job.mockResolvedValue(job({ status: "succeeded", asset_id: "asset-1", image_url: "/api/v1/images/files/asset-1?signature=abc" }));
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick(4);
    expect(api.images.job).toHaveBeenCalledTimes(1);
  });

  test("a provider failure is surfaced with the server message and a retry", async () => {
    useTimers();
    api.images.job.mockResolvedValue(
      job({
        status: "failed",
        error: "No pudimos generar la imagen. Intenta de nuevo.",
        error_code: "IMAGE_PROVIDER_ERROR",
        completed_at: "2026-07-31T12:01:00Z",
      })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    expect(await screen.findByText(es.statusFailed)).toBeInTheDocument();
    expect(screen.getByText("No pudimos generar la imagen. Intenta de nuevo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: es.retry })).toBeInTheDocument();
  });

  test("a storage failure is reported as a failure, never as a finished image", async () => {
    useTimers();
    api.images.job.mockResolvedValue(
      job({
        status: "failed",
        error: "No pudimos guardar la imagen generada.",
        error_code: "IMAGE_STORAGE_ERROR",
        asset_id: null,
        completed_at: "2026-07-31T12:01:00Z",
      })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    expect(await screen.findByText(es.statusFailed)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText(es.statusSucceeded)).not.toBeInTheDocument();
  });

  test("retrying takes a fresh preflight and a fresh idempotency key", async () => {
    useTimers();
    api.images.job.mockResolvedValue(
      job({ status: "failed", error: "Falló la generación.", error_code: "IMAGE_PROVIDER_ERROR" })
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    await tick();
    await click(await screen.findByRole("button", { name: es.retry }));
    await waitFor(() => expect(api.images.preflight).toHaveBeenCalledTimes(2));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await waitFor(() => expect(api.images.createJob).toHaveBeenCalledTimes(2));
    expect(api.images.createJob.mock.calls[0]?.[1]).toEqual({ idempotencyKey: "key-1" });
    expect(api.images.createJob.mock.calls[1]?.[1]).toEqual({ idempotencyKey: "key-2" });
  });

  test("unmounting cancels the poll instead of leaving a timer behind", async () => {
    useTimers();
    const view = renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    await screen.findByText(es.statusQueued);
    view.unmount();
    await tick(5);
    expect(api.images.job).not.toHaveBeenCalled();
  });

  test("renders every string from the catalogue in en and pt as well", async () => {
    const keys = Object.keys(es);
    for (const locale of ["en", "pt"] as const) {
      const other = instagramFlowCopy[locale].image;
      expect(Object.keys(other)).toEqual(keys);
      expect(Object.keys(other.ratioLabels)).toEqual(Object.keys(es.ratioLabels));
      expect(Object.keys(other.reason)).toEqual(Object.keys(es.reason));
      expect(
        Object.values(other).every((value) =>
          typeof value === "string" ? value.length > 0 : Object.values(value).every(Boolean)
        )
      ).toBe(true);
    }

    const en = instagramFlowCopy.en.image;
    renderStep({ copy: en });
    expect(await screen.findByRole("heading", { name: en.heading })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: en.ratioLabels["9:16"] })).toBeInTheDocument();
    expect(screen.getByLabelText(en.subject)).toBeInTheDocument();
  });

  test("has no basic accessibility violations, with honest labels and states", async () => {
    const { container } = renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await screen.findByRole("button", { name: es.confirm });

    // Every control is reachable by its visible name, and the format group
    // reports its own selection rather than relying on colour alone.
    expect(screen.getByRole("radiogroup", { name: es.formatHeading })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: es.ratioLabels["4:5"] })).toHaveAttribute(
      "aria-checked",
      "true"
    );
    expect(screen.getByRole("radio", { name: es.ratioLabels["1:1"] })).toHaveAttribute(
      "aria-checked",
      "false"
    );

    const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  test("lays every panel out in a single column that cannot overflow sideways", async () => {
    const { container } = renderStep();
    await screen.findByDisplayValue(brief.subject);
    // The step is a grid of full-width panels: nothing is absolutely positioned
    // or given a fixed pixel width, so a narrow viewport wraps instead of
    // scrolling. The generated image is capped by `max-width`, never by px.
    for (const element of Array.from(container.querySelectorAll<HTMLElement>("*"))) {
      expect(element.style.width).not.toMatch(/px$/);
      expect(element.style.position).not.toBe("absolute");
    }
    expect(container.querySelector(".image-step")).toBeInTheDocument();
    expect(container.querySelector(".image-brief")).toBeInTheDocument();
  });

  test("a failed brief keeps the step usable and never spends", async () => {
    const { ApiError } = await import("@/lib/api");
    api.images.draftBrief.mockRejectedValue(
      new ApiError(503, "CAPABILITY_UNAVAILABLE", "La generación de imágenes no está disponible.", false)
    );
    renderStep();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La generación de imágenes no está disponible."
    );
    expect(api.images.createJob).not.toHaveBeenCalled();
  });

  test("a rejected confirmation surfaces the reason and frees the key for a new attempt", async () => {
    const { ApiError } = await import("@/lib/api");
    api.images.createJob.mockRejectedValueOnce(
      new ApiError(429, "IMAGE_QUOTA_EXHAUSTED", "Alcanzaste el límite de imágenes de hoy.", false)
    );
    renderStep();
    await click(await screen.findByRole("button", { name: es.preflight }));
    await click(await screen.findByRole("button", { name: es.confirm }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Alcanzaste el límite de imágenes de hoy."
    );
    await click(screen.getByRole("button", { name: es.confirm }));
    await waitFor(() => expect(api.images.createJob).toHaveBeenCalledTimes(2));
    expect(api.images.createJob.mock.calls[1]?.[1]).toEqual({ idempotencyKey: "key-2" });
  });
});
