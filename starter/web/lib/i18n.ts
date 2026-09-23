/**
 * Static translation catalog for the interface.
 *
 * The catalog ships with the build and is versioned: nothing is translated at
 * runtime by a machine, and no key is ever rendered to the user. A key missing
 * from a locale falls back to Spanish, and a key missing everywhere renders as
 * an empty string instead of leaking its identifier.
 */

import { useEffect, useState } from "react";

export type AppLocale = "es" | "en" | "pt";

export const supportedLocales: readonly AppLocale[] = ["es", "en", "pt"];

export const defaultLocale: AppLocale = "es";

/** Bumped whenever the catalog changes, so caches and tests can pin it. */
export const catalogVersion = "2026.07-wave-009";

/** BCP 47 tags used for dates, numbers, and currency. */
export const localeTags: Record<AppLocale, string> = {
  es: "es-ES",
  en: "en-US",
  pt: "pt-BR",
};

/** Each language is written in its own language, never translated. */
export const localeLabels: Record<AppLocale, string> = {
  es: "Español",
  en: "English",
  pt: "Português",
};

export const LOCALE_STORAGE_KEY = "hitrendy.interface_locale";
export const LOCALE_EVENT = "hitrendy:locale";

const es = {
  nav: {
    studio: "Studio",
    dashboard: "Dashboard",
    trends: "Tendencias",
    templates: "Plantillas",
    settings: "Configuración",
    logout: "Cerrar sesión",
    loggingOut: "Saliendo…",
    mobileLogout: "Salir",
    notifications: "Notificaciones",
    sections: "Secciones",
    main: "Navegación principal",
    mobile: "Navegación móvil",
    home: "HiTrendy, inicio",
  },
  common: {
    loading: "Cargando…",
    saving: "Guardando…",
    error: "Ocurrió un error.",
    empty: "No hay datos todavía.",
    retry: "Reintentar",
    save: "Guardar",
    cancel: "Cancelar",
    close: "Cerrar",
    edit: "Editar",
  },
  dashboard: {
    eyebrow: "DASHBOARD",
    title: "Tu espacio creativo",
    subtitle:
      "Organiza proyectos y encuentra una plantilla para tu próxima idea.",
    tabsLabel: "Contenido del dashboard",
    projects: "Proyectos",
    templates: "Plantillas",
    yourProjects: "Tus proyectos",
    startEyebrow: "EMPIEZA A DISEÑAR",
    projectsHeadline: "Todo tu contenido, en un solo lugar.",
    projectsLead:
      "Retoma una campaña, organiza tus borradores o continúa el trabajo pendiente.",
    templatesHeadline: "Elige una base y hazla completamente tuya.",
    templatesLead:
      "Usa una plantilla como punto de partida y personalízala con ayuda del Studio.",
    createCta: "Crear con HiTrendy",
    startCta: "Comenzar a crear",
    statusLabel: "Estado de proyectos",
    loadingProjects: "Cargando proyectos",
    loadError: "No pudimos cargar tus proyectos.",
    noResults: "No encontramos proyectos",
    noResultsHint: "Prueba otra búsqueda.",
    emptyArchived: "No hay proyectos archivados",
    emptyActive: "No hay proyectos todavía",
    emptyHint: "Crea tu primer borrador desde una plantilla o desde cero.",
    updatedAt: "Actualizado",
    noActivity: "Sin actividad",
    statusActive: "Activos",
    statusArchived: "Archivados",
    search: "Buscar proyectos",
    searchPlaceholder: "Nombre o plataforma",
    projectsList: "Lista de proyectos",
    archive: "Archivar",
    restore: "Restaurar",
    updateError: "No pudimos actualizar el proyecto.",
    newProject: "Nuevo proyecto",
    newProjectHint: "Organiza una campaña",
    recommended: "Plantillas recomendadas",
    seeAll: "Ver todas",
  },
  settings: {
    title: "Configuración",
    tabs: {
      account: "Cuenta",
      business: "Negocio",
      brand: "Marca",
      social: "Conexiones sociales",
      language: "Idioma",
      usage: "Uso",
      privacy: "Privacidad",
      delete: "Eliminar cuenta",
    },
    save: "Guardar cambios",
    saved: "Cambios guardados.",
    loadError: "No pudimos cargar la configuración.",
    saveError: "No pudimos guardar los cambios.",
    partialSave:
      "Guardamos una parte de los cambios; el resto sigue pendiente.",
    noBusiness: "Todavía no hay un negocio configurado.",
    account: {
      name: "Nombre",
      email: "Email",
      emailHint: "El email identifica tu cuenta y no puede editarse aquí.",
      nameRequired: "El nombre no puede quedar vacío.",
    },
    business: {
      name: "Nombre del negocio",
      category: "Categoría",
      country: "País",
      city: "Ciudad",
      description: "Descripción",
      product: "Producto o servicio principal",
      audience: "Audiencia objetivo",
      platforms: "Plataformas preferidas",
      platformsRequired: "Elige al menos una plataforma.",
      objective: "Objetivo principal",
    },
    brand: {
      tones: "Tono de voz",
      tonesHint: "Elige entre 1 y 3 tonos.",
      tonesRequired: "Elige entre 1 y 3 tonos.",
      value: "Propuesta de valor",
      valueRequired: "La propuesta de valor no puede quedar vacía.",
      preferred: "Palabras preferidas",
      forbidden: "Palabras prohibidas",
      wordsHint: "Sepáralas con comas.",
      wordConflict: "Una palabra no puede ser preferida y prohibida a la vez.",
      primaryColor: "Color principal",
      secondaryColor: "Color secundario",
      colorFormat: "Usa un color en formato #RRGGBB.",
    },
    social: {
      title: "Conexiones sociales",
      description:
        "Conecta tus cuentas propias para tenerlas disponibles en HiTrendy.",
      loading: "Cargando conexiones sociales…",
      empty: "Aún no hay cuentas sociales conectadas.",
      loadError: "No pudimos cargar las conexiones sociales.",
      connectError: "No se pudo iniciar la conexión. Vuelve a intentarlo.",
      checkError: "No se pudo comprobar la conexión. Vuelve a intentarlo.",
      disconnectError: "No se pudo desconectar la cuenta. Vuelve a intentarlo.",
      disabled:
        "Las conexiones sociales están desactivadas en esta instalación.",
      providers: {
        instagram: "Instagram",
        tiktok: "TikTok",
        x: "X",
        demo: "Demo",
      },
      providerStatus: {
        available: "Disponible",
        unconfigured: "Sin configurar",
        disabled: "Desactivado",
      },
      providerReason: {
        requires_platform_approval: "Requiere aprobación de la plataforma.",
        requires_paid_plan: "Requiere un plan de pago.",
        not_configured: "Este proveedor no está configurado.",
      },
      connectionStatus: {
        connected: "Conectada",
        expired: "Expirada",
        revoked: "Revocada",
        degraded: "Degradada",
        error: "Con error",
        disconnected: "Desconectada",
      },
      accountTypeLabel: "Tipo de cuenta",
      statusLabel: "Estado",
      accountType: {
        business: "Empresa",
        creator: "Creador",
        personal: "Personal",
        unknown: "Desconocida",
      },
      errors: {
        provider_unavailable: "Proveedor no disponible",
        token_unreadable: "Credencial ilegible",
        revoke_unconfirmed: "Revocación no confirmada",
        invalid_grant: "Autorización inválida",
        token_expired: "Credencial expirada",
        token_revoked: "Credencial revocada",
        insufficient_scope: "Permisos insuficientes",
        unexpected_scope: "Permisos inesperados",
        no_eligible_account: "No hay una cuenta elegible",
        provider_error: "Error del proveedor",
      },
      connect: "Conectar",
      connecting: "Conectando…",
      checking: "Comprobando…",
      disconnecting: "Desconectando…",
      check: "Comprobar conexión",
      disconnect: "Desconectar",
      disconnectQuestion: "¿Desconectar esta cuenta?",
      confirm: "Confirmar desconexión",
      cancel: "Cancelar",
      connectedAt: "Conectada el",
      lastCheckedAt: "Última comprobación",
      callback: {
        connected: "La cuenta de {provider} se conectó correctamente.",
        invalid_request:
          "No pudimos completar la conexión. Vuelve a intentarlo.",
        denied: "La conexión fue cancelada en el proveedor.",
        provider_error: "El proveedor no pudo completar la conexión.",
        unavailable: "Este proveedor no está disponible ahora.",
      },
    },
    language: {
      interface: "Idioma de interfaz",
      content: "Idioma de contenido",
      hint: "El idioma de contenido se usa como valor inicial de nuevas generaciones.",
    },
    usage: {
      title: "Uso de los últimos 30 días",
      note: "Información orientativa, no es una factura.",
      empty: "Aún no hay uso registrado.",
      capability: "Capacidad",
      quality: "Calidad",
      generations: "Generaciones",
      tokens: "Tokens",
      cost: "Costo reportado",
      knownCost: "con costo reportado",
      unknownCost: "sin costo reportado",
      unknown: "Sin dato",
      unknownHint:
        "Un costo desconocido no es cero: el proveedor no lo informó.",
    },
    privacy: {
      title: "Privacidad",
      body: "Guardamos datos de cuenta, negocio y marca. El registro de uso conserva metadata técnica, no prompts ni respuestas completas. Las conexiones OAuth existentes pueden revocarse mediante la eliminación de cuenta.",
    },
    deletion: {
      title: "Eliminar cuenta",
      body: "El acceso se bloquea de inmediato y la purga se ejecuta de forma asíncrona. No se puede deshacer.",
      confirmLabel: "Escribe {phrase} para confirmar",
      confirmError: "Escribe {phrase} para confirmar.",
      request: "Solicitar eliminación",
      blocked: "Acceso bloqueado. La purga continuará de forma asíncrona.",
      followLink: "Seguir el estado de la eliminación",
    },
  },
  deletionStatus: {
    title: "Estado de la eliminación",
    lead: "Esta pantalla no necesita sesión. El seguimiento se guarda solo en esta pestaña.",
    refresh: "Actualizar estado",
    close: "Cerrar seguimiento",
    loading: "Consultando…",
    missing: "No hay un seguimiento activo en esta pestaña.",
    invalid: "El seguimiento no está disponible. Es posible que haya expirado.",
    state: {
      pending: "En cola. La eliminación empezará en breve.",
      processing: "En proceso. Estamos eliminando tus datos.",
      completed: "Completada. Tus datos fueron eliminados.",
      failed:
        "No pudo completarse. Nuestro equipo debe intervenir; tu acceso sigue bloqueado.",
    },
  },
  surfaces: {
    projects: "Proyectos",
    templates: "Plantillas",
    studio: "Studio",
    create: "Crear contenido",
    recent: "Proyectos recientes",
    noProjects: "Todavía no tienes proyectos.",
    chooseTemplate: "Elige una plantilla para empezar.",
    login: "Iniciar sesión",
    register: "Crear cuenta",
    onboarding: "Configuración inicial",
    continue: "Continuar",
    back: "Atrás",
    success: "Listo",
    invalidResponse: "La respuesta no es válida.",
    providerError: "No pudimos completar la generación.",
  },
  options: {
    category: {
      fashion: "Moda",
      art: "Arte",
      lifestyle: "Lifestyle",
      health: "Salud y bienestar",
      gastronomy: "Gastronomía",
      services: "Servicios",
      retail: "Comercio",
      technology: "Tecnología",
      other: "Otra",
    },
    objective: {
      reach: "Alcance",
      engagement: "Interacción",
      sales: "Ventas",
      store_visits: "Visitas a la tienda",
      launch: "Lanzamiento",
      brand_awareness: "Reconocimiento de marca",
      community: "Comunidad",
    },
    tone: {
      friendly: "Cercano",
      professional: "Profesional",
      youthful: "Juvenil",
      elegant: "Elegante",
      fun: "Divertido",
      direct: "Directo",
      inspiring: "Inspirador",
    },
    capability: {
      advisor: "Asesoría",
      copywriter: "Redacción",
      vision_review: "Revisión visual",
      image_generation: "Generación de imágenes",
      video_generation: "Generación de video",
      trend_analysis: "Análisis de tendencias",
    },
    quality: {
      fast: "Rápida",
      balanced: "Equilibrada",
      quality: "Máxima",
    },
  },
};

