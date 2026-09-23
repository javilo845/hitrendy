import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

vi.mock("next/image", () => ({
  default: (props: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={props.alt} src={props.src} />
  ),
}));

import {
  TemplateCarousel,
  type TemplateCarouselItem,
} from "@/components/templates/template-carousel";

const items: TemplateCarouselItem[] = [
  {
    id: "tmpl-1",
    title: "Reel de producto",
    thumbnailUrl: "https://example.com/one.png",
    aspectRatio: "9 / 16",
    badge: "Reels",
    reason: "Combina bien con tu último lanzamiento.",
  },
  {
    id: "tmpl-2",
    title: "Carrusel de tips",
    thumbnailUrl: "https://example.com/two.png",
    aspectRatio: "4 / 5",
  },
];

const baseProps = {
  label: "Plantillas recomendadas",
  useLabel: "Usar plantilla",
  busyLabel: "Preparando...",
  previousLabel: "Anterior",
  nextLabel: "Siguiente",
};

describe("TemplateCarousel", () => {
  test("renders one card per item with its title", () => {
    render(
      <TemplateCarousel {...baseProps} items={items} onSelect={vi.fn()} />
    );

    expect(screen.getByText("Reel de producto")).toBeInTheDocument();
    expect(screen.getByText("Carrusel de tips")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Usar plantilla/ })
    ).toHaveLength(2);
  });

  test("calls onSelect with the matching id when a card action is used", () => {
    const onSelect = vi.fn();
    render(
      <TemplateCarousel {...baseProps} items={items} onSelect={onSelect} />
    );

    const buttons = screen.getAllByRole("button", { name: /Usar plantilla/ });
    buttons[1].click();

    expect(onSelect).toHaveBeenCalledWith("tmpl-2");
    expect(onSelect).toHaveBeenCalledOnce();
  });

  test("disables every action button and shows busyLabel on the busy card", () => {
    render(
      <TemplateCarousel
        {...baseProps}
        items={items}
        onSelect={vi.fn()}
        busyId="tmpl-1"
      />
    );

    const busyButton = screen.getByRole("button", { name: /Preparando/ });
    expect(busyButton).toBeDisabled();

    const otherButton = screen.getByRole("button", { name: /Usar plantilla/ });
    expect(otherButton).toBeDisabled();
  });

  test("renders nothing when items is empty", () => {
    const { container } = render(
      <TemplateCarousel {...baseProps} items={[]} onSelect={vi.fn()} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
