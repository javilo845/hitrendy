import { ApiError, api, createIdempotencyKey } from "@/lib/api";
import {
  isTerminalImageJob,
  type ImageAspectRatio,
  type ImageBudget,
  type ImageJob,
} from "@/types/images";

/** The job is durable server-side, so giving up here costs nothing. */
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 45;

/** The formats the product offers; the feed post is the one it defaults to. */
export const DEFAULT_ASPECT_RATIO: ImageAspectRatio = "4:5";

export interface ImageRunResult {
  url: string | null;
  budget: ImageBudget | null;
  jobId: string;
}

/**
 * A refusal the user is meant to read: no budget left, capability down, or a
 * job that ended without an image. It never carries a provider detail.
 */
export class ImageGenerationError extends Error {}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

/**
 * Runs the whole documented sequence for one image: draft the brief, preflight
 * it, confirm it, then watch the durable job.
 *
 * The steps are not collapsed. Preflight is what authorizes the spend and what
 * reports the remaining allowance, and confirming without it would be sending
 * an unsigned request the server would refuse anyway.
 */
export async function runImageGeneration(
  prompt: string,
  {
    businessId,
    aspectRatio = DEFAULT_ASPECT_RATIO,
    signal,
    onProgress,
  }: {
    businessId: string;
    aspectRatio?: ImageAspectRatio;
    signal?: AbortSignal;
    onProgress?: (label: string) => void;
  }
): Promise<ImageRunResult> {
  onProgress?.("Preparando la descripción visual…");
  const draft = await api.images.draftBrief({
    business_id: businessId,
    publication_text: prompt,
  });

  // What the user wrote is the subject of the image; the rest of the brief is
  // whatever the server derived from the business, unedited.
  const brief = { ...draft.brief, subject: prompt.slice(0, 240) };

  onProgress?.("Confirmando el consumo del día…");
  const preflight = await api.images.preflight({ brief, aspect_ratio: aspectRatio });
  if (!preflight.allowed || !preflight.approval_token) {
    throw new ImageGenerationError(
      preflight.message || "No podemos generar imágenes en este momento."
    );
  }

  onProgress?.("Generando la imagen…");
  let job: ImageJob = await api.images.createJob(
    {
      brief: preflight.brief,
      aspect_ratio: preflight.aspect_ratio,
      approval_token: preflight.approval_token,
      confirmed: true,
    },
    { idempotencyKey: createIdempotencyKey() }
  );

  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
    if (isTerminalImageJob(job.status)) break;
    await wait(POLL_INTERVAL_MS, signal);
    job = await api.images.job(job.id);
  }

  if (job.status === "succeeded") {
    return {
      url: job.image_url ?? null,
      budget: preflight.budget ?? null,
      jobId: job.id,
    };
  }

  if (!isTerminalImageJob(job.status)) {
    throw new ImageGenerationError(
      "La imagen está tardando más de lo normal. Sigue generándose y aparecerá en tu biblioteca."
    );
  }

  throw new ImageGenerationError(
    job.error || "No pudimos generar la imagen. Inténtalo de nuevo."
  );
}

/** The message to show for a failure, without leaking transport detail. */
export function imageGenerationMessage(reason: unknown): string {
  if (reason instanceof ImageGenerationError) return reason.message;
  if (reason instanceof ApiError) return reason.message;
  return "No pudimos generar la imagen. Inténtalo de nuevo.";
}