export type AppCopy = typeof es;

const en: AppCopy = {
  nav: {
    studio: "Studio",
    dashboard: "Dashboard",
    trends: "Trends",
    templates: "Templates",
    settings: "Settings",
    logout: "Sign out",
    loggingOut: "Signing out…",
    mobileLogout: "Sign out",
    notifications: "Notifications",
    sections: "Sections",
    main: "Main navigation",
    mobile: "Mobile navigation",
    home: "HiTrendy, home",
  },
  common: {
    loading: "Loading…",
    saving: "Saving…",
    error: "Something went wrong.",
    empty: "No data yet.",
    retry: "Retry",
    save: "Save",
    cancel: "Cancel",
    close: "Close",
    edit: "Edit",
  },
  dashboard: {
    eyebrow: "DASHBOARD",
    title: "Your creative space",
    subtitle: "Organize projects and find a template for your next idea.",
    tabsLabel: "Dashboard content",
    projects: "Projects",
    templates: "Templates",
    yourProjects: "Your projects",
    startEyebrow: "START DESIGNING",
    projectsHeadline: "All your content, in one place.",
    projectsLead:
      "Pick up a campaign, organize drafts, or continue pending work.",
    templatesHeadline: "Pick a starting point and make it yours.",
    templatesLead:
      "Use a template as a base and personalize it with the Studio.",
    createCta: "Create with HiTrendy",
    startCta: "Start creating",
    statusLabel: "Project status",
    loadingProjects: "Loading projects",
    loadError: "We could not load your projects.",
    noResults: "No projects found",
    noResultsHint: "Try a different search.",
    emptyArchived: "No archived projects",
    emptyActive: "No projects yet",
    emptyHint: "Create your first draft from a template or from scratch.",
    updatedAt: "Updated",
    noActivity: "No activity",
    statusActive: "Active",
    statusArchived: "Archived",
    search: "Search projects",
    searchPlaceholder: "Name or platform",
    projectsList: "Project list",
    archive: "Archive",
    restore: "Restore",
    updateError: "We could not update the project.",
    newProject: "New project",
    newProjectHint: "Organize a campaign",
    recommended: "Recommended templates",
    seeAll: "See all",
  },
  settings: {
    title: "Settings",
    tabs: {
      account: "Account",
      business: "Business",
      brand: "Brand",
      social: "Social connections",
      language: "Language",
      usage: "Usage",
      privacy: "Privacy",
      delete: "Delete account",
    },
    save: "Save changes",
    saved: "Changes saved.",
    loadError: "We could not load your settings.",
    saveError: "We could not save your changes.",
    partialSave: "Part of your changes were saved; the rest is still pending.",
    noBusiness: "There is no business configured yet.",
    account: {
      name: "Name",
      email: "Email",
      emailHint: "Your email identifies the account and cannot be edited here.",
      nameRequired: "The name cannot be empty.",
    },
    business: {
      name: "Business name",
      category: "Category",
      country: "Country",
      city: "City",
      description: "Description",
      product: "Primary product or service",
      audience: "Target audience",
      platforms: "Preferred platforms",
      platformsRequired: "Pick at least one platform.",
      objective: "Primary objective",
    },
    brand: {
      tones: "Voice tone",
      tonesHint: "Pick between 1 and 3 tones.",
      tonesRequired: "Pick between 1 and 3 tones.",
      value: "Value proposition",
      valueRequired: "The value proposition cannot be empty.",
      preferred: "Preferred words",
      forbidden: "Forbidden words",
      wordsHint: "Separate them with commas.",
      wordConflict:
        "A word cannot be preferred and forbidden at the same time.",
      primaryColor: "Primary color",
      secondaryColor: "Secondary color",
      colorFormat: "Use a color in #RRGGBB format.",
    },
    social: {
      title: "Social connections",
      description:
        "Connect your own accounts so they are available in HiTrendy.",
      loading: "Loading social connections…",
      empty: "No social accounts are connected yet.",
      loadError: "We could not load social connections.",
      connectError: "The connection could not be started. Try again.",
      checkError: "The connection could not be checked. Try again.",
      disconnectError: "The account could not be disconnected. Try again.",
      disabled: "Social connections are disabled in this installation.",
      providers: {
        instagram: "Instagram",
        tiktok: "TikTok",
        x: "X",
        demo: "Demo",
      },
      providerStatus: {
        available: "Available",
        unconfigured: "Unconfigured",
        disabled: "Disabled",
      },
      providerReason: {
        requires_platform_approval: "Platform approval is required.",
        requires_paid_plan: "A paid plan is required.",
        not_configured: "This provider is not configured.",
      },
      connectionStatus: {
        connected: "Connected",
        expired: "Expired",
        revoked: "Revoked",
        degraded: "Degraded",
        error: "Error",
        disconnected: "Disconnected",
      },
      accountTypeLabel: "Account type",
      statusLabel: "Status",
      accountType: {
        business: "Business",
        creator: "Creator",
        personal: "Personal",
        unknown: "Unknown",
      },
      errors: {
        provider_unavailable: "Provider unavailable",
        token_unreadable: "Credential unreadable",
        revoke_unconfirmed: "Revocation unconfirmed",
        invalid_grant: "Invalid authorization",
        token_expired: "Credential expired",
        token_revoked: "Credential revoked",
        insufficient_scope: "Insufficient permissions",
        unexpected_scope: "Unexpected permissions",
        no_eligible_account: "No eligible account",
        provider_error: "Provider error",
      },
      connect: "Connect",
      connecting: "Connecting…",
      checking: "Checking…",
      disconnecting: "Disconnecting…",
      check: "Check connection",
      disconnect: "Disconnect",
      disconnectQuestion: "Disconnect this account?",
      confirm: "Confirm disconnect",
      cancel: "Cancel",
      connectedAt: "Connected on",
      lastCheckedAt: "Last checked",
      callback: {
        connected: "The {provider} account was connected successfully.",
        invalid_request:
          "We could not complete the connection. Please try again.",
        denied: "The connection was canceled at the provider.",
        provider_error: "The provider could not complete the connection.",
        unavailable: "This provider is not available right now.",
      },
    },
    language: {
      interface: "Interface language",
      content: "Content language",
      hint: "The content language is the starting value for new generations.",
    },
    usage: {
      title: "Usage in the last 30 days",
      note: "Informational only; this is not an invoice.",
      empty: "No usage recorded yet.",
      capability: "Capability",
      quality: "Quality",
      generations: "Generations",
      tokens: "Tokens",
      cost: "Reported cost",
      knownCost: "with a reported cost",
      unknownCost: "without a reported cost",
      unknown: "Not reported",
      unknownHint:
        "An unknown cost is not zero: the provider did not report it.",
    },
    privacy: {
      title: "Privacy",
      body: "We store account, business, and brand data. The usage ledger keeps technical metadata, not full prompts or responses. Existing OAuth connections can be revoked by deleting the account.",
    },
    deletion: {
      title: "Delete account",
      body: "Access is blocked immediately and purging runs asynchronously. This cannot be undone.",
      confirmLabel: "Type {phrase} to confirm",
      confirmError: "Type {phrase} to confirm.",
      request: "Request deletion",
      blocked: "Access blocked. Purging will continue asynchronously.",
      followLink: "Follow the deletion status",
    },
  },
  deletionStatus: {
    title: "Deletion status",
    lead: "This screen needs no session. The tracker is stored in this tab only.",
    refresh: "Refresh status",
    close: "Close tracker",
    loading: "Checking…",
    missing: "There is no active tracker in this tab.",
    invalid: "The tracker is not available. It may have expired.",
    state: {
      pending: "Queued. Deletion will start shortly.",
      processing: "In progress. We are deleting your data.",
      completed: "Completed. Your data has been deleted.",
      failed:
        "It could not be completed. Our team must step in; your access stays blocked.",
    },
  },
  surfaces: {
    projects: "Projects",
    templates: "Templates",
    studio: "Studio",
    create: "Create content",
    recent: "Recent projects",
    noProjects: "You do not have projects yet.",
    chooseTemplate: "Choose a template to get started.",
    login: "Sign in",
    register: "Create account",
    onboarding: "Initial setup",
    continue: "Continue",
    back: "Back",
    success: "Done",
    invalidResponse: "The response is not valid.",
    providerError: "We could not complete the generation.",
  },
  options: {
    category: {
      fashion: "Fashion",
      art: "Art",
      lifestyle: "Lifestyle",
      health: "Health and wellness",
      gastronomy: "Food and drink",
      services: "Services",
      retail: "Retail",
      technology: "Technology",
      other: "Other",
    },
    objective: {
      reach: "Reach",
      engagement: "Engagement",
      sales: "Sales",
      store_visits: "Store visits",
      launch: "Launch",
      brand_awareness: "Brand awareness",
      community: "Community",
    },
    tone: {
      friendly: "Friendly",
      professional: "Professional",
      youthful: "Youthful",
      elegant: "Elegant",
      fun: "Fun",
      direct: "Direct",
      inspiring: "Inspiring",
    },
    capability: {
      advisor: "Advice",
      copywriter: "Copywriting",
      vision_review: "Visual review",
      image_generation: "Image generation",
      video_generation: "Video generation",
      trend_analysis: "Trend analysis",
    },
    quality: {
      fast: "Fast",
      balanced: "Balanced",
      quality: "Highest",
    },
  },
};

