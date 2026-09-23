import type { Template, TemplateSource } from "@/types/template";

export const templateCategories = [
  { id: "all", label: "Todos" },
  { id: "reels", label: "Reels" },
  { id: "posts", label: "Posts" },
  { id: "stories", label: "Stories" },
  { id: "ads", label: "Anuncios" },
] as const;

export type TemplateCategory = (typeof templateCategories)[number]["id"];

export type TemplatePresentation = Template & {
  categoryId: Exclude<TemplateCategory, "all">;
  displayCategory: string;
  aspectRatio: "4 / 5" | "9 / 16";
  tags: string[];
  /** Resolved, never optional: the card branches on it to pick its action. */
  source: TemplateSource;
};

type PresentationMeta = Pick<
  TemplatePresentation,
  "categoryId" | "displayCategory" | "aspectRatio" | "tags"
>;

const fallbackMeta: PresentationMeta = {
  categoryId: "posts",
  displayCategory: "Posts",
  aspectRatio: "4 / 5",
  tags: [],
};

const metaById: Record<string, PresentationMeta> = {
  "template-demo-1": {
    categoryId: "posts",
    displayCategory: "Posts",
    aspectRatio: "4 / 5",
    tags: ["promoción", "producto", "oferta"],
  },
  "template-demo-2": {
    categoryId: "reels",
    displayCategory: "Reels",
    aspectRatio: "9 / 16",
    tags: ["lanzamiento", "video", "campaña"],
  },
  "template-demo-3": {
    categoryId: "stories",
    displayCategory: "Stories",
    aspectRatio: "9 / 16",
    tags: ["café", "menú", "temporada"],
  },
  "template-demo-4": {
    categoryId: "ads",
    displayCategory: "Anuncios",
    aspectRatio: "4 / 5",
    tags: ["flores", "regalo", "venta"],
  },
  "template-demo-5": {
    categoryId: "stories",
    displayCategory: "Stories",
    aspectRatio: "9 / 16",
    tags: ["verano", "descuento", "historia"],
  },
  "template-demo-6": {
    categoryId: "posts",
    displayCategory: "Posts",
    aspectRatio: "4 / 5",
    tags: ["amor", "fecha especial", "promoción"],
  },
  "template-demo-7": {
    categoryId: "reels",
    displayCategory: "Reels",
    aspectRatio: "9 / 16",
    tags: ["natural", "producto", "video"],
  },
  "template-demo-8": {
    categoryId: "ads",
    displayCategory: "Anuncios",
    aspectRatio: "4 / 5",
    tags: ["café", "destacado", "anuncio"],
  },
};

const localThumbnailById: Record<string, string> = {
  tpl_reel_01: "/templates/video-mar.png",
  tpl_static_01: "/templates/flores.png",
  tpl_story_01: "/templates/comida.png",
  tpl_video_01: "/templates/video-noche.png",
  tpl_carousel_01: "/templates/coffee.png",
  tpl_whatsapp_01: "/templates/amor.png",
  tpl_launch_01: "/templates/video-trigo.png",
  tpl_event_01: "/templates/summer.png",
};

function inferredMeta(template: Template): PresentationMeta {
  const category = normalize(template.category);
  const formats = template.formats.map(normalize);
  const vertical = formats.some(
    (format) =>
      format === "reel" || format === "story" || format === "short video"
  );

  if (category.includes("reel") || formats.includes("reel")) {
    return {
      ...fallbackMeta,
      categoryId: "reels",
      displayCategory: "Reels",
      aspectRatio: "9 / 16",
    };
  }
  if (category.includes("story") || formats.includes("story")) {
    return {
      ...fallbackMeta,
      categoryId: "stories",
      displayCategory: "Stories",
      aspectRatio: "9 / 16",
    };
  }
  if (category.includes("anuncio") || category.includes("ad")) {
    return { ...fallbackMeta, categoryId: "ads", displayCategory: "Anuncios" };
  }
  return {
    ...fallbackMeta,
    aspectRatio: vertical ? "9 / 16" : "4 / 5",
    tags: [template.category, ...template.formats].filter(Boolean),
  };
}

export function normalize(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]/g, " ")
    .toLocaleLowerCase("es")
    .trim();
}

export function toTemplatePresentation(
  template: Template
): TemplatePresentation {
  const source: TemplateSource = template.source === "canva" ? "canva" : "custom";
  // Canva entries are drawn from their niche cover; handing them a seeded asset
  // would show someone else's design as if it were the template.
  const localThumbnail =
    source === "canva" ? undefined : localThumbnailById[template.id];
  return {
    ...template,
    ...(metaById[template.id] || inferredMeta(template)),
    ...(localThumbnail ? { thumbnail_url: localThumbnail } : {}),
    source,
  };
}

export function matchesTemplate(
  template: TemplatePresentation,
  query: string,
  category: TemplateCategory
) {
  const searchable = [
    template.title,
    template.category,
    template.displayCategory,
    template.formats.join(" "),
    template.tags.join(" "),
    // Canva entries share their category with dozens of others; the niche wording
    // that tells them apart only appears in the description.
    template.description || "",
  ]
    .map(normalize)
    .join(" ");

  return (
    (category === "all" || template.categoryId === category) &&
    (!normalize(query) || searchable.includes(normalize(query)))
  );
}
