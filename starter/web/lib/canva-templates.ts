import type { GeneratedSocialPost, Platform } from "@/types/artifact";

/**
 * The Canva link is only useful when it lands on templates that look like the
 * post that was asked for: a technology post should open technology designs,
 * not a generic "promoción" search. The niche is read from the words the model
 * actually produced, which is the closest thing we have to what the user asked
 * for, and each niche carries the search terms and the hashtags that belong to
 * it.
 *
 * This is a suggestion, never a claim of an approved template: the curated
 * `canva.link` designs are a separate, allow-listed thing.
 */
export interface CanvaSuggestion {
  /** Stable id, useful for tests and analytics. */
  niche: string;
  /** Spanish label shown next to the link. */
  label: string;
  /** What is searched on Canva. */
  query: string;
  url: string;
  /** Hashtags that belong to the niche, offered on top of the post's own. */
  hashtags: string[];
}

interface Niche {
  id: string;
  label: string;
  /** Lowercase, unaccented keywords. */
  keywords: string[];
  terms: string;
  hashtags: string[];
}

const niches: Niche[] = [
  {
    id: "technology",
    label: "Tecnología",
    keywords: [
      "tecnologia", "tech", "software", "app", "aplicacion", "computadora",
      "computador", "laptop", "pc", "celular", "smartphone", "gadget",
      "inteligencia artificial", "ia", "ai", "programacion", "codigo",
      "startup", "saas", "digital", "ciberseguridad", "datos", "robot",
      "innovacion", "hardware", "internet", "web",
    ],
    terms: "tecnologia moderna gadgets",
    hashtags: ["#tecnologia", "#innovacion", "#inteligenciaartificial", "#gadgets", "#computadoras"],
  },
  {
    id: "gastronomy",
    label: "Gastronomía",
    keywords: [
      "restaurante", "comida", "cafe", "cafeteria", "pizza", "hamburguesa",
      "postre", "reposteria", "panaderia", "menu", "chef", "cocina", "bebida",
      "almuerzo", "desayuno", "cena", "delivery", "sabor", "receta",
    ],
    terms: "restaurante comida menu",
    hashtags: ["#comida", "#foodie", "#restaurante", "#delicioso", "#gastronomia"],
  },
  {
    id: "fashion",
    label: "Moda",
    keywords: [
      "moda", "ropa", "outfit", "tienda de ropa", "boutique", "vestido",
      "zapatos", "accesorios", "coleccion", "estilo", "prendas", "tendencia de moda",
    ],
    terms: "moda ropa boutique",
    hashtags: ["#moda", "#outfit", "#estilo", "#tiendaderopa", "#lookdeldia"],
  },
  {
    id: "beauty",
    label: "Belleza",
    keywords: [
      "belleza", "maquillaje", "salon", "peluqueria", "barberia", "uñas",
      "manicura", "spa", "skincare", "piel", "cabello", "estetica", "cosmetica",
    ],
    terms: "belleza salon spa",
    hashtags: ["#belleza", "#skincare", "#maquillaje", "#salondebelleza", "#autocuidado"],
  },
  {
    id: "fitness",
    label: "Fitness",
    keywords: [
      "gimnasio", "gym", "fitness", "entrenamiento", "entrenador", "ejercicio",
      "rutina", "crossfit", "yoga", "pilates", "musculacion", "deporte",
    ],
    terms: "gimnasio fitness entrenamiento",
    hashtags: ["#fitness", "#gym", "#entrenamiento", "#vidasaludable", "#deporte"],
  },
  {
    id: "health",
    label: "Salud",
    keywords: [
      "salud", "clinica", "doctor", "medico", "dental", "dentista", "farmacia",
      "consulta", "paciente", "bienestar", "nutricion", "nutricionista", "psicologia",
    ],
    terms: "salud clinica bienestar",
    hashtags: ["#salud", "#bienestar", "#clinica", "#cuidatusalud", "#prevencion"],
  },
  {
    id: "education",
    label: "Educación",
    keywords: [
      "curso", "clase", "educacion", "escuela", "colegio", "universidad",
      "taller", "capacitacion", "aprender", "estudiar", "profesor", "academia",
      "diplomado", "beca",
    ],
    terms: "educacion curso clases",
    hashtags: ["#educacion", "#cursos", "#aprender", "#formacion", "#clases"],
  },
  {
    id: "real_estate",
    label: "Inmobiliaria",
    keywords: [
      "inmobiliaria", "casa", "apartamento", "propiedad", "alquiler", "renta",
      "venta de casas", "terreno", "bienes raices", "residencial", "condominio",
    ],
    terms: "inmobiliaria propiedades casas",
    hashtags: ["#inmobiliaria", "#bienesraices", "#casaenventa", "#hogar", "#inversion"],
  },
  {
    id: "automotive",
    label: "Automotriz",
    keywords: [
      "auto", "carro", "vehiculo", "taller mecanico", "mecanico", "llantas",
      "repuestos", "moto", "motocicleta", "automotriz", "concesionario",
    ],
    terms: "automotriz taller carros",
    hashtags: ["#autos", "#taller", "#mecanica", "#vehiculos", "#motor"],
  },
  {
    id: "travel",
    label: "Viajes",
    keywords: [
      "viaje", "turismo", "hotel", "hostal", "tour", "playa", "destino",
      "vacaciones", "agencia de viajes", "aventura", "excursion",
    ],
    terms: "viajes turismo destinos",
    hashtags: ["#viajes", "#turismo", "#destinos", "#vacaciones", "#aventura"],
  },
  {
    id: "events",
    label: "Eventos",
    keywords: [
      "evento", "boda", "fiesta", "cumpleaños", "celebracion", "catering",
      "decoracion", "quinceañera", "banquete", "salon de eventos", "concierto",
    ],
    terms: "eventos fiesta celebracion",
    hashtags: ["#eventos", "#fiesta", "#celebracion", "#bodas", "#decoracion"],
  },
  {
    id: "pets",
    label: "Mascotas",
    keywords: [
      "mascota", "perro", "gato", "veterinaria", "veterinario", "pet",
      "peluqueria canina", "alimento para mascotas",
    ],
    terms: "mascotas veterinaria",
    hashtags: ["#mascotas", "#perros", "#gatos", "#veterinaria", "#petlovers"],
  },
];