const pt: AppCopy = {
  nav: {
    studio: "Studio",
    dashboard: "Dashboard",
    trends: "Tendências",
    templates: "Templates",
    settings: "Configurações",
    logout: "Sair",
    loggingOut: "Saindo…",
    mobileLogout: "Sair",
    notifications: "Notificações",
    sections: "Seções",
    main: "Navegação principal",
    mobile: "Navegação móvel",
    home: "HiTrendy, início",
  },
  common: {
    loading: "Carregando…",
    saving: "Salvando…",
    error: "Ocorreu um erro.",
    empty: "Ainda não há dados.",
    retry: "Tentar novamente",
    save: "Salvar",
    cancel: "Cancelar",
    close: "Fechar",
    edit: "Editar",
  },
  dashboard: {
    eyebrow: "PAINEL",
    title: "Seu espaço criativo",
    subtitle: "Organize projetos e encontre um template para a próxima ideia.",
    tabsLabel: "Conteúdo do painel",
    projects: "Projetos",
    templates: "Templates",
    yourProjects: "Seus projetos",
    startEyebrow: "COMECE A CRIAR",
    projectsHeadline: "Todo o seu conteúdo em um só lugar.",
    projectsLead:
      "Retome uma campanha, organize rascunhos ou continue o trabalho pendente.",
    templatesHeadline: "Escolha uma base e deixe-a com a sua cara.",
    templatesLead:
      "Use um template como ponto de partida e personalize com o Studio.",
    createCta: "Criar com a HiTrendy",
    startCta: "Começar a criar",
    statusLabel: "Status dos projetos",
    loadingProjects: "Carregando projetos",
    loadError: "Não foi possível carregar seus projetos.",
    noResults: "Nenhum projeto encontrado",
    noResultsHint: "Tente outra busca.",
    emptyArchived: "Não há projetos arquivados",
    emptyActive: "Ainda não há projetos",
    emptyHint: "Crie seu primeiro rascunho a partir de um template ou do zero.",
    updatedAt: "Atualizado",
    noActivity: "Sem atividade",
    statusActive: "Ativos",
    statusArchived: "Arquivados",
    search: "Buscar projetos",
    searchPlaceholder: "Nome ou plataforma",
    projectsList: "Lista de projetos",
    archive: "Arquivar",
    restore: "Restaurar",
    updateError: "Não foi possível atualizar o projeto.",
    newProject: "Novo projeto",
    newProjectHint: "Organize uma campanha",
    recommended: "Templates recomendados",
    seeAll: "Ver todos",
  },
  settings: {
    title: "Configurações",
    tabs: {
      account: "Conta",
      business: "Negócio",
      brand: "Marca",
      social: "Conexões sociais",
      language: "Idioma",
      usage: "Uso",
      privacy: "Privacidade",
      delete: "Excluir conta",
    },
    save: "Salvar alterações",
    saved: "Alterações salvas.",
    loadError: "Não foi possível carregar as configurações.",
    saveError: "Não foi possível salvar as alterações.",
    partialSave:
      "Parte das alterações foi salva; o restante continua pendente.",
    noBusiness: "Ainda não há um negócio configurado.",
    account: {
      name: "Nome",
      email: "E-mail",
      emailHint: "O e-mail identifica a conta e não pode ser editado aqui.",
      nameRequired: "O nome não pode ficar vazio.",
    },
    business: {
      name: "Nome do negócio",
      category: "Categoria",
      country: "País",
      city: "Cidade",
      description: "Descrição",
      product: "Produto ou serviço principal",
      audience: "Público-alvo",
      platforms: "Plataformas preferidas",
      platformsRequired: "Escolha pelo menos uma plataforma.",
      objective: "Objetivo principal",
    },
    brand: {
      tones: "Tom de voz",
      tonesHint: "Escolha de 1 a 3 tons.",
      tonesRequired: "Escolha de 1 a 3 tons.",
      value: "Proposta de valor",
      valueRequired: "A proposta de valor não pode ficar vazia.",
      preferred: "Palavras preferidas",
      forbidden: "Palavras proibidas",
      wordsHint: "Separe por vírgulas.",
      wordConflict:
        "Uma palavra não pode ser preferida e proibida ao mesmo tempo.",
      primaryColor: "Cor principal",
      secondaryColor: "Cor secundária",
      colorFormat: "Use uma cor no formato #RRGGBB.",
    },
    social: {
      title: "Conexões sociais",
      description:
        "Conecte suas contas próprias para deixá-las disponíveis na HiTrendy.",
      loading: "Carregando conexões sociais…",
      empty: "Ainda não há contas sociais conectadas.",
      loadError: "Não foi possível carregar as conexões sociais.",
      connectError: "Não foi possível iniciar a conexão. Tente novamente.",
      checkError: "Não foi possível verificar a conexão. Tente novamente.",
      disconnectError: "Não foi possível desconectar a conta. Tente novamente.",
      disabled: "As conexões sociais estão desativadas nesta instalação.",
      providers: {
        instagram: "Instagram",
        tiktok: "TikTok",
        x: "X",
        demo: "Demo",
      },
      providerStatus: {
        available: "Disponível",
        unconfigured: "Não configurado",
        disabled: "Desativado",
      },
      providerReason: {
        requires_platform_approval: "É necessária a aprovação da plataforma.",
        requires_paid_plan: "É necessário um plano pago.",
        not_configured: "Este provedor não está configurado.",
      },
      connectionStatus: {
        connected: "Conectada",
        expired: "Expirada",
        revoked: "Revogada",
        degraded: "Degradada",
        error: "Com erro",
        disconnected: "Desconectada",
      },
      accountTypeLabel: "Tipo de conta",
      statusLabel: "Status",
      accountType: {
        business: "Empresa",
        creator: "Criador",
        personal: "Pessoal",
        unknown: "Desconhecida",
      },
      errors: {
        provider_unavailable: "Provedor indisponível",
        token_unreadable: "Credencial ilegível",
        revoke_unconfirmed: "Revogação não confirmada",
        invalid_grant: "Autorização inválida",
        token_expired: "Credencial expirada",
        token_revoked: "Credencial revogada",
        insufficient_scope: "Permissões insuficientes",
        unexpected_scope: "Permissões inesperadas",
        no_eligible_account: "Nenhuma conta elegível",
        provider_error: "Erro do provedor",
      },
      connect: "Conectar",
      connecting: "Conectando…",
      checking: "Verificando…",
      disconnecting: "Desconectando…",
      check: "Verificar conexão",
      disconnect: "Desconectar",
      disconnectQuestion: "Desconectar esta conta?",
      confirm: "Confirmar desconexão",
      cancel: "Cancelar",
      connectedAt: "Conectada em",
      lastCheckedAt: "Última verificação",
      callback: {
        connected: "A conta do {provider} foi conectada com sucesso.",
        invalid_request:
          "Não foi possível concluir a conexão. Tente novamente.",
        denied: "A conexão foi cancelada no provedor.",
        provider_error: "O provedor não conseguiu concluir a conexão.",
        unavailable: "Este provedor não está disponível agora.",
      },
    },
    language: {
      interface: "Idioma da interface",
      content: "Idioma do conteúdo",
      hint: "O idioma do conteúdo é o valor inicial de novas gerações.",
    },
    usage: {
      title: "Uso dos últimos 30 dias",
      note: "Apenas informativo; não é uma fatura.",
      empty: "Ainda não há uso registrado.",
      capability: "Capacidade",
      quality: "Qualidade",
      generations: "Gerações",
      tokens: "Tokens",
      cost: "Custo informado",
      knownCost: "com custo informado",
      unknownCost: "sem custo informado",
      unknown: "Sem dado",
      unknownHint: "Um custo desconhecido não é zero: o provedor não informou.",
    },
    privacy: {
      title: "Privacidade",
      body: "Armazenamos dados da conta, do negócio e da marca. O registro de uso guarda metadados técnicos, não prompts ou respostas completas. Conexões OAuth existentes podem ser revogadas ao excluir a conta.",
    },
    deletion: {
      title: "Excluir conta",
      body: "O acesso é bloqueado imediatamente e a limpeza roda de forma assíncrona. Não é possível desfazer.",
      confirmLabel: "Digite {phrase} para confirmar",
      confirmError: "Digite {phrase} para confirmar.",
      request: "Solicitar exclusão",
      blocked: "Acesso bloqueado. A limpeza continuará de forma assíncrona.",
      followLink: "Acompanhar o status da exclusão",
    },
  },
  deletionStatus: {
    title: "Status da exclusão",
    lead: "Esta tela não precisa de sessão. O acompanhamento fica apenas nesta aba.",
    refresh: "Atualizar status",
    close: "Fechar acompanhamento",
    loading: "Consultando…",
    missing: "Não há acompanhamento ativo nesta aba.",
    invalid: "O acompanhamento não está disponível. Pode ter expirado.",
    state: {
      pending: "Na fila. A exclusão começará em breve.",
      processing: "Em andamento. Estamos excluindo seus dados.",
      completed: "Concluída. Seus dados foram excluídos.",
      failed:
        "Não foi possível concluir. Nossa equipe precisa intervir; seu acesso segue bloqueado.",
    },
  },
  surfaces: {
    projects: "Projetos",
    templates: "Templates",
    studio: "Studio",
    create: "Criar conteúdo",
    recent: "Projetos recentes",
    noProjects: "Você ainda não tem projetos.",
    chooseTemplate: "Escolha um template para começar.",
    login: "Entrar",
    register: "Criar conta",
    onboarding: "Configuração inicial",
    continue: "Continuar",
    back: "Voltar",
    success: "Pronto",
    invalidResponse: "A resposta não é válida.",
    providerError: "Não foi possível concluir a geração.",
  },
  options: {
    category: {
      fashion: "Moda",
      art: "Arte",
      lifestyle: "Lifestyle",
      health: "Saúde e bem-estar",
      gastronomy: "Gastronomia",
      services: "Serviços",
      retail: "Varejo",
      technology: "Tecnologia",
      other: "Outra",
    },
    objective: {
      reach: "Alcance",
      engagement: "Engajamento",
      sales: "Vendas",
      store_visits: "Visitas à loja",
      launch: "Lançamento",
      brand_awareness: "Reconhecimento de marca",
      community: "Comunidade",
    },
    tone: {
      friendly: "Próximo",
      professional: "Profissional",
      youthful: "Jovem",
      elegant: "Elegante",
      fun: "Divertido",
      direct: "Direto",
      inspiring: "Inspirador",
    },
    capability: {
      advisor: "Consultoria",
      copywriter: "Redação",
      vision_review: "Revisão visual",
      image_generation: "Geração de imagens",
      video_generation: "Geração de vídeo",
      trend_analysis: "Análise de tendências",
    },
    quality: {
      fast: "Rápida",
      balanced: "Equilibrada",
      quality: "Máxima",
    },
  },
};

