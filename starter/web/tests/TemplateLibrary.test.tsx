import { afterEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import { TemplateLibrary } from "@/components/templates/template-library";
import { surfaceCopy } from "@/lib/i18n";
import type { Template } from "@/types/template";

const copy = surfaceCopy.es.templates;

const customTemplate: Template = {
  id: "tpl_static_01",
  title: "Promoción floral",
  platforms: ["instagram"],
  formats: ["static_post"],
  category: "Posts",
  objective: "sales",
  thumbnail_url: "/templates/flores.png",
  canva_url: "https://canva.link/jxr6r3xdtdx3p18",
  aspect_ratio: "4:5",
  editable_slots: ["titular"],
  description: "Una promoción de producto con espacio para una oferta clara.",
  source: "custom",
  cover: null,
};

const canvaTemplate: Template = {
  id: "canva_gastro_01",
  title: "Menú del día",
  platforms: ["instagram"],
  formats: ["static_post"],
  category: "Posts",
  objective: "store_visits",
  thumbnail_url: null,
  canva_url: "https://www.canva.com/templates/EAF-menu/",
  aspect_ratio: "4:5",
  editable_slots: [],
  description: "Plantilla de restaurante para el menú semanal.",
  source: "canva",
  cover: "gastronomy",
};

function renderLibrary(onUse = vi.fn().mockResolvedValue(undefined)) {
  render(
    <TemplateLibrary
      templates={[customTemplate, canvaTemplate]}
      onUse={onUse}
      copy={copy}
    />
  );
  return onUse;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("biblioteca de plantillas con entradas de Canva", () => {
  test("dibuja una portada en vez de una imagen para la entrada de Canva", () => {
    renderLibrary();

    const cover = screen.getByRole("img", {
      name: "Portada de Gastronomía: Menú del día",
    });
    expect(cover).toHaveAttribute("data-cover", "gastronomy");
    expect(cover.querySelector("img")).toBeNull();

    // La plantilla propia conserva su bitmap.
    expect(
      screen.getByRole("img", { name: `${copy.preview}: Promoción floral` })
    ).toBeInTheDocument();
  });

  test("la insignia distingue el origen de cada tarjeta", () => {
    renderLibrary();

    expect(screen.getByText("Canva")).toBeInTheDocument();
    expect(screen.getByText("HiTrendy")).toBeInTheDocument();
    expect(
      screen.getByText("Origen: plantilla de Canva")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Origen: plantilla de HiTrendy")
    ).toBeInTheDocument();
  });

  test("la entrada de Canva abre su enlace y nunca entra al studio", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const onUse = renderLibrary();

    fireEvent.click(screen.getByRole("button", { name: /Abrir en Canva/ }));

    expect(open).toHaveBeenCalledWith(
      canvaTemplate.canva_url,
      "_blank",
      "noopener,noreferrer"
    );
    expect(onUse).not.toHaveBeenCalled();
  });

  test("la plantilla propia sigue llamando a onUse", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const onUse = renderLibrary();

    // onUse es asíncrona y libera el estado "preparando" al resolverse.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: new RegExp(copy.use) }));
    });

    expect(onUse).toHaveBeenCalledWith(
      expect.objectContaining({ id: "tpl_static_01" })
    );
    expect(open).not.toHaveBeenCalled();
  });

  test("la búsqueda y el conteo siguen alcanzando a las entradas de Canva", () => {
    renderLibrary();

    expect(screen.getByRole("status")).toHaveTextContent(`2 ${copy.plural}`);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "restaurante" },
    });

    expect(screen.getByRole("status")).toHaveTextContent(`1 ${copy.singular}`);
    // El título aparece en la tarjeta y también rotulado sobre la portada.
    expect(
      screen.getByRole("heading", { name: "Menú del día" })
    ).toBeInTheDocument();
    expect(screen.queryByText("Promoción floral")).not.toBeInTheDocument();
  });
});
