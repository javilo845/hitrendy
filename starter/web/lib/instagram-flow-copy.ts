const objectiveLabels = {
  engagement: ["Interacción", "Engagement", "Engajamento"],
  sales: ["Ventas", "Sales", "Vendas"],
  reach: ["Alcance", "Reach", "Alcance"],
  store_visits: ["Visitas al negocio", "Store visits", "Visitas ao negócio"],
  launch: ["Lanzamiento", "Launch", "Lançamento"],
  brand_awareness: ["Reconocimiento de marca", "Brand awareness", "Reconhecimento da marca"],
  community: ["Comunidad", "Community", "Comunidade"],
} as const;

const qualityLabels = {
  fast: ["Rápido", "Fast", "Rápido"],
  balanced: ["Equilibrado", "Balanced", "Equilibrado"],
  quality: ["Calidad", "Quality", "Qualidade"],
} as const;

/**
 * Every string the image step can render, in the three interface languages.
 *
 * The keys mirror the contract the backend exposes: one label per brief field,
 * one per aspect ratio, one per job state and one per refusal reason, so an
 * unavailable capability is explained instead of hidden behind a dead button.
 */
const imageCopy = {
  heading: ["4. Imagen del post", "4. Post image", "4. Imagem do post"],
  intro: [
    "Revisa y edita el brief visual. Nada se genera hasta que lo confirmes.",
    "Review and edit the visual brief. Nothing is generated until you confirm.",
    "Revise e edite o brief visual. Nada é gerado até você confirmar.",
  ],
  briefHeading: ["Brief visual", "Visual brief", "Brief visual"],
  briefLoading: ["Preparando el brief visual…", "Preparing the visual brief…", "Preparando o brief visual…"],
  briefError: [
    "No pudimos preparar el brief visual.",
    "We could not prepare the visual brief.",
    "Não foi possível preparar o brief visual.",
  ],
  subject: ["Qué se ve", "What is shown", "O que aparece"],
  setting: ["Dónde ocurre", "Where it happens", "Onde acontece"],
  style: ["Estilo visual", "Visual style", "Estilo visual"],
  palette: ["Paleta de color", "Color palette", "Paleta de cores"],
  mood: ["Ánimo", "Mood", "Clima"],
  avoid: ["Qué evitar", "What to avoid", "O que evitar"],
  formatHeading: ["Formato", "Format", "Formato"],
  formatHint: [
    "Una imagen por generación, en uno de estos tres formatos.",
    "One image per generation, in one of these three formats.",
    "Uma imagem por geração, em um destes três formatos.",
  ],
  ratioLabels: {
    "1:1": ["Cuadrado 1:1", "Square 1:1", "Quadrado 1:1"],
    "4:5": ["Vertical 4:5", "Portrait 4:5", "Vertical 4:5"],
    "9:16": ["Historia 9:16", "Story 9:16", "Story 9:16"],
  },
  referenceHeading: ["Imagen de referencia", "Reference image", "Imagem de referência"],
  referenceHint: [
    "Opcional. Solo puedes usar imágenes que ya subiste a este espacio.",
    "Optional. You can only use images already uploaded to this workspace.",
    "Opcional. Você só pode usar imagens já enviadas para este espaço.",
  ],
  referenceNone: ["Sin referencia", "No reference", "Sem referência"],
  preflight: ["Revisar antes de generar", "Review before generating", "Revisar antes de gerar"],
  preflighting: ["Revisando…", "Reviewing…", "Revisando…"],
  preflightHeading: ["Resumen de la generación", "Generation summary", "Resumo da geração"],
  costHeading: ["Costo", "Cost", "Custo"],
  costValue: ["1 imagen de tu límite diario", "1 image from your daily limit", "1 imagem do seu limite diário"],
  budget: ["Disponible hoy", "Available today", "Disponível hoje"],
  budgetValue: ["{remaining} de {total}", "{remaining} of {total}", "{remaining} de {total}"],
  budgetReset: ["Se renueva el {date}", "Renews on {date}", "Renova em {date}"],
  promptPreview: ["Descripción que se enviará", "Description that will be sent", "Descrição que será enviada"],
  avoidPreview: ["Lo que se pedirá evitar", "What will be avoided", "O que será evitado"],
  avoidPreviewNone: ["Nada en particular", "Nothing in particular", "Nada em particular"],
  confirm: ["Confirmar y generar imagen", "Confirm and generate image", "Confirmar e gerar imagem"],
  confirming: ["Enviando…", "Sending…", "Enviando…"],
  confirmHint: [
    "Al confirmar se descuenta una imagen de tu límite diario.",
    "Confirming uses one image from your daily limit.",
    "Ao confirmar, uma imagem do seu limite diário é usada.",
  ],
  editedAfterPreflight: [
    "Cambiaste el brief. Vuelve a revisarlo antes de generar.",
    "You changed the brief. Review it again before generating.",
    "Você alterou o brief. Revise novamente antes de gerar.",
  ],
  statusHeading: ["Estado de la imagen", "Image status", "Status da imagem"],
  statusQueued: ["En cola. Puedes seguir editando tu post.", "Queued. You can keep editing your post.", "Na fila. Você pode continuar editando seu post."],
  statusRunning: ["Generando tu imagen…", "Generating your image…", "Gerando sua imagem…"],
  statusProviderStarted: [
    "El proveedor ya está creando tu imagen. Espera su respuesta.",
    "The provider is already creating your image. Wait for its response.",
    "O provedor já está criando sua imagem. Aguarde a resposta.",
  ],
  statusSucceeded: ["Tu imagen está lista.", "Your image is ready.", "Sua imagem está pronta."],
  statusFailed: ["No pudimos generar la imagen.", "We could not generate the image.", "Não foi possível gerar a imagem."],
  statusCancelled: ["La generación se canceló.", "The generation was cancelled.", "A geração foi cancelada."],
  statusUnknown: ["Seguimos esperando una respuesta.", "We are still waiting for a response.", "Ainda estamos aguardando uma resposta."],
  pollTimeout: [
    "La imagen está tardando más de lo normal. Consulta el estado cuando quieras.",
    "The image is taking longer than usual. Check the status whenever you want.",
    "A imagem está demorando mais que o normal. Consulte o status quando quiser.",
  ],
  checkStatus: ["Consultar estado", "Check status", "Consultar status"],
  retry: ["Reintentar generación", "Retry generation", "Tentar gerar novamente"],
  altNote: [
    "La descripción accesible de la imagen se toma de tu brief visual.",
    "The image's accessible description comes from your visual brief.",
    "A descrição acessível da imagem vem do seu brief visual.",
  ],
  linkExpires: [
    "El enlace de la imagen es temporal y privado.",
    "The image link is temporary and private.",
    "O link da imagem é temporário e privado.",
  ],
  refreshLink: [
    "Actualizar el enlace de la imagen",
    "Refresh the image link",
    "Atualizar o link da imagem",
  ],
  savePostFirst: [
    "Guarda el post antes de generar la imagen, para poder recuperarla si cierras la página.",
    "Save the post before generating the image, so you can recover it if you close the page.",
    "Salve o post antes de gerar a imagem, para poder recuperá-la se fechar a página.",
  ],
  recovering: [
    "Buscando la imagen que ya habías pedido para este post…",
    "Looking for the image you already requested for this post…",
    "Procurando a imagem que você já pediu para este post…",
  ],
  recovered: [
    "Recuperamos la generación que ya habías iniciado para este post.",
    "We recovered the generation you had already started for this post.",
    "Recuperamos a geração que você já havia iniciado para este post.",
  ],
  fallbackHeading: ["Usa el brief visual", "Use the visual brief", "Use o brief visual"],
  fallbackHint: [
    "La generación no está disponible, pero este brief sirve para Canva o para tu diseñador.",
    "Generation is unavailable, but this brief works for Canva or for your designer.",
    "A geração não está disponível, mas este brief serve para o Canva ou para seu designer.",
  ],
  reason: {
    disabled: [
      "La generación de imágenes está desactivada en este espacio.",
      "Image generation is turned off for this workspace.",
      "A geração de imagens está desativada neste espaço.",
    ],
    unconfigured: [
      "Todavía no hay un proveedor de imágenes configurado.",
      "No image provider is configured yet.",
      "Ainda não há um provedor de imagens configurado.",
    ],
    quota_exhausted: [
      "Alcanzaste el límite de imágenes de hoy.",
      "You have reached today's image limit.",
      "Você atingiu o limite de imagens de hoje.",
    ],
    payment_required: [
      "La cuenta del proveedor no tiene crédito disponible.",
      "The provider account has no credit available.",
      "A conta do provedor não tem crédito disponível.",
    ],
    restricted: [
      "Tu plan no incluye generación de imágenes.",
      "Your plan does not include image generation.",
      "Seu plano não inclui geração de imagens.",
    ],
    degraded: [
      "El proveedor responde con lentitud. Puedes intentarlo igualmente.",
      "The provider is responding slowly. You can still try.",
      "O provedor está respondendo devagar. Você ainda pode tentar.",
    ],
    error: [
      "La generación de imágenes no está disponible en este momento.",
      "Image generation is unavailable right now.",
      "A geração de imagens não está disponível no momento.",
    ],
  },
  confirmError: [
    "No pudimos iniciar la generación.",
    "We could not start the generation.",
    "Não foi possível iniciar a geração.",
  ],
  statusError: [
    "No pudimos consultar el estado de la imagen.",
    "We could not check the image status.",
    "Não foi possível consultar o status da imagem.",
  ],
} as const;