export const appCopy: Record<AppLocale, AppCopy> = { es, en, pt };

export function isSupportedLocale(value: unknown): value is AppLocale {
  return (
    typeof value === "string" && supportedLocales.includes(value as AppLocale)
  );
}

export function copyFor(locale: string | null | undefined): AppCopy {
  return appCopy[isSupportedLocale(locale) ? locale : defaultLocale];
}

function lookup(source: unknown, path: string): string | undefined {
  let current: unknown = source;
  for (const segment of path.split(".")) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return typeof current === "string" ? current : undefined;
}

/**
 * Resolve a dotted catalog path, falling back to Spanish. A path that exists in
 * no locale resolves to an empty string: users never see a raw key.
 */
export function translate(
  locale: string | null | undefined,
  path: string,
  values: Record<string, string | number> = {}
): string {
  const active = isSupportedLocale(locale) ? locale : defaultLocale;
  const template =
    lookup(appCopy[active], path) ?? lookup(appCopy[defaultLocale], path) ?? "";
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match
  );
}

/** Localized label for a backend identifier, keeping the identifier if unknown. */
export function optionLabel(
  locale: AppLocale,
  group: string,
  value: string
): string {
  return translate(locale, `options.${group}.${value}`) || value;
}

export function formatNumber(
  locale: AppLocale,
  value: number | null | undefined,
  options: Intl.NumberFormatOptions = {}
): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "";
  return new Intl.NumberFormat(localeTags[locale], options).format(value);
}

