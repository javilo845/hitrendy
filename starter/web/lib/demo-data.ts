import type {
  GeneratedShortVideoScript,
  GeneratedSocialPost,
} from "@/types/artifact";
import type { Template } from "@/types/template";

type DemoConversation = {
  id: string;
  title: string;
  status: "active" | "archived";
  last_message: string;
  updated_at: string;
};

type DemoProject = {
  id: string;
  name: string;
  platform: string;
  status: "active" | "archived";
  updated_at: string;
  artifact_snapshot: { hook: string };
};

const demoUser = {
  user: {
    id: "demo-user",
    name: "Ana Demo",
    email: "demo@hitrendy.local",
    interface_locale: "es",
    deletion_confirmation_phrase: "ELIMINAR",
  },
  workspaces: [{ id: "demo-workspace", role: "owner" }],
};

const demoProjects: DemoProject[] = [
  {
    id: "project-demo-1",
    name: "Lanzamiento de desayuno",
    platform: "Instagram",
    status: "active",
    updated_at: new Date().toISOString(),
    artifact_snapshot: { hook: "Nueva carta de desayunos para llevar" },
  },
  {
    id: "project-demo-2",
    name: "Promo fin de semana",
    platform: "Facebook",
    status: "archived",
    updated_at: new Date().toISOString(),
    artifact_snapshot: { hook: "Una promo clara para traer más visitas" },
  },
];

const demoConversations: DemoConversation[] = [
  {
    id: "conversation-demo-1",
    title: "Nueva creación",
    status: "active",
    last_message: "Necesito un post para anunciar una oferta.",
    updated_at: new Date().toISOString(),
  },
];

const demoTemplates: Template[] = [
  {
    id: "tpl_instagram_01",
    title: "Promoción floral",
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Posts",
    objective: "sales",
    thumbnail_url: "/templates/flores.png",
    editable_slots: ["titular", "precio", "llamada_a_la_accion"],
    description: "Una promoción de producto con espacio para una oferta clara.",
    canva_url: "https://canva.link/jxr6r3xdtdx3p18",
    aspect_ratio: "4:5",
  },
  {
    id: "tpl_instagram_02",
    title: "Oferta de temporada",
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Anuncios",
    objective: "launch",
    thumbnail_url: "/templates/amor.png",
    editable_slots: ["oferta", "fecha", "llamada_a_la_accion"],
    description: "Un anuncio cálido y editable para una fecha especial.",
    canva_url: "https://canva.link/d5gnf0tsot7t70m",
    aspect_ratio: "4:5",
  },
  {
    id: "tpl_instagram_03",
    title: "Menú del día",
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Posts",
    objective: "store_visits",
    thumbnail_url: "/templates/comida.png",
    editable_slots: ["producto", "precio", "horario"],
    description: "Un post claro para impulsar visitas hoy.",
    canva_url: "https://canva.link/2hk1wscap0jikce",
    aspect_ratio: "4:5",
  },
  {
    id: "tpl_instagram_04",
    title: "Historia de marca",
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Posts",
    objective: "brand_awareness",
    thumbnail_url: "/templates/coffee.png",
    editable_slots: ["producto", "historia", "llamada_a_la_accion"],
    description:
      "Una pieza editorial para contar qué hace especial a tu negocio.",
    canva_url: "https://canva.link/9667338l5l4mgwg",
    aspect_ratio: "4:5",
  },
  {
    id: "tpl_instagram_05",
    title: "Café destacado",
    platforms: ["instagram"],
    formats: ["static_post"],
    category: "Anuncios",
    objective: "sales",
    thumbnail_url: "/templates/coffee.png",
    editable_slots: ["producto", "precio", "cta"],
    description: "Un anuncio de producto que conserva espacio para tu oferta.",
    canva_url: "https://canva.link/7ped4en1xal5yk7",
    aspect_ratio: "4:5",
  },
];

const demoArtifact: GeneratedSocialPost = {
  artifact_type: "social_post",
  platform: "instagram",
  hook: "Desayuna mejor esta semana",
  caption:
    "Una propuesta fresca, rápida y lista para compartir con tu audiencia.",
  call_to_action: "Escríbenos y te preparamos el tuyo.",
  hashtags: ["#HiTrendy", "#Contenido", "#Instagram"],
  visual_direction: "Luz cálida, mesa cercana y composición limpia.",
  format_recommendation: "static_post",
  assumptions: ["El negocio quiere impulsar visitas esta semana."],
};

const demoVideoScript: GeneratedShortVideoScript = {
  artifact_type: "short_video_script",
  platform: "instagram",
  hook: "Un video corto para tu promo",
  duration_seconds: 15,
  scenes: [
    {
      order: 1,
      duration_seconds: 5,
      visual: "Plano del producto principal",
      on_screen_text: "Nuevo lanzamiento",
      voiceover: "Hoy te mostramos una opción pensada para convertir.",
    },
    {
      order: 2,
      duration_seconds: 5,
      visual: "Cliente disfrutando el resultado",
      on_screen_text: "Rápido y claro",
      voiceover: "Sin complicarte, con un mensaje directo.",
    },
    {
      order: 3,
      duration_seconds: 5,
      visual: "Cierre con marca y CTA",
      on_screen_text: "Pide el tuyo",
      voiceover: "Pide tu versión y te ayudamos a ajustarla.",
    },
  ],
  call_to_action: "Pide tu versión hoy.",
  caption: "Guion de ejemplo para revisar ritmo, enfoque y CTA.",
  assumptions: ["El negocio quiere una pieza breve para redes."],
};

export const demoData = {
  auth: demoUser,
  projects: demoProjects,
  conversations: demoConversations,
  templates: demoTemplates,
  businesses: [
    {
      id: "business-demo-1",
      name: "Café Central",
      category: "gastronomy",
      country: "Honduras",
      city: "Tegucigalpa",
      description: "Café de especialidad para quienes trabajan y viven cerca.",
      primary_product: "Café de especialidad y desayunos",
      target_audience: "Personas que buscan una pausa cercana y de calidad.",
      preferred_platforms: ["instagram", "facebook"],
      primary_objective: "store_visits",
      content_locale: "es",
    },
  ],
  brandProfile: {
    voice_tones: ["friendly"],
    value_proposition:
      "Un café cercano que convierte una pausa en un buen momento.",
    preferred_words: ["cercano", "fresco", "hecho con cariño"],
    forbidden_words: ["barato", "urgente"],
    primary_color: "#541787",
    secondary_color: "#B79CFA",
  },
  artifacts: {
    demoArtifact,
    demoVideoScript,
  },
};

export function cloneDemo<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
