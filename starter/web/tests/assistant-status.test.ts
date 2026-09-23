import { describe, expect, test } from "vitest";

import { assistantStatusFrom } from "@/lib/assistant-status";
import type { PublicCapabilities, PublicCapability } from "@/types/capabilities";

function capability(
  status: PublicCapability["status"],
  message?: string
): PublicCapability {
  return {
    status,
    tier: "free",
    quality_levels: status === "available" ? ["fast"] : [],
    ...(message ? { message } : {}),
  };
}

function snapshot(
  advisor: PublicCapability,
  vision: PublicCapability
): PublicCapabilities {
  return {
    advisor,
    copywriter: advisor,
    vision_review: vision,
    image_generation: capability("disabled"),
    video_generation: capability("disabled"),
    trend_analysis: capability("available"),
  };
}

describe("assistantStatusFrom", () => {
  test("only claims availability when both capabilities are up", () => {
    const status = assistantStatusFrom(
      snapshot(capability("available"), capability("available"))
    );
    expect(status).toEqual({ tone: "ok", label: "Asistente disponible" });
  });

  test("warns instead of claiming full service when the visual review is down", () => {
    const status = assistantStatusFrom(
      snapshot(
        capability("available"),
        capability("unconfigured", "La revisión visual no está disponible.")
      )
    );
    expect(status.tone).toBe("warning");
    expect(status.label).toContain("sin análisis de imágenes");
    expect(status.detail).toBe("La revisión visual no está disponible.");
  });

  test("reports the advisor as unavailable and carries the server reason", () => {
    const status = assistantStatusFrom(
      snapshot(
        capability("unconfigured", "El asistente no está disponible."),
        capability("available")
      )
    );
    expect(status).toEqual({
      tone: "error",
      label: "Asistente no disponible",
      detail: "El asistente no está disponible.",
    });
  });

  test("distinguishes quota, payment and degraded states", () => {
    expect(
      assistantStatusFrom(
        snapshot(capability("quota_exhausted"), capability("available"))
      ).label
    ).toBe("Asistente sin cuota disponible");
    expect(
      assistantStatusFrom(
        snapshot(capability("payment_required"), capability("available"))
      ).label
    ).toBe("Asistente sin presupuesto habilitado");
    const degraded = assistantStatusFrom(
      snapshot(capability("degraded"), capability("available"))
    );
    expect(degraded.tone).toBe("warning");
    expect(degraded.label).toBe("Asistente con capacidad reducida");
  });

  test("treats a snapshot without an advisor entry as unreachable", () => {
    const status = assistantStatusFrom(
      {} as unknown as PublicCapabilities
    );
    expect(status.tone).toBe("error");
    expect(status.label).toBe("Asistente sin conexión");
  });
});