export function formatDate(
  locale: AppLocale,
  value: string | Date | null | undefined
): string {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(localeTags[locale], {
    dateStyle: "medium",
  }).format(date);
}

/**
 * Format a reported cost. The amount arrives as a decimal string so no
 * precision is lost on the way; an unknown currency degrades to a plain number.
 */
export function formatCost(
  locale: AppLocale,
  amount: string | number | null | undefined,
  currency: string | null | undefined
): string {
  if (amount === null || amount === undefined || amount === "") return "";
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return "";
  const code =
    typeof currency === "string" ? currency.trim().toUpperCase() : "";
  if (/^[A-Z]{3}$/.test(code)) {
    try {
      return new Intl.NumberFormat(localeTags[locale], {
        style: "currency",
        currency: code,
        maximumFractionDigits: 6,
      }).format(value);
    } catch {
      // An unsupported code should not break the screen.
    }
  }
  const plain = formatNumber(locale, value, { maximumFractionDigits: 6 });
  return code ? `${plain} ${code}` : plain;
}

export function readStoredLocale(): AppLocale {
  if (typeof window === "undefined") return defaultLocale;
  const value = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  return isSupportedLocale(value) ? value : defaultLocale;
}

export function setStoredLocale(locale: AppLocale): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  window.dispatchEvent(
    new CustomEvent<AppLocale>(LOCALE_EVENT, { detail: locale })
  );
}