/** Canva names formats differently per platform; this is what its search understands. */
const formatTerms: Record<GeneratedSocialPost["format_recommendation"], string> = {
  static_post: "post",
  carousel: "carrusel",
  story: "historia",
  reel: "reel portada",
  short_video: "video corto",
  text_post: "post",
};

const platformTerms: Record<Platform, string> = {
  instagram: "instagram",
  facebook: "facebook",
  tiktok: "tiktok",
  whatsapp: "whatsapp",
  youtube: "youtube",
  x: "twitter",
  linkedin: "linkedin",
};

/** Lowercases and drops accents so keyword matching does not depend on typing. */
export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

const ownHashtagStopWords = ["hitrendy", "contenidoparanegocios", "negocio", "emprendimiento"];

/**
 * Scores every niche against the post and keeps the best match. A keyword is
 * worth more when it appears in the hook or the hashtags than deep in the
 * caption, because that is where the subject of the request lives.
 */
export function detectNiche(post: GeneratedSocialPost): Niche | null {
  const strong = normalize([post.hook, post.hashtags.join(" ")].join(" "));
  const weak = normalize([post.caption, post.visual_direction].join(" "));
  let best: { niche: Niche; score: number } | null = null;

  for (const niche of niches) {
    let score = 0;
    for (const keyword of niche.keywords) {
      const pattern = new RegExp(`(^|[^a-z0-9])${keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z0-9]|$)`);
      if (pattern.test(strong)) score += 3;
      else if (pattern.test(weak)) score += 1;
    }
    if (score > 0 && (!best || score > best.score)) best = { niche, score };
  }

  return best ? best.niche : null;
}

/** The post's own hashtags, cleaned, used when no niche is recognised. */
function ownTerms(post: GeneratedSocialPost): string {
  const fromHashtags = post.hashtags
    .map((tag) => tag.replace(/^#/, "").trim())
    .filter((tag) => tag && !ownHashtagStopWords.some((word) => normalize(tag).includes(word)))
    .slice(0, 3)
    .join(" ");
  if (fromHashtags) return fromHashtags;
  return post.hook.replace(/[^\p{L}\p{N}\s]/gu, "").trim().split(/\s+/).slice(0, 4).join(" ");
}

export function suggestCanvaTemplate(post: GeneratedSocialPost): CanvaSuggestion {
  const niche = detectNiche(post);
  const shape = `${platformTerms[post.platform] || "instagram"} ${formatTerms[post.format_recommendation] || "post"}`;
  const subject = niche ? niche.terms : ownTerms(post) || "promocion negocio";
  const query = `${shape} ${subject}`.trim();

  return {
    niche: niche?.id || "general",
    label: niche?.label || "Tu tema",
    query,
    url: `https://www.canva.com/templates/?query=${encodeURIComponent(query)}`,
    hashtags: niche ? niche.hashtags : [],
  };
}
