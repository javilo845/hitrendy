"use client";

import type { ImageAspectRatio, ImageBudget } from "@/types/images";

/**
 * One image generation as the conversation sees it.
 *
 * The job itself is durable on the server; this is only what the chat needs to
 * show while it runs and once it lands, so it stays a plain value object.
 */
export interface ChatImage {
  state: "working" | "ready" | "failed";
  prompt: string;
  aspectRatio: ImageAspectRatio;
  /** Signed and short-lived: it is minted per read and never stored. */
  url?: string | null;
  message?: string;
  budget?: ImageBudget | null;
}

const ASPECT_LABEL: Record<ImageAspectRatio, string> = {
  "1:1": "Cuadrada (1:1)",
  "4:5": "Vertical (4:5)",
  "9:16": "Historia (9:16)",
};

export function GeneratedImageCard({ image }: { image: ChatImage }) {
  return (
    <figure className="generated-image-card" data-state={image.state}>
      {image.state === "ready" && image.url ? (
        <>
          {/* A signed, short-lived URL from the API host: next/image would
              re-fetch it through the optimizer after it has expired. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image.url} alt={image.prompt} />
          <figcaption>
            <span>{ASPECT_LABEL[image.aspectRatio]}</span>
            <a href={image.url} target="_blank" rel="noreferrer">
              Abrir en tamaño completo
            </a>
          </figcaption>
        </>
      ) : image.state === "working" ? (
        <div className="generated-image-pending" role="status">
          <span className="generated-image-spinner" aria-hidden="true" />
          <p>{image.message || "Generando la imagen…"}</p>
        </div>
      ) : (
        <p className="generated-image-error" role="alert">
          {image.message || "No pudimos generar la imagen."}
        </p>
      )}
      {image.budget ? (
        <p className="generated-image-budget">
          Te quedan {image.budget.remaining} de {image.budget.total} imágenes hoy.
        </p>
      ) : null}
    </figure>
  );
}