/** Reactive interface locale. localStorage is only the initial cache; Settings
 * persists the selected value through the account endpoint and emits this event
 * so already-mounted screens update without a reload. */
export function useInterfaceLocale(): AppLocale {
  const [locale, setLocale] = useState<AppLocale>(readStoredLocale);
  useEffect(() => {
    const onLocale = (event: Event) => {
      const next = (event as CustomEvent<unknown>).detail;
      if (isSupportedLocale(next)) setLocale(next);
    };
    window.addEventListener(LOCALE_EVENT, onLocale);
    return () => window.removeEventListener(LOCALE_EVENT, onLocale);
  }, []);
  return locale;
}

/** Copy for the routes added before the common catalog existed.  Keep user
 * supplied values (business names, messages, URLs and IDs) out of this map. */
export const surfaceCopy = {
  es: {
    templates: {
      library: "Biblioteca de plantillas",
      eyebrow: "BIBLIOTECA CREATIVA",
      title: "Explora plantillas",
      lead: "Encuentra una base por formato, categoría o tema.",
      search: "Buscar plantillas",
      searchPlaceholder: "Buscar por nombre, formato o tema...",
      categories: "Categorías de plantillas",
      singular: "plantilla",
      plural: "plantillas",
      use: "Usar plantilla",
      preparing: "Preparando…",
      empty: "No encontramos plantillas",
      emptyHint: "Prueba otra búsqueda o selecciona una categoría diferente.",
      preview: "Vista previa",
      unavailable: "Vista previa no disponible",
      loading: "Preparando catálogo…",
      error: "No pudimos comprobar las plantillas.",
      carousel: "Plantillas recomendadas para tu negocio",
      previous: "Anterior",
      next: "Siguiente",
      whyPrefix: "Por qué",
      originCustom: "Origen: plantilla de HiTrendy",
      originCanva: "Origen: plantilla de Canva",
      openInCanva: "Abrir en Canva",
      canvaUnavailable: "Enlace no disponible",
    },
    auth: {
      demoLabel: "Contenido de ejemplo de HiTrendy",
      heroTitle: "Convierte una idea en algo que la gente quiera compartir.",
      heroLead:
        "Publicaciones, campañas y guiones que parten de la identidad de tu negocio.",
      welcome: "¡Bienvenido de vuelta!",
      loginLead: "Ingresa tus datos para seguir creando.",
      email: "Correo electrónico",
      password: "Contraseña",
      showPassword: "Mostrar contraseña",
      hidePassword: "Ocultar contraseña",
      rememberMe: "Recordarme",
      forgotPassword: "¿Olvidaste tu contraseña?",
      divider: "o",
      login: "Iniciar sesión",
      loggingIn: "Iniciando sesión…",
      noAccount: "¿No tienes cuenta?",
      registerLink: "Regístrate",
      loginFallback: "No pudimos iniciar sesión.",
      loginLoading: "Preparando inicio de sesión…",
      register: "Crea tu cuenta",
      registerLead:
        "Primero creemos tu cuenta. Después conoceremos tu negocio para preparar tu espacio en HiTrendy.",
      name: "Tu nombre",
      passwordHint: "Usa al menos 12 caracteres.",
      inviteCode: "Código de invitación",
      inviteCodeOptional: "Opcional",
      inviteCodePlaceholder: "Código de beta",
      interfaceLocale: "Idioma de la interfaz",
      create: "Crear cuenta",
      creating: "Creando cuenta…",
      hasAccount: "¿Ya tienes cuenta?",
      loginLink: "Inicia sesión",
      registerFallback: "No pudimos crear tu cuenta.",
      googleOpening: "Abriendo Google…",
      googleChecking: "Comprobando Google…",
      googleContinue: "Continuar con Google",
      googleUnavailable: "Google no está disponible en este momento.",
      googleFallback: "No pudimos iniciar el acceso con Google.",
    },
    onboarding: {
      steps: [
        "Tu negocio",
        "Canales y objetivo",
        "Identidad de marca",
        "Confirmación",
      ],
      eyebrow: "PRIMEROS PASOS",
      title: "Configura tu negocio",
      exit: "Salir",
      label: "Configuración inicial",
      loading: "Recuperando tu registro…",
      saving: "Guardando este paso…",
      creating: "Creando tu cuenta…",
      saved: "Tus datos se guardan en tu cuenta.",
      retrying: "Hubo un problema temporal. Reintentando…",
      back: "Anterior",
      next: "Siguiente",
      version: "Versión guardada",
      keyboard:
        "Puedes usar Enter para avanzar y Tab para recorrer los campos.",
      businessTitle: "Cuéntanos sobre tu negocio",
      businessLead:
        "Usaremos este contexto para que tus primeras recomendaciones sean útiles desde el inicio.",
      businessName: "Nombre comercial",
      category: "Categoría",
      select: "Seleccionar…",
      country: "País",
      city: "Ciudad",
      product: "Producto o servicio principal",
      audience: "¿A quién ayudas?",
      audiencePlaceholder:
        "Ej: Personas que buscan una pausa cercana y de calidad",
      description: "Descripción del negocio",
      website: "Sitio web",
      optional: "Opcional",
      channelsTitle: "Canales y objetivos",
      channelsLead:
        "Elige dónde quieres concentrar tus próximos contenidos y qué esperas conseguir.",
      platforms: "Redes sociales que usas",
      objective: "Objetivo principal",
      brandTitle: "Identidad de marca",
      brandLead:
        "Define una primera dirección para que el contenido conserve la personalidad de tu negocio.",
      tones: "Tonos de voz (máx. 3)",
      proposition: "Propuesta de valor",
      propositionPlaceholder: "Ej: Café artesanal de origen responsable",
      preferred: "Palabras preferidas",
      forbidden: "Palabras prohibidas",
      wordsPlaceholder: "Separadas por comas",
      primaryColor: "Color primario",
      secondaryColor: "Color secundario",
      contentLocale: "Idioma predeterminado del contenido",
      reviewTitle: "Revisa tu información",
      reviewLead:
        "Esto es lo que entendimos de tu negocio. Podrás editarlo después desde Configuración.",
      business: "Negocio",
      channels: "Canales y objetivo",
      brand: "Marca",
      location: "Ubicación",
      confirm: "Confirmo que la información es correcta.",
      finish: "Finalizar y entrar a HiTrendy",
      finishing: "Finalizando…",
      progress: "Progreso de registro",
      progressLabel: "Paso {current} de {total}: {label}",
      required: "Obligatorio",
      requiredHint: "Los campos marcados con * son obligatorios.",
      missingBusiness:
        "Completa los datos obligatorios de tu negocio para continuar.",
      missingChannels:
        "Elige al menos una red social y un objetivo principal para continuar.",
      missingBrand:
        "Elige al menos un tono de voz y escribe tu propuesta de valor para continuar.",
      missingReview:
        "Confirma que la información es correcta para finalizar tu registro.",
    },
  },
  en: {
    templates: {
      library: "Template library",
      eyebrow: "CREATIVE LIBRARY",
      title: "Explore templates",
      lead: "Find a starting point by format, category, or theme.",
      search: "Search templates",
      searchPlaceholder: "Search by name, format, or theme...",
      categories: "Template categories",
      singular: "template",
      plural: "templates",
      use: "Use template",
      preparing: "Preparing…",
      empty: "No templates found",
      emptyHint: "Try another search or select a different category.",
      preview: "Preview",
      unavailable: "Preview unavailable",
      loading: "Preparing catalog…",
      error: "We could not check the templates.",
      carousel: "Templates recommended for your business",
      previous: "Previous",
      next: "Next",
      whyPrefix: "Why",
      originCustom: "Source: HiTrendy template",
      originCanva: "Source: Canva template",
      openInCanva: "Open in Canva",
      canvaUnavailable: "Link unavailable",
    },
    auth: {
      demoLabel: "HiTrendy sample content",
      heroTitle: "Turn an idea into something people want to share.",
      heroLead:
        "Posts, campaigns, and scripts rooted in your business identity.",
      welcome: "Welcome back",
      loginLead: "Enter your details to keep creating.",
      email: "Email",
      password: "Password",
      showPassword: "Show password",
      hidePassword: "Hide password",
      rememberMe: "Remember me",
      forgotPassword: "Forgot your password?",
      divider: "or",
      login: "Sign in",
      loggingIn: "Signing in…",
      noAccount: "Don't have an account?",
      registerLink: "Sign up",
      loginFallback: "We could not sign you in.",
      loginLoading: "Preparing sign in…",
      register: "Create your account",
      registerLead:
        "First, let's create your account. Then we'll learn about your business to prepare your HiTrendy space.",
      name: "Your name",
      passwordHint: "Use at least 12 characters.",
      inviteCode: "Invite code",
      inviteCodeOptional: "Optional",
      inviteCodePlaceholder: "Beta code",
      interfaceLocale: "Interface language",
      create: "Create account",
      creating: "Creating account…",
      hasAccount: "Already have an account?",
      loginLink: "Sign in",
      registerFallback: "We could not create your account.",
      googleOpening: "Opening Google…",
      googleChecking: "Checking Google…",
      googleContinue: "Continue with Google",
      googleUnavailable: "Google is not available right now.",
      googleFallback: "We could not start Google sign-in.",
    },
    onboarding: {
      steps: [
        "Your business",
        "Channels and goal",
        "Brand identity",
        "Confirmation",
      ],
      eyebrow: "GETTING STARTED",
      title: "Set up your business",
      exit: "Exit",
      label: "Initial setup",
      loading: "Restoring your registration…",
      saving: "Saving this step…",
      creating: "Creating your account…",
      saved: "Your information is saved to your account.",
      retrying: "There was a temporary issue. Retrying…",
      back: "Back",
      next: "Next",
      version: "Saved version",
      keyboard: "You can use Enter to continue and Tab to move through fields.",
      businessTitle: "Tell us about your business",
      businessLead:
        "We will use this context to make your first recommendations useful from the start.",
      businessName: "Business name",
      category: "Category",
      select: "Select…",
      country: "Country",
      city: "City",
      product: "Main product or service",
      audience: "Who do you help?",
      audiencePlaceholder:
        "Example: People looking for a nearby, quality break",
      description: "Business description",
      website: "Website",
      optional: "Optional",
      channelsTitle: "Channels and goals",
      channelsLead:
        "Choose where you want to focus your next content and what you expect to achieve.",
      platforms: "Social networks you use",
      objective: "Main goal",
      brandTitle: "Brand identity",
      brandLead:
        "Set a first direction so the content keeps your business personality.",
      tones: "Voice tones (max. 3)",
      proposition: "Value proposition",
      propositionPlaceholder: "Example: Responsibly sourced artisan coffee",
      preferred: "Preferred words",
      forbidden: "Forbidden words",
      wordsPlaceholder: "Separated by commas",
      primaryColor: "Primary color",
      secondaryColor: "Secondary color",
      contentLocale: "Default content language",
      reviewTitle: "Review your information",
      reviewLead:
        "This is what we understood about your business. You can edit it later in Settings.",
      business: "Business",
      channels: "Channels and goal",
      brand: "Brand",
      location: "Location",
      confirm: "I confirm that the information is correct.",
      finish: "Finish and enter HiTrendy",
      finishing: "Finishing…",
      progress: "Registration progress",
      progressLabel: "Step {current} of {total}: {label}",
      required: "Required",
      requiredHint: "Fields marked with * are required.",
      missingBusiness:
        "Complete the required details about your business to continue.",
      missingChannels:
        "Choose at least one social network and a main goal to continue.",
      missingBrand:
        "Choose at least one voice tone and write your value proposition to continue.",
      missingReview:
        "Confirm that the information is correct to finish your registration.",
    },
  },
  pt: {
    templates: {
      library: "Biblioteca de templates",
      eyebrow: "BIBLIOTECA CRIATIVA",
      title: "Explore templates",
      lead: "Encontre uma base por formato, categoria ou tema.",
      search: "Buscar templates",
      searchPlaceholder: "Buscar por nome, formato ou tema...",
      categories: "Categorias de templates",
      singular: "template",
      plural: "templates",
      use: "Usar template",
      preparing: "Preparando…",
      empty: "Nenhum template encontrado",
      emptyHint: "Tente outra busca ou selecione uma categoria diferente.",
      preview: "Prévia",
      unavailable: "Prévia indisponível",
      loading: "Preparando catálogo…",
      error: "Não foi possível verificar os templates.",
      carousel: "Modelos recomendados para o seu negócio",
      previous: "Anterior",
      next: "Próximo",
      whyPrefix: "Por quê",
      originCustom: "Origem: template da HiTrendy",
      originCanva: "Origem: template do Canva",
      openInCanva: "Abrir no Canva",
      canvaUnavailable: "Link indisponível",
    },
    auth: {
      demoLabel: "Conteúdo de exemplo da HiTrendy",
      heroTitle:
        "Transforme uma ideia em algo que as pessoas queiram compartilhar.",
      heroLead:
        "Posts, campanhas e roteiros que partem da identidade do seu negócio.",
      welcome: "Boas-vindas de volta",
      loginLead: "Informe seus dados para continuar criando.",
      email: "E-mail",
      password: "Senha",
      showPassword: "Mostrar senha",
      hidePassword: "Ocultar senha",
      rememberMe: "Lembrar de mim",
      forgotPassword: "Esqueceu sua senha?",
      divider: "ou",
      login: "Entrar",
      loggingIn: "Entrando…",
      noAccount: "Não tem uma conta?",
      registerLink: "Cadastre-se",
      loginFallback: "Não foi possível entrar.",
      loginLoading: "Preparando acesso…",
      register: "Crie sua conta",
      registerLead:
        "Primeiro, vamos criar sua conta. Depois conheceremos seu negócio para preparar seu espaço na HiTrendy.",
      name: "Seu nome",
      passwordHint: "Use pelo menos 12 caracteres.",
      inviteCode: "Código de convite",
      inviteCodeOptional: "Opcional",
      inviteCodePlaceholder: "Código beta",
      interfaceLocale: "Idioma da interface",
      create: "Criar conta",
      creating: "Criando conta…",
      hasAccount: "Já tem uma conta?",
      loginLink: "Entrar",
      registerFallback: "Não foi possível criar sua conta.",
      googleOpening: "Abrindo o Google…",
      googleChecking: "Verificando o Google…",
      googleContinue: "Continuar com o Google",
      googleUnavailable: "O Google não está disponível agora.",
      googleFallback: "Não foi possível iniciar o acesso pelo Google.",
    },
    onboarding: {
      steps: [
        "Seu negócio",
        "Canais e objetivo",
        "Identidade da marca",
        "Confirmação",
      ],
      eyebrow: "PRIMEIROS PASSOS",
      title: "Configure seu negócio",
      exit: "Sair",
      label: "Configuração inicial",
      loading: "Recuperando seu cadastro…",
      saving: "Salvando esta etapa…",
      creating: "Criando sua conta…",
      saved: "Seus dados são salvos na sua conta.",
      retrying: "Houve um problema temporário. Tentando novamente…",
      back: "Voltar",
      next: "Próximo",
      version: "Versão salva",
      keyboard:
        "Você pode usar Enter para avançar e Tab para percorrer os campos.",
      businessTitle: "Conte-nos sobre seu negócio",
      businessLead:
        "Usaremos este contexto para que suas primeiras recomendações sejam úteis desde o início.",
      businessName: "Nome comercial",
      category: "Categoria",
      select: "Selecionar…",
      country: "País",
      city: "Cidade",
      product: "Produto ou serviço principal",
      audience: "Quem você ajuda?",
      audiencePlaceholder:
        "Ex.: Pessoas que procuram uma pausa próxima e de qualidade",
      description: "Descrição do negócio",
      website: "Site",
      optional: "Opcional",
      channelsTitle: "Canais e objetivos",
      channelsLead:
        "Escolha onde você quer concentrar seus próximos conteúdos e o que espera alcançar.",
      platforms: "Redes sociais que você usa",
      objective: "Objetivo principal",
      brandTitle: "Identidade da marca",
      brandLead:
        "Defina uma primeira direção para que o conteúdo preserve a personalidade do seu negócio.",
      tones: "Tons de voz (máx. 3)",
      proposition: "Proposta de valor",
      propositionPlaceholder: "Ex.: Café artesanal de origem responsável",
      preferred: "Palavras preferidas",
      forbidden: "Palavras proibidas",
      wordsPlaceholder: "Separadas por vírgulas",
      primaryColor: "Cor primária",
      secondaryColor: "Cor secundária",
      contentLocale: "Idioma padrão do conteúdo",
      reviewTitle: "Revise suas informações",
      reviewLead:
        "Foi isso que entendemos sobre seu negócio. Você poderá editar depois em Configurações.",
      business: "Negócio",
      channels: "Canais e objetivo",
      brand: "Marca",
      location: "Localização",
      confirm: "Confirmo que as informações estão corretas.",
      finish: "Finalizar e entrar na HiTrendy",
      finishing: "Finalizando…",
      progress: "Progresso do cadastro",
      progressLabel: "Etapa {current} de {total}: {label}",
      required: "Obrigatório",
      requiredHint: "Os campos marcados com * são obrigatórios.",
      missingBusiness:
        "Preencha os dados obrigatórios do seu negócio para continuar.",
      missingChannels:
        "Escolha pelo menos uma rede social e um objetivo principal para continuar.",
      missingBrand:
        "Escolha pelo menos um tom de voz e escreva sua proposta de valor para continuar.",
      missingReview:
        "Confirme que as informações estão corretas para finalizar seu cadastro.",
    },
  },
} as const;
