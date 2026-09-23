import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import {
  VisualReviewCard,
  type VisualAnalysis,
} from "@/components/visual-review-card";

function analysis(overrides: Partial<VisualAnalysis> = {}): VisualAnalysis {
  return {
    id: "an_1",
    summary: "La pieza comunica, pero pierde jerarquía.",
    strengths: ["Color coherente"],
    improvements: [],
    revised_copy: null,
    accessibility_notes: [],
    ...overrides,
  };
}

afterEach(cleanup);

describe("tarjeta de auditoría visual", () => {
  test("dibuja la portada del nicho cuando Canva no entrega miniatura", () => {
    render(
      <VisualReviewCard
        analysis={analysis({
          canva_templates: [
            {
              title: "Rutina semanal",
              canva_url: "https://www.canva.com/templates/EAF-rutina/",
              cover: "fitness",
            },
          ],
        })}
      />
    );

    const cover = screen.getByRole("img", {
      name: "Portada de Fitness: Rutina semanal",
    });
    expect(cover).toHaveAttribute("data-cover", "fitness");
    expect(screen.queryByText("◫")).not.toBeInTheDocument();
  });

  test("conserva la miniatura cuando Canva sí la entrega", () => {
    const { container } = render(
      <VisualReviewCard
        analysis={analysis({
          canva_templates: [
            {
              title: "Rutina semanal",
              canva_url: "https://www.canva.com/templates/EAF-rutina/",
              thumbnail_url: "https://images.example.test/rutina.png",
            },
          ],
        })}
      />
    );

    expect(container.querySelector(".review-template-thumb img")).toHaveAttribute(
      "src",
      "https://images.example.test/rutina.png"
    );
    expect(container.querySelector(".template-cover")).toBeNull();
  });

  test("usa la portada neutra cuando el nicho no se reconoce", () => {
    render(
      <VisualReviewCard
        analysis={analysis({
          canva_templates: [
            {
              title: "Pieza sin nicho",
              canva_url: "https://www.canva.com/templates/EAF-otra/",
              cover: "criptomonedas",
            },
          ],
        })}
      />
    );

    expect(
      screen.getByRole("img", { name: "Portada de Plantilla: Pieza sin nicho" })
    ).toHaveAttribute("data-cover", "default");
  });
});