/**
 * Every string the video step can render, in the three interface languages.
 * The storyboard remains useful when generation is unavailable, so fallback,
 * capability, approval and job states all have product-language copy.
 */
const videoCopy = {
  heading: ["5. Video del post", "5. Post video", "5. Vídeo do post"],
  intro: [
    "Convierte tu publicación en un storyboard vertical editable. Nada se genera hasta que lo confirmes.",
    "Turn your publication into an editable vertical storyboard. Nothing is generated until you confirm.",
    "Transforme sua publicação em um storyboard vertical editável. Nada é gerado até você confirmar.",
  ],
  storyboardHeading: ["Storyboard editable", "Editable storyboard", "Storyboard editável"],
  storyboardLoading: [
    "Preparando el storyboard…",
    "Preparing the storyboard…",
    "Preparando o storyboard…",
  ],
  storyboardError: [
    "No pudimos preparar el storyboard.",
    "We could not prepare the storyboard.",
    "Não foi possível preparar o storyboard.",
  ],
  storyboardEmpty: [
    "Todavía no hay tomas para editar.",
    "There are no shots to edit yet.",
    "Ainda não há tomadas para editar.",
  ],
  hook: ["Gancho", "Hook", "Gancho"],
  voiceover: ["Voz en off", "Voiceover", "Narração"],
  music_direction: ["Dirección musical", "Music direction", "Direção musical"],
  shotsHeading: ["Tomas", "Shots", "Tomadas"],
  shotLabel: ["Toma {number}", "Shot {number}", "Tomada {number}"],
  visual: ["Qué se ve", "What is shown", "O que aparece"],
  camera: ["Cámara", "Camera", "Câmera"],
  on_screen_text: ["Texto en pantalla", "On-screen text", "Texto na tela"],
  shot_voiceover: ["Voz de la toma", "Shot voiceover", "Narração da tomada"],
  transition: ["Transición", "Transition", "Transição"],
  durationHeading: ["Duración", "Duration", "Duração"],
  durationHint: [
    "Elige una duración antes de revisar el costo en unidades.",
    "Choose a duration before reviewing the cost in units.",
    "Escolha uma duração antes de revisar o custo em unidades.",
  ],
  durationLabels: {
    5: ["5 segundos", "5 seconds", "5 segundos"],
    10: ["10 segundos", "10 seconds", "10 segundos"],
    16: ["16 segundos", "16 seconds", "16 segundos"],
    20: ["20 segundos", "20 seconds", "20 segundos"],
  },
  formatHeading: ["Formato", "Format", "Formato"],
  formatLabel: ["Vertical 9:16", "Vertical 9:16", "Vertical 9:16"],
  sourceHeading: ["Imagen de origen", "Source image", "Imagem de origem"],
  sourceHint: [
    "Opcional. Elige una imagen que ya pertenece a este espacio.",
    "Optional. Choose an image already owned by this workspace.",
    "Opcional. Escolha uma imagem que já pertence a este espaço.",
  ],
  sourceNone: ["Sin imagen de origen", "No source image", "Sem imagem de origem"],
  sourceImageOption: ["Imagen {number}", "Image {number}", "Imagem {number}"],
  promptHeading: ["Descripción para el video", "Video prompt", "Descrição do vídeo"],
  negativePromptHeading: [
    "Qué evitar en el video",
    "What to avoid in the video",
    "O que evitar no vídeo",
  ],
  negativePromptNone: ["Nada en particular", "Nothing in particular", "Nada em particular"],
  preflight: ["Revisar antes de generar", "Review before generating", "Revisar antes de gerar"],
  preflighting: ["Revisando…", "Reviewing…", "Revisando…"],
  preflightHeading: ["Resumen de la generación", "Generation summary", "Resumo da geração"],
  storyboardPreview: ["Storyboard aprobado", "Approved storyboard", "Storyboard aprovado"],
  durationSummary: ["Duración elegida", "Selected duration", "Duração escolhida"],
  sourceSummary: ["Origen visual", "Visual source", "Origem visual"],
  formatSummary: ["Formato vertical", "Vertical format", "Formato vertical"],
  promptPreview: ["Descripción que se enviará", "Description that will be sent", "Descrição que será enviada"],
  negativePromptPreview: ["Lo que se pedirá evitar", "What will be avoided", "O que será evitado"],
  costHeading: ["Costo estimado", "Estimated cost", "Custo estimado"],
  costValue: [
    "{units} unidad(es) de tu límite de video",
    "{units} video limit unit(s)",
    "{units} unidade(s) do seu limite de vídeo",
  ],
  budget: ["Presupuesto de unidades", "Unit budget", "Orçamento de unidades"],
  budgetValue: ["{remaining} de {total}", "{remaining} of {total}", "{remaining} de {total}"],
  budgetReset: ["Se renueva el {date}", "Renews on {date}", "Renova em {date}"],
  capabilityHeading: ["Disponibilidad", "Availability", "Disponibilidade"],
  capabilityAvailable: ["Disponible", "Available", "Disponível"],
  capabilityDegraded: ["Disponible con demora", "Available with delays", "Disponível com demora"],
  confirm: ["Confirmar y generar video", "Confirm and generate video", "Confirmar e gerar vídeo"],
  confirming: ["Enviando…", "Sending…", "Enviando…"],
  confirmHint: [
    "Al confirmar se descuentan las unidades estimadas de tu límite.",
    "Confirming uses the estimated units from your limit.",
    "Ao confirmar, as unidades estimadas são usadas do seu limite.",
  ],
  editedAfterPreflight: [
    "Cambiaste el storyboard, el prompt, la duración o el origen. Vuelve a revisarlo antes de generar.",
    "You changed the storyboard, prompt, duration or source. Review it again before generating.",
    "Você alterou o storyboard, o prompt, a duração ou a origem. Revise novamente antes de gerar.",
  ],
  savePostFirst: [
    "Guarda el post antes de generar el video, para poder recuperarlo si cierras la página.",
    "Save the post before generating the video, so you can recover it if you close the page.",
    "Salve o post antes de gerar o vídeo, para poder recuperá-lo se fechar a página.",
  ],
  fallbackHeading: ["Conserva el storyboard", "Keep the storyboard", "Mantenha o storyboard"],
  fallbackHint: [
    "El video no está disponible, pero este storyboard sirve como guía editable para tu producción.",
    "Video is unavailable, but this storyboard remains an editable guide for production.",
    "O vídeo não está disponível, mas este storyboard continua sendo um guia editável para sua produção.",
  ],
  statusHeading: ["Estado del video", "Video status", "Status do vídeo"],
  status: {
    queued: ["En cola. Puedes seguir editando tu post.", "Queued. You can keep editing your post.", "Na fila. Você pode continuar editando seu post."],
    preparing: ["Preparando tu video…", "Preparing your video…", "Preparando seu vídeo…"],
    submitting: ["Enviando la solicitud de video…", "Sending the video request…", "Enviando a solicitação de vídeo…"],
    provider_pending: ["El servicio está generando tu video…", "The video service is generating your video…", "O serviço de vídeo está gerando seu vídeo…"],
    downloading: ["Descargando el resultado…", "Downloading the result…", "Baixando o resultado…"],
    succeeded: ["Tu video está listo.", "Your video is ready.", "Seu vídeo está pronto."],
    failed: ["No pudimos generar el video.", "We could not generate the video.", "Não foi possível gerar o vídeo."],
    cancelled: ["La generación se canceló.", "The generation was cancelled.", "A geração foi cancelada."],
    execution_unknown: ["No pudimos confirmar el resultado.", "We could not confirm the result.", "Não foi possível confirmar o resultado."],
  },
  pollTimeout: [
    "El video está tardando más de lo normal. Consulta el estado cuando quieras.",
    "The video is taking longer than usual. Check the status whenever you want.",
    "O vídeo está demorando mais que o normal. Consulte o status quando quiser.",
  ],
  checkStatus: ["Consultar estado", "Check status", "Consultar status"],
  retry: ["Revisar y reintentar", "Review and retry", "Revisar e tentar novamente"],
  recovering: [
    "Buscando el video que ya habías pedido para este post…",
    "Looking for the video you already requested for this post…",
    "Procurando o vídeo que você já pediu para este post…",
  ],
  recovered: [
    "Recuperamos la generación que ya habías iniciado para este post.",
    "We recovered the generation you had already started for this post.",
    "Recuperamos a geração que você já havia iniciado para este post.",
  ],
  refreshingLink: [
    "Actualizando el enlace temporal del video…",
    "Refreshing the video's temporary link…",
    "Atualizando o link temporário do vídeo…",
  ],
  refreshLink: [
    "Actualizar el enlace del video",
    "Refresh the video link",
    "Atualizar o link do vídeo",
  ],
  linkExpires: [
    "El enlace del video es temporal y privado.",
    "The video link is temporary and private.",
    "O link do vídeo é temporário e privado.",
  ],
  videoAlt: [
    "Video vertical generado para la publicación",
    "Vertical video generated for the publication",
    "Vídeo vertical gerado para a publicação",
  ],
  noVideo: [
    "El resultado todavía no tiene un enlace de reproducción.",
    "The result does not have a playback link yet.",
    "O resultado ainda não tem um link de reprodução.",
  ],
  safeErrorFallback: [
    "No pudimos completar el video. Revisa el storyboard y vuelve a intentarlo.",
    "We could not complete the video. Review the storyboard and try again.",
    "Não foi possível concluir o vídeo. Revise o storyboard e tente novamente.",
  ],
  briefError: [
    "No pudimos preparar el storyboard del video.",
    "We could not prepare the video storyboard.",
    "Não foi possível preparar o storyboard do vídeo.",
  ],
  preflightError: [
    "No pudimos revisar esta generación.",
    "We could not review this generation.",
    "Não foi possível revisar esta geração.",
  ],
  confirmError: [
    "No pudimos iniciar la generación del video.",
    "We could not start the video generation.",
    "Não foi possível iniciar a geração do vídeo.",
  ],
  statusError: [
    "No pudimos consultar el estado del video.",
    "We could not check the video status.",
    "Não foi possível consultar o status do vídeo.",
  ],
  reason: {
    disabled: [
      "La generación de video está desactivada en este espacio.",
      "Video generation is turned off for this workspace.",
      "A geração de vídeo está desativada neste espaço.",
    ],
    unconfigured: [
      "La generación de video todavía no está configurada.",
      "Video generation is not configured yet.",
      "A geração de vídeo ainda não está configurada.",
    ],
    quota_exhausted: [
      "Alcanzaste el límite de videos de hoy.",
      "You have reached today's video limit.",
      "Você atingiu o limite de vídeos de hoje.",
    ],
    payment_required: [
      "La cuenta de generación no tiene crédito disponible.",
      "The generation account has no credit available.",
      "A conta de geração não tem crédito disponível.",
    ],
    restricted: [
      "Tu plan no incluye generación de video.",
      "Your plan does not include video generation.",
      "Seu plano não inclui geração de vídeo.",
    ],
    degraded: [
      "La generación de video está funcionando con demora. Puedes intentarlo igualmente.",
      "Video generation is responding slowly. You can still try.",
      "A geração de vídeo está respondendo devagar. Você ainda pode tentar.",
    ],
    error: [
      "La generación de video no está disponible en este momento.",
      "Video generation is unavailable right now.",
      "A geração de vídeo não está disponível no momento.",
    ],
  },
} as const;

