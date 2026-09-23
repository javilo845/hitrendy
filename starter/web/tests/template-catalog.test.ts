import { describe, expect, test } from "vitest";

import {
  matchesTemplate,
  toTemplatePresentation,
} from "@/lib/template-catalog";
import type { Template } from "@/types/template";

const template: Template = {
  id: "tpl_instagram_01",
  title: "Oferta de temporada",
  platforms: ["instagram"],
  formats: ["static_post"],
  category: "Anuncios",
  objective: "sales",
  thumbnail_url: "/templates/amor.png",
  canva_url: "https://canva.link/jxr6r3xdtdx3p18",
  aspect_ratio: "4:5",
  editable_slots: ["titulo"],
  description: null,
};

describe("catálogo de plantillas", () => {
  test("busca por nombre, categoría, formato y etiquetas sin distinguir tildes", () => {
    const presentation = toTemplatePresentation(template);

    expect(matchesTemplate(presentation, "temporada", "all")).toBe(true);
    expect(matchesTemplate(presentation, "anuncios", "all")).toBe(true);
    expect(matchesTemplate(presentation, "static post", "all")).toBe(true);
    expect(matchesTemplate(presentation, "ANUNCIOS", "all")).toBe(true);
    expect(matchesTemplate(presentation, "anuncios", "ads")).toBe(true);
    expect(matchesTemplate(presentation, "anuncios", "reels")).toBe(false);
  });

  test("mantiene la proporción vertical apropiada para anuncios", () => {
    expect(toTemplatePresentation(template).aspectRatio).toBe("4 / 5");
  });

  test("conserva el asset local y formato del catálogo Instagram aprobado", () => {
    const seededTemplate: Template = {
      ...template,
      thumbnail_url: "/templates/flores.png",
    };

    expect(toTemplatePresentation(seededTemplate).thumbnail_url).toBe(
      "/templates/flores.png"
    );
    expect(seededTemplate.aspect_ratio).toBe("4:5");
  });

  test("resuelve el origen y acepta una entrada de Canva sin miniatura", () => {
    const canvaTemplate: Template = {
      ...template,
      id: "tpl_static_01",
      title: "Menú del día",
      thumbnail_url: null,
      description: "Plantilla de restaurante para el menú semanal.",
      source: "canva",
      cover: "gastronomy",
    };

    const presentation = toTemplatePresentation(canvaTemplate);

    expect(presentation.source).toBe("canva");
    // El id coincide con un asset sembrado: la entrada de Canva no debe
    // adoptarlo y presentar el diseño de otra plantilla como suyo.
    expect(presentation.thumbnail_url).toBeNull();
    expect(presentation.cover).toBe("gastronomy");
  });

  test("trata como propia la plantilla que llega sin origen declarado", () => {
    expect(toTemplatePresentation(template).source).toBe("custom");
  });

  test("encuentra la entrada de Canva por su descripción y por categoría", () => {
    const canvaTemplate: Template = {
      ...template,
      id: "canva_gastro_01",
      title: "Menú del día",
      thumbnail_url: null,
      description: "Plantilla de restaurante para el menú semanal.",
      source: "canva",
      cover: "gastronomy",
    };
    const presentation = toTemplatePresentation(canvaTemplate);

    expect(matchesTemplate(presentation, "restaurante", "all")).toBe(true);
    expect(matchesTemplate(presentation, "menu", "all")).toBe(true);
    expect(matchesTemplate(presentation, "", "ads")).toBe(true);
    expect(matchesTemplate(presentation, "", "reels")).toBe(false);
  });
});
