import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GeneratedVideoScriptCard } from "@/components/generated-video-script-card";

describe("GeneratedVideoScriptCard", () => {
  it("renders an ordered, actionable short-video draft", () => {
    render(
      <GeneratedVideoScriptCard
        artifact={{
          artifact_type: "short_video_script",
          platform: "tiktok",
          hook: "Una pausa fría para tu día",
          duration_seconds: 20,
          scenes: [
            {
              order: 1,
              duration_seconds: 5,
              visual: "Primer plano del café.",
              on_screen_text: "Café frío",
              voiceover: "Conoce nuestra pausa fría.",
            },
            {
              order: 2,
              duration_seconds: 15,
              visual: "Una persona disfruta el café.",
              on_screen_text: "Conócelo hoy",
              voiceover: "Visítanos hoy.",
            },
          ],
          call_to_action: "Visítanos hoy.",
          caption: "Conoce nuestro café frío.",
          assumptions: [],
        }}
      />
    );

    expect(screen.getByRole("heading", { name: "Una pausa fría para tu día" })).toBeInTheDocument();
    expect(screen.getByText("Escena 1 · 5 seg")).toBeInTheDocument();
    expect(screen.getByText("Caption sugerido")).toBeInTheDocument();
    expect(screen.getByText("Guion generado como borrador.", { exact: false })).toBeInTheDocument();
  });

  it("copies the full script", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(
      <GeneratedVideoScriptCard
        artifact={{
          artifact_type: "short_video_script",
          platform: "tiktok",
          hook: "Una pausa fría para tu día",
          duration_seconds: 20,
          scenes: [
            { order: 1, duration_seconds: 5, visual: "Café.", on_screen_text: "Café", voiceover: "Conoce." },
            { order: 2, duration_seconds: 15, visual: "Persona.", on_screen_text: "Hoy", voiceover: "Visítanos." },
          ],
          call_to_action: "Visítanos hoy.",
          caption: "Conoce nuestro café frío.",
          assumptions: [],
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Copiar guion" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toHaveTextContent("Guion copiado.");
  });
});
