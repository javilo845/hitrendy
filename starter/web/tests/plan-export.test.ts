import { describe, expect, test } from "vitest";

import { buildPlanDocument, planFileName } from "@/lib/plan-export";

const advisor = {
  summary: "Publica tres veces por semana.",
  recommendations: [
    {
      title: "Reel de producto",
      description: "Muestra el café frío en preparación.",
      priority: "high" as const,
    },
  ],
  next_actions: ["Grabar el reel el lunes"],
};

describe("buildPlanDocument", () => {
  test("carries the whole plan into the printable sheet", () => {
    const html = buildPlanDocument(advisor, {
      date: new Date("2026-09-01T12:00:00Z"),
    });
    expect(html).toContain("Publica tres veces por semana.");
    expect(html).toContain("Reel de producto");
    expect(html).toContain("Alta prioridad");
    expect(html).toContain("Grabar el reel el lunes");
    expect(html).toContain("2026");
  });

  test("escapes model output instead of injecting it as markup", () => {
    const html = buildPlanDocument({
      ...advisor,
      summary: '<script>alert("x")</script>',
    });
    expect(html).not.toContain("<script>alert");
    expect(html).toContain("&lt;script&gt;");
  });

  test("omits the empty sections rather than printing bare headings", () => {
    const html = buildPlanDocument({
      summary: "Solo un resumen.",
      recommendations: [],
      next_actions: [],
    });
    expect(html).not.toContain("Próximos pasos");
    expect(html).not.toContain("Ideas y publicaciones");
  });

  test("names the file by the day it was produced", () => {
    expect(planFileName(new Date("2026-09-01T12:00:00Z"))).toBe(
      "plan-de-contenido-2026-09-01"
    );
  });
});
