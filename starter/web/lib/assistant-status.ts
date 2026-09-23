import type { PublicCapabilities } from "@/types/capabilities";

export type AssistantTone = "checking" | "ok" | "warning" | "error";

export interface AssistantStatus {
  tone: AssistantTone;
  /** Short line shown in the Studio header. */
  label: string;
  /** Longer reason, surfaced as the element's title when the server sends one. */
  detail?: string;
}

/** Before the first answer comes back we do not know anything yet. */
export const ASSISTANT_STATUS_CHECKING: AssistantStatus = {
  tone: "checking",
  label: "Comprobando el asistente…",
};

/** The capabilities call itself failed, so the backend is what is unreachable. */
export const ASSISTANT_STATUS_UNREACHABLE: AssistantStatus = {
  tone: "error",
  label: "Asistente sin conexión",
  detail: "No pudimos consultar el estado del asistente.",
};

/**
 * Turns the capability snapshot into the one line the Studio header shows.
 *
 * `advisor` is the assistant's brain: without it the conversation cannot answer
 * at all, so it decides the tone. `vision_review` only powers the image audit,
 * which is a degraded state rather than an outage — the user can still write.
 * The wording never claims more than the snapshot says, which is the point:
 * the indicator used to be a hardcoded "Asistente disponible".
 */
export function assistantStatusFrom(
  capabilities: PublicCapabilities
): AssistantStatus {
  const advisor = capabilities?.advisor;
  const vision = capabilities?.vision_review;

  if (!advisor) return ASSISTANT_STATUS_UNREACHABLE;

  if (advisor.status !== "available") {
    const detail = advisor.message || undefined;
    if (advisor.status === "degraded")
      return {
        tone: "warning",
        label: "Asistente con capacidad reducida",
        detail,
      };
    if (advisor.status === "quota_exhausted")
      return { tone: "error", label: "Asistente sin cuota disponible", detail };
    if (advisor.status === "payment_required")
      return {
        tone: "error",
        label: "Asistente sin presupuesto habilitado",
        detail,
      };
    return { tone: "error", label: "Asistente no disponible", detail };
  }

  if (vision?.status === "available")
    return { tone: "ok", label: "Asistente disponible" };

  if (vision?.status === "degraded")
    return {
      tone: "warning",
      label: "Asistente disponible · análisis visual reducido",
      detail: vision.message || undefined,
    };

  return {
    tone: "warning",
    label: "Asistente disponible · sin análisis de imágenes",
    detail:
      vision?.message ||
      "La revisión visual no está disponible en este momento.",
  };
}