type ImageCopyEntry = readonly [string, string, string];

function localizedImageCopy(index: 0 | 1 | 2) {
  const flat = Object.fromEntries(
    Object.entries(imageCopy)
      .filter(([, value]) => Array.isArray(value))
      .map(([key, value]) => [key, (value as ImageCopyEntry)[index]])
  ) as Record<
    Exclude<keyof typeof imageCopy, "ratioLabels" | "reason">,
    string
  >;

  return {
    ...flat,
    ratioLabels: Object.fromEntries(
      Object.entries(imageCopy.ratioLabels).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof imageCopy.ratioLabels, string>,
    reason: Object.fromEntries(
      Object.entries(imageCopy.reason).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof imageCopy.reason, string>,
  };
}

type VideoCopyEntry = readonly [string, string, string];

function localizedVideoCopy(index: 0 | 1 | 2) {
  const flat = Object.fromEntries(
    Object.entries(videoCopy)
      .filter(([, value]) => Array.isArray(value))
      .map(([key, value]) => [key, (value as VideoCopyEntry)[index]])
  ) as Record<
    Exclude<keyof typeof videoCopy, "durationLabels" | "reason" | "status">,
    string
  >;

  return {
    ...flat,
    durationLabels: Object.fromEntries(
      Object.entries(videoCopy.durationLabels).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof videoCopy.durationLabels, string>,
    reason: Object.fromEntries(
      Object.entries(videoCopy.reason).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof videoCopy.reason, string>,
    status: Object.fromEntries(
      Object.entries(videoCopy.status).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof videoCopy.status, string>,
  };
}

function copyAt(index: 0 | 1 | 2) {
  return {
    objectiveLabels: Object.fromEntries(
      Object.entries(objectiveLabels).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof objectiveLabels, string>,
    qualityLabels: Object.fromEntries(
      Object.entries(qualityLabels).map(([key, value]) => [key, value[index]])
    ) as Record<keyof typeof qualityLabels, string>,
    image: localizedImageCopy(index),
    video: localizedVideoCopy(index),
  };
}

export const instagramFlowCopy = {
  es: {
    title: "Crea tu post de Instagram", subtitle: "Elige una plantilla 4:5, confirma tu idea y obtén un borrador editable.", loading: "Cargando tu contexto creativo…", briefFromProject: "Nuevo brief a partir de tu proyecto", noBusiness: "Completa primero la información de tu negocio y marca.", template: "1. Elige una plantilla de Instagram 4:5", context: "Tu contexto de negocio y marca", theme: "2. Objetivo o tema", objective: "Objetivo", quality: "3. Nivel de calidad", generate: "Generar post", generating: "Generando tu recomendación y post…", result: "Post generado", caption: "Texto del post", cta: "Llamada a la acción", hashtags: "Hashtags", visualBrief: "Visual brief 4:5", visualNote: "Esta es una guía para Canva o diseño; no es una imagen generada.", save: "Guardar post", saving: "Guardando…", restore: "Restaurar generado", unsaved: "Tienes cambios sin guardar.", duplicate: "Duplicar proyecto", duplicating: "Duplicando…", variation: "Crear variación", variationNotice: "La variación se creó como una nueva versión del post original.", openCanva: "Abrir plantilla en Canva", saved: "Post guardado. Puedes abrirlo de nuevo desde Proyectos.", format: "Instagram · 4:5", locale: "Idioma del contenido", invalidResponse: "No recibimos un post de Instagram válido.", generationError: "No pudimos generar el post. Puedes reintentar sin perder tu tema.", saveError: "No pudimos guardar. Tus cambios siguen disponibles aquí.", duplicateError: "No pudimos duplicar el proyecto.", variationError: "No pudimos crear la variación.", validationCaption: "Escribe un caption de hasta 2.200 caracteres.", validationVisual: "Escribe un visual brief de hasta 700 caracteres.", validationCta: "Escribe una llamada a la acción de hasta 240 caracteres.", validationHashtags: "Usa entre uno y cinco hashtags no vacíos, de hasta 100 caracteres cada uno.",
    ...copyAt(0),
  },
  en: {
    title: "Create your Instagram post", subtitle: "Choose a 4:5 template, confirm your idea, and get an editable draft.", loading: "Loading your creative context…", briefFromProject: "New brief based on your project", noBusiness: "Complete your business and brand information first.", template: "1. Choose an Instagram 4:5 template", context: "Your business and brand context", theme: "2. Goal or topic", objective: "Goal", quality: "3. Quality level", generate: "Generate post", generating: "Generating your recommendation and post…", result: "Generated post", caption: "Post caption", cta: "Call to action", hashtags: "Hashtags", visualBrief: "4:5 visual brief", visualNote: "This is guidance for Canva or a designer; it is not a generated image.", save: "Save post", saving: "Saving…", restore: "Restore generated", unsaved: "You have unsaved changes.", duplicate: "Duplicate project", duplicating: "Duplicating…", variation: "Create variation", variationNotice: "The variation was created as a new version of the original post.", openCanva: "Open template in Canva", saved: "Post saved. You can reopen it from Projects.", format: "Instagram · 4:5", locale: "Content language", invalidResponse: "We did not receive a valid Instagram post.", generationError: "We could not generate the post. You can retry without losing your topic.", saveError: "We could not save the post. Your changes are still available here.", duplicateError: "We could not duplicate the project.", variationError: "We could not create the variation.", validationCaption: "Enter a caption of up to 2,200 characters.", validationVisual: "Enter a visual brief of up to 700 characters.", validationCta: "Enter a call to action of up to 240 characters.", validationHashtags: "Use one to five non-empty hashtags, up to 100 characters each.",
    ...copyAt(1),
  },
  pt: {
    title: "Crie seu post do Instagram", subtitle: "Escolha um template 4:5, confirme sua ideia e receba um rascunho editável.", loading: "Carregando seu contexto criativo…", briefFromProject: "Novo brief a partir do seu projeto", noBusiness: "Complete primeiro as informações do seu negócio e da sua marca.", template: "1. Escolha um template Instagram 4:5", context: "Seu contexto de negócio e marca", theme: "2. Objetivo ou tema", objective: "Objetivo", quality: "3. Nível de qualidade", generate: "Gerar post", generating: "Gerando sua recomendação e post…", result: "Post gerado", caption: "Legenda do post", cta: "Chamada para ação", hashtags: "Hashtags", visualBrief: "Brief visual 4:5", visualNote: "Esta é uma orientação para Canva ou design; não é uma imagem gerada.", save: "Salvar post", saving: "Salvando…", restore: "Restaurar gerado", unsaved: "Você tem alterações não salvas.", duplicate: "Duplicar projeto", duplicating: "Duplicando…", variation: "Criar variação", variationNotice: "A variação foi criada como uma nova versão do post original.", openCanva: "Abrir template no Canva", saved: "Post salvo. Você pode reabri-lo em Projetos.", format: "Instagram · 4:5", locale: "Idioma do conteúdo", invalidResponse: "Não recebemos um post válido do Instagram.", generationError: "Não foi possível gerar o post. Você pode tentar novamente sem perder seu tema.", saveError: "Não foi possível salvar. Suas alterações continuam disponíveis aqui.", duplicateError: "Não foi possível duplicar o projeto.", variationError: "Não foi possível criar a variação.", validationCaption: "Escreva uma legenda de até 2.200 caracteres.", validationVisual: "Escreva um brief visual de até 700 caracteres.", validationCta: "Escreva uma chamada para ação de até 240 caracteres.", validationHashtags: "Use de uma a cinco hashtags não vazias, com até 100 caracteres cada.",
    ...copyAt(2),
  },
} as const;

export type InstagramFlowLocale = keyof typeof instagramFlowCopy;
