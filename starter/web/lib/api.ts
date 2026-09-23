import { cloneDemo, demoData } from "@/lib/demo-data";
import {
  isDemoModeEnabled,
  readDemoProjects,
  saveDemoProjects,
} from "@/lib/demo-mode";
import type { Category, Objective, Platform } from "@/types/business";
import type { Tone } from "@/types/brand";
import type { PublicCapabilities } from "@/types/capabilities";
import type {
  ImageAspectRatio,
  ImageBriefDraft,
  ImageJob,
  ImagePreflight,
  VisualBrief,
} from "@/types/images";
import type {
  VideoAspectRatio,
  VideoJob,
  VideoPreflight,
  VideoStoryboard,
  VideoStoryboardDraft,
} from "@/types/videos";
import type {
  TrendCard,
  TrendDetail,
  TrendHome,
  TrendRefreshResult,
  TrendRefreshScope,
  TrendSource,
} from "@/types/trends";
import type {
  SocialAuthorizeResult,
  SocialConnection,
  SocialConnectionsResponse,
} from "@/types/social";

let _csrfToken: string | null = null;
let _csrfTokenPromise: Promise<string | null> | null = null;
let _csrfGeneration = 0;

const CSRF_API_PATH = "/api/v1/auth/csrf";

async function fetchCsrfToken(): Promise<string | null> {
  try {
    const res = await fetch(CSRF_API_PATH, {
      credentials: "include",
      cache: "no-store",
    });

    if (!res.ok) return null;

    const body: { token?: string | null } = await res.json();
    return body.token ?? null;
  } catch {
    return null;
  }
}

async function ensureCsrfToken(): Promise<string | null> {
  if (_csrfToken) return _csrfToken;
  if (_csrfTokenPromise) return _csrfTokenPromise;

  const generation = _csrfGeneration;

  const promise = fetchCsrfToken()
    .then((token) => {
      if (generation !== _csrfGeneration) {
        return null;
      }

      _csrfToken = token;
      return token;
    })
    .finally(() => {
      if (_csrfTokenPromise === promise) {
        _csrfTokenPromise = null;
      }
    });

  _csrfTokenPromise = promise;
  return promise;
}

export function resetCsrfToken(): void {
  _csrfGeneration += 1;
  _csrfToken = null;
  _csrfTokenPromise = null;
}

async function resetCsrfAfter<T>(operation: Promise<T>): Promise<T> {
  const result = await operation;
  resetCsrfToken();
  return result;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable: boolean
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type RequestRetryCallback = (attempt: number) => void;

export interface ApiRequestOptions extends RequestInit {
  idempotencyKey?: string;
  maxAttempts?: number;
  onRetry?: RequestRetryCallback;
}

export type SignupStep = "business" | "channels" | "brand" | "review";

export interface SignupBusinessDraft {
  name: string;
  category: Category;
  country: string;
  city: string;
  description?: string;
  primary_product: string;
  target_audience: string;
  website_url?: string;
}

export interface SignupChannelsDraft {
  preferred_platforms: Platform[];
  primary_objective: Objective;
}

export interface SignupBrandDraft {
  voice_tones: Tone[];
  value_proposition: string;
  preferred_words: string[];
  forbidden_words: string[];
  primary_color?: string;
  secondary_color?: string;
  content_locale: "es" | "en" | "pt";
}

export interface SignupProgress {
  signup: {
    status: "pending" | "completed";
    current_step: SignupStep | "completed";
    expires_at: string;
    updated_at: string | null;
    version: number;
    draft: {
      business?: SignupBusinessDraft;
      channels?: SignupChannelsDraft;
      brand?: SignupBrandDraft;
      review?: { confirmed: boolean };
    };
  };
}

export type SignupDraftPayload =
  | { step: "business"; business: SignupBusinessDraft }
  | { step: "channels"; channels: SignupChannelsDraft }
  | { step: "brand"; brand: SignupBrandDraft }
  | { step: "review"; review: { confirmed: boolean } };

export interface GoogleSignInStatus {
  configured: boolean;
}

export interface GoogleAuthorizationStart {
  authorization_url: string;
}

export type InterfaceLocale = "es" | "en" | "pt";

export interface AccountUser {
  id: string;
  name: string;
  email: string;
  interface_locale: InterfaceLocale;
  /** Word the backend accepts as confirmation, in the user's own locale. */
  deletion_confirmation_phrase: string;
}

/**
 * One usage group. A null cost is unknown, never zero: the counters say how
 * many generations in the group actually reported one.
 */
export interface UsageItem {
  capability: string;
  quality_level: string;
  generations: number;
  total_tokens: number | null;
  reported_cost: string | null;
  known_cost_count: number;
  unknown_cost_count: number;
  currency: string | null;
}

export type DeletionStatus = "pending" | "processing" | "completed" | "failed";

export interface BetaPolicies {
  privacy: { version: string; path: string; retention_days: number };
  terms: { version: string; path: string };
  support: { email: string; path: string };
  email_verification: "disabled" | "optional" | "required";
  closed_beta: boolean;
}

const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
const DEFAULT_MAX_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 250;
const MAX_RETRY_AFTER_MS = 30_000;

export function createIdempotencyKey(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  return `hitrendy-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

function retryDelayMs(attempt: number, retryAfter: string | null): number {
  if (retryAfter) {
    const seconds = Number(retryAfter);

    if (Number.isFinite(seconds)) {
      return Math.min(Math.max(seconds * 1000, 0), MAX_RETRY_AFTER_MS);
    }

    const date = Date.parse(retryAfter);

    if (!Number.isNaN(date)) {
      return Math.min(Math.max(date - Date.now(), 0), MAX_RETRY_AFTER_MS);
    }
  }

  return RETRY_BASE_DELAY_MS * 2 ** (attempt - 1);
}

function waitForRetry(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  }

  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, delayMs);

    function onAbort() {
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    }

    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function isRetryableError(error: ApiError): boolean {
  return RETRYABLE_STATUSES.has(error.status) || error.retryable;
}

const CSRF_SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

async function request<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  if (isDemoModeEnabled()) {
    return demoRequest<T>(path, options);
  }

  const maxAttempts = Math.max(1, options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);

  const {
    idempotencyKey,
    onRetry,
    maxAttempts: _maxAttempts,
    ...fetchOptions
  } = options;

  const headers = new Headers(fetchOptions.headers);
  headers.set("ngrok-skip-browser-warning", "true");

  if (typeof fetchOptions.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (idempotencyKey) {
    headers.set("Idempotency-Key", idempotencyKey);
  }

  const method = (fetchOptions.method || "GET").toUpperCase();
  const requiresCsrf = !CSRF_SAFE_METHODS.has(method);

  let attempt = 1;
  let csrfRetryAvailable = true;

  while (attempt <= maxAttempts) {
    /*
     * Build a fresh Headers instance for every fetch attempt.
     * This prevents later CSRF refreshes from mutating the headers
     * associated with an earlier request.
     */
    const attemptHeaders = new Headers(headers);

    if (requiresCsrf) {
      attemptHeaders.delete("X-CSRF-Token");

      const token = await ensureCsrfToken();

      if (token) {
        attemptHeaders.set("X-CSRF-Token", token);
      }
    }

    try {
      const res = await fetch(path, {
        ...fetchOptions,
        headers: attemptHeaders,
        credentials: "include",
      });

      if (!res.ok) {
        let body: {
          error?: {
            code?: string;
            message?: string;
            retryable?: boolean;
          };
        } = {};

        try {
          body = await res.json();
        } catch {
          // The response may not contain JSON.
        }

        const error = new ApiError(
          res.status,
          body.error?.code || "UNKNOWN",
          body.error?.message || "Error de conexión",
          RETRYABLE_STATUSES.has(res.status) || (body.error?.retryable ?? false)
        );

        /*
         * A CSRF refresh gets one dedicated retry and does not consume
         * maxAttempts because the backend rejected the request before
         * executing the protected operation.
         */
        if (error.code.startsWith("CSRF_TOKEN_") && csrfRetryAvailable) {
          csrfRetryAvailable = false;
          resetCsrfToken();
          onRetry?.(attempt + 1);
          continue;
        }

        if (
          !idempotencyKey ||
          !isRetryableError(error) ||
          attempt >= maxAttempts
        ) {
          throw error;
        }

        attempt += 1;
        onRetry?.(attempt);

        await waitForRetry(
          retryDelayMs(attempt - 1, res.headers.get("Retry-After")),
          fetchOptions.signal ?? undefined
        );

        continue;
      }

      if (res.status === 204) {
        return undefined as T;
      }

      return res.json();
    } catch (reason) {
      if (isAbortError(reason)) {
        throw reason;
      }

      if (reason instanceof ApiError) {
        throw reason;
      }

      const error = new ApiError(0, "NETWORK_ERROR", "Error de conexión", true);

      if (
        !idempotencyKey ||
        !isRetryableError(error) ||
        attempt >= maxAttempts
      ) {
        throw error;
      }

      attempt += 1;
      onRetry?.(attempt);

      await waitForRetry(
        retryDelayMs(attempt - 1, null),
        fetchOptions.signal ?? undefined
      );
    }
  }

  throw new ApiError(0, "REQUEST_FAILED", "Error de conexión", true);
}

async function requestForm<T>(path: string, body: FormData): Promise<T> {
  if (isDemoModeEnabled()) {
    return demoRequest<T>(path, { method: "POST", body });
  }

  let token = await ensureCsrfToken();
  const headers: Record<string, string> = {
    "ngrok-skip-browser-warning": "true",
  };
  if (token) {
    headers["X-CSRF-Token"] = token;
  }

  let res = await fetch(path, {
    method: "POST",
    headers,
    body,
    credentials: "include",
  });

  if (!res.ok) {
    let payload = await res.json().catch(() => ({}));
    const code = payload.error?.code || "UNKNOWN";

    if (code.startsWith("CSRF_TOKEN_")) {
      resetCsrfToken();
      token = await ensureCsrfToken();
      const retryHeaders: Record<string, string> = {
        "ngrok-skip-browser-warning": "true",
      };
      if (token) {
        retryHeaders["X-CSRF-Token"] = token;
      }
      res = await fetch(path, {
        method: "POST",
        headers: retryHeaders,
        body,
        credentials: "include",
      });
      if (res.ok) {
        return res.json();
      }
      payload = await res.json().catch(() => ({}));
    }

    throw new ApiError(
      res.status,
      payload.error?.code || "UNKNOWN",
      payload.error?.message || "Error de conexión",
      payload.error?.retryable ?? false
    );
  }

  return res.json();
}

async function demoRequest<T>(path: string, options: RequestInit): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const url = new URL(path, "http://localhost");
  const pathname = url.pathname;

  if (pathname === "/api/v1/auth/me") {
    return cloneDemo(demoData.auth) as T;
  }

  if (
    pathname === "/api/v1/auth/login" ||
    pathname === "/api/v1/auth/register"
  ) {
    return cloneDemo(demoData.auth) as T;
  }

  if (pathname === "/api/v1/auth/password-reset/request" && method === "POST") {
    const data = parseJsonBody(options.body);
    const email = typeof data.email === "string" ? data.email : "";
    const demoToken = "demo-reset-token-123";
    return {
      message: "Si existe una cuenta con este correo, recibirás instrucciones para recuperar el acceso.",
      dev_reset_url: `/reset-password?token=${demoToken}`,
    } as T;
  }

  if (pathname === "/api/v1/auth/password-reset/confirm" && method === "POST") {
    return { status: "reset" } as T;
  }

  if (pathname === "/api/v1/auth/logout") {
    return { ok: true } as T;
  }

  if (pathname === "/api/v1/auth/usage" && method === "GET") {
    return { period_days: 30, items: [] } as T;
  }

  if (pathname === "/api/v1/auth/account" && method === "PATCH") {
    const data = parseJsonBody(options.body);
    return {
      user: {
        ...cloneDemo(demoData.auth.user),
        ...(typeof data.name === "string" ? { name: data.name } : {}),
        ...(data.interface_locale === "es" ||
        data.interface_locale === "en" ||
        data.interface_locale === "pt"
          ? { interface_locale: data.interface_locale }
          : {}),
      },
    } as T;
  }

  if (pathname === "/api/v1/capabilities" && method === "GET") {
    return {
      advisor: { status: "available", tier: "free", quality_levels: ["fast"] },
      copywriter: {
        status: "available",
        tier: "free",
        quality_levels: ["fast"],
      },
      vision_review: {
        status: "available",
        tier: "free",
        quality_levels: ["fast"],
      },
      image_generation: {
        status: "disabled",
        tier: "paid",
        quality_levels: [],
      },
      video_generation: {
        status: "disabled",
        tier: "paid",
        quality_levels: [],
      },
      trend_analysis: { status: "disabled", tier: "free", quality_levels: [] },
    } as T;
  }

  if (pathname === "/api/v1/trends/home" && method === "GET") {
    return {
      status: "disabled",
      refresh_scope: { region: "HN", category: null },
      updated_at: null,
      refresh_allowed: false,
      next_refresh_at: null,
      sources: {
        total: 0,
        available: 0,
        degraded: 0,
        quota_exhausted: 0,
        unavailable: 0,
        unconfigured: 0,
        disabled: 0,
      },
      items: [],
    } as T;
  }

  if (pathname === "/api/v1/trends/sources" && method === "GET") {
    return { sources: [] } as T;
  }

  if (pathname === "/api/v1/social/connections" && method === "GET") {
    return {
      enabled: true,
      providers: [
        {
          name: "instagram",
          status: "unconfigured",
          reason_code: "not_configured",
        },
        {
          name: "tiktok",
          status: "unconfigured",
          reason_code: "not_configured",
        },
        { name: "x", status: "unconfigured", reason_code: "not_configured" },
        { name: "demo", status: "available", reason_code: null },
      ],
      connections: [],
    } as T;
  }

  if (pathname === "/api/v1/social/demo/authorize" && method === "POST") {
    return {
      provider: "demo",
      authorization_url: "/settings?social=connected&provider=demo",
    } as T;
  }

  /*
   * Demo mode has no provider and no budget of its own, so it answers with the
   * documented fallback: a usable visual brief and a capability that is
   * honestly reported as disabled. It never fabricates a generated image.
   */
  if (pathname === "/api/v1/images/brief" && method === "POST") {
    return {
      brief: {
        subject: "Producto principal del negocio en primer plano",
        setting: "Local del negocio con luz natural",
        style: "Fotografía realista",
        palette: "Colores de la marca",
        mood: "Cercano y confiable",
        avoid: "Texto superpuesto, logotipos de terceros",
      },
      aspect_ratios: ["1:1", "4:5", "9:16"],
      capability: {
        status: "disabled",
        tier: "paid",
        message: null,
        fallback: "visual_brief",
      },
      budget: {
        remaining: 0,
        total: 0,
        next_reset_at: new Date().toISOString(),
      },
    } as T;
  }

  if (pathname === "/api/v1/images/jobs" && method === "GET") {
    // Demo mode never enqueues a job, so a reload has nothing to recover.
    return { job: null } as T;
  }

  if (pathname === "/api/v1/images/preflight" && method === "POST") {
    const data = parseJsonBody(options.body);

    return {
      allowed: false,
      aspect_ratio: data.aspect_ratio || "4:5",
      brief: data.brief || {},
      prompt_preview: "",
      negative_prompt_preview: null,
      reference_asset_id: null,
      budget: {
        remaining: 0,
        total: 0,
        next_reset_at: new Date().toISOString(),
      },
      reason_code: "disabled",
      message: null,
      approval_token: null,
      approval_expires_at: null,
      capability: {
        status: "disabled",
        tier: "paid",
        message: null,
        fallback: "visual_brief",
      },
    } as T;
  }

  /*
   * Demo mode has no video service and no budget of its own, so it returns a
   * useful storyboard fallback and reports video generation as disabled. It
   * never fabricates a video or pretends to enqueue a paid job.
   */
  if (pathname === "/api/v1/videos/storyboard" && method === "POST") {
    const data = parseJsonBody(options.body);
    const requestedDuration = data.duration_seconds;
    if (
      requestedDuration !== undefined &&
      requestedDuration !== 5 &&
      requestedDuration !== 10
    ) {
      throw new ApiError(
        422,
        "duration_not_allowed",
        "Elige una duración permitida: 5 o 10 segundos.",
        false
      );
    }
    const duration = requestedDuration === 10 ? 10 : 5;
    const storyboard = {
      hook: "Muestra el producto principal y por qué hace especial tu negocio",
      duration_seconds: duration,
      aspect_ratio: "9:16",
      voiceover:
        "Presenta el producto con una idea clara y cierra invitando a conocerlo.",
      music_direction:
        "Ritmo cálido, optimista y discreto para dejar respirar la voz.",
      shots: [
        {
          order: 1,
          duration_seconds: duration === 10 ? 5 : 2,
          visual:
            "Producto principal en primer plano, con luz natural y detalles del negocio.",
          camera: "Acercamiento lento desde una vista vertical estable.",
          on_screen_text: "Hecho para tu momento",
          voiceover: "Descubre una forma sencilla de disfrutar lo que hacemos.",
          transition: "Corte suave",
        },
        {
          order: 2,
          duration_seconds: duration === 10 ? 5 : 3,
          visual:
            "Una persona usa o disfruta el producto en un ambiente cercano.",
          camera: "Plano medio vertical con movimiento lateral sutil.",
          on_screen_text: "Conoce más hoy",
          voiceover: "Escríbenos y encuentra la opción ideal para ti.",
          transition: "Fundido breve",
        },
      ],
    };

    return {
      storyboard,
      prompt_preview:
        "Video vertical 9:16, cálido y cercano, con el producto principal como protagonista.",
      negative_prompt_preview:
        "Sin texto ilegible, marcas de terceros, parpadeos ni movimientos bruscos.",
      allowed_durations: [5, 10],
      aspect_ratio: "9:16",
      budget: {
        remaining: 0,
        total: 0,
        next_reset_at: new Date().toISOString(),
      },
      capability: {
        status: "disabled",
        tier: "paid",
        message: null,
        fallback: "storyboard",
      },
    } as T;
  }

  if (pathname === "/api/v1/videos/preflight" && method === "POST") {
    const data = parseJsonBody(options.body);
    const requestedDuration = data.duration_seconds;
    if (
      requestedDuration !== undefined &&
      requestedDuration !== 5 &&
      requestedDuration !== 10
    ) {
      throw new ApiError(
        422,
        "duration_not_allowed",
        "Elige una duración permitida: 5 o 10 segundos.",
        false
      );
    }

    return {
      allowed: false,
      aspect_ratio: "9:16",
      duration_seconds: requestedDuration === 10 ? 10 : 5,
      storyboard: data.storyboard || {},
      prompt_preview: typeof data.prompt === "string" ? data.prompt : "",
      negative_prompt_preview:
        typeof data.negative_prompt === "string" ? data.negative_prompt : "",
      source_asset_id:
        typeof data.source_asset_id === "string" ? data.source_asset_id : null,
      estimated_units: 0,
      budget: {
        remaining: 0,
        total: 0,
        next_reset_at: new Date().toISOString(),
      },
      reason_code: "disabled",
      message: null,
      approval_token: null,
      approval_expires_at: null,
      capability: {
        status: "disabled",
        tier: "paid",
        message: null,
        fallback: "storyboard",
      },
    } as T;
  }

  if (pathname === "/api/v1/videos/jobs" && method === "GET") {
    // Demo mode never enqueues a job, so a reload has nothing to recover.
    return { job: null } as T;
  }

  const demoProjects = readDemoProjects(cloneDemo(demoData.projects));

  if (pathname === "/api/v1/projects" && method === "GET") {
    return cloneDemo(demoProjects) as T;
  }

  if (pathname === "/api/v1/projects" && method === "POST") {
    const data = parseJsonBody(options.body);
    const template = demoData.templates.find(
      (item) => item.id === data.template_id
    );
    const now = new Date().toISOString();

    const project = {
      id: `project-demo-${Date.now()}`,
      name:
        typeof data.name === "string"
          ? data.name
          : template?.title || "Proyecto sin título",
      business_id:
        typeof data.business_id === "string"
          ? data.business_id
          : "business-demo-1",
      platform: template?.platforms[0] || "instagram",
      status: "active" as const,
      updated_at: now,
      created_at: now,
      artifact_id: `artifact-demo-${Date.now()}`,
      source_template_id: template?.id || null,
      artifact_snapshot: {
        ...cloneDemo(demoData.artifacts.demoArtifact),
        hook: template?.title || demoData.artifacts.demoArtifact.hook,
        format_recommendation:
          template?.formats[0] ||
          demoData.artifacts.demoArtifact.format_recommendation,
        assumptions: template
          ? [`Proyecto iniciado desde la plantilla ${template.title}.`]
          : demoData.artifacts.demoArtifact.assumptions,
      },
    };

    demoProjects.unshift(project);
    saveDemoProjects(demoProjects);

    return cloneDemo(project) as T;
  }

  const projectMatch = pathname.match(
    /^\/api\/v1\/projects\/([^/]+)(?:\/(.+))?$/
  );

  if (projectMatch) {
    const [, projectId, action] = projectMatch;
    const project = demoProjects.find((item) => item.id === projectId);

    if (!project) {
      throw new ApiError(404, "NOT_FOUND", "Proyecto no encontrado.", false);
    }

    if (!action && method === "GET") {
      return cloneDemo(project) as T;
    }

    if (!action && method === "PATCH") {
      Object.assign(project, parseJsonBody(options.body), {
        updated_at: new Date().toISOString(),
      });
      saveDemoProjects(demoProjects);
      return cloneDemo(project) as T;
    }

    if (action === "versions" && method === "GET") {
      return [
        {
          id: `${project.id}-version-1`,
          version_number: 1,
          user_edited: false,
          created_at: project.updated_at,
        },
      ] as T;
    }

    if (action === "artifact-version" && method === "PUT") {
      project.artifact_snapshot = parseJsonBody(
        options.body
      ) as typeof project.artifact_snapshot;
      project.updated_at = new Date().toISOString();
      saveDemoProjects(demoProjects);

      return { version_number: 2 } as T;
    }
  }

  if (pathname === "/api/v1/templates" && method === "GET") {
    return cloneDemo(demoData.templates) as T;
  }

  if (pathname === "/api/v1/templates/recommendations") {
    return cloneDemo(demoData.templates) as T;
  }

  if (pathname === "/api/v1/businesses" && method === "GET") {
    return cloneDemo(demoData.businesses) as T;
  }

  if (pathname === "/api/v1/businesses" && method === "POST") {
    return { id: "business-demo-created" } as T;
  }

  if (
    /^\/api\/v1\/businesses\/[^/]+\/brand-profile$/.test(pathname) &&
    method === "GET"
  ) {
    return cloneDemo(demoData.brandProfile) as T;
  }

  if (
    /^\/api\/v1\/businesses\/[^/]+\/brand-profile$/.test(pathname) &&
    method === "PUT"
  ) {
    return cloneDemo(demoData.brandProfile) as T;
  }

  if (/^\/api\/v1\/businesses\/[^/]+$/.test(pathname) && method === "PATCH") {
    return cloneDemo(demoData.businesses[0]) as T;
  }

  if (pathname === "/api/v1/conversations" && method === "GET") {
    return cloneDemo(demoData.conversations) as T;
  }

  if (pathname === "/api/v1/conversations" && method === "POST") {
    return { id: "conversation-demo-created" } as T;
  }

  if (pathname.startsWith("/api/v1/conversations/") && method === "GET") {
    return {
      messages: [
        {
          id: "message-demo-1",
          role: "user",
          content: "Necesito un post para una promo de fin de semana.",
          metadata: null,
        },
        {
          id: "message-demo-2",
          role: "assistant",
          content: "Aquí tienes una propuesta lista para editar.",
          artifact: demoData.artifacts.demoArtifact,
          artifact_id: "artifact-demo-1",
        },
      ],
    } as T;
  }

  if (pathname.startsWith("/api/v1/conversations/") && method === "POST") {
    return {
      type: "artifact",
      assistant_message: {
        id: "message-demo-3",
        content: "Aquí tienes tu borrador de ejemplo.",
      },
      artifact: demoData.artifacts.demoArtifact,
      artifact_id: "artifact-demo-1",
    } as T;
  }

  if (pathname === "/api/v1/assets" && method === "GET") {
    return [] as T;
  }

  if (pathname === "/api/v1/assets/uploads" && method === "POST") {
    return {
      upload_id: "upload-demo",
      upload_url: "/api/v1/assets/uploads",
    } as T;
  }

  return {} as T;
}

function parseJsonBody(
  body: BodyInit | null | undefined
): Record<string, unknown> {
  if (typeof body !== "string") {
    return {};
  }

  try {
    return JSON.parse(body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

const BASE = "/api/v1";

export const api = {
  operations: {
    policies(): Promise<BetaPolicies> {
      return request<BetaPolicies>(`${BASE}/policies`);
    },
    feedback(
      data: {
        category: "bug" | "idea" | "support" | "other";
        message: string;
        rating?: number;
      },
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ) {
      return request<{ id: string; status: string }>(`${BASE}/feedback`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey,
        body: JSON.stringify(data),
      });
    },
    abuseReport(data: {
      category: "unsafe_content" | "spam" | "harassment" | "other";
      message: string;
      resource_id?: string;
    }) {
      return request<{ id: string; status: string }>(`${BASE}/abuse/reports`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },

  capabilities: {
    get(): Promise<PublicCapabilities> {
      return request<PublicCapabilities>(`${BASE}/capabilities`);
    },
  },

  social: {
    connections(): Promise<SocialConnectionsResponse> {
      return request<SocialConnectionsResponse>(`${BASE}/social/connections`);
    },

    authorize(
      provider: string,
      returnPath?: string
    ): Promise<SocialAuthorizeResult> {
      return request<SocialAuthorizeResult>(
        `${BASE}/social/${encodeURIComponent(provider)}/authorize`,
        {
          method: "POST",
          body: JSON.stringify(
            returnPath === undefined ? {} : { return_path: returnPath }
          ),
        }
      );
    },

    check(connectionId: string): Promise<SocialConnection> {
      return request<{ connection: SocialConnection }>(
        `${BASE}/social/connections/${encodeURIComponent(connectionId)}/check`,
        { method: "POST" }
      ).then((result) => result.connection);
    },

    disconnect(connectionId: string): Promise<SocialConnection> {
      return request<{ connection: SocialConnection }>(
        `${BASE}/social/connections/${encodeURIComponent(connectionId)}`,
        { method: "DELETE" }
      ).then((result) => result.connection);
    },
  },

  trends: {
    home(): Promise<TrendHome> {
      return request<TrendHome>(`${BASE}/trends/home`);
    },
    sources(): Promise<TrendSource[]> {
      return request<{ sources: TrendSource[] }>(`${BASE}/trends/sources`).then(
        (result) => result.sources
      );
    },
    detail(id: string): Promise<TrendDetail> {
      return request<TrendDetail>(`${BASE}/trends/${encodeURIComponent(id)}`);
    },
    /**
     * Collects exactly the Home `refresh_scope`. The aggregated Home cards may
     * belong to other scopes and are never the target of this call.
     */
    refresh(
      scope: TrendRefreshScope,
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ): Promise<TrendRefreshResult> {
      return request<TrendRefreshResult>(`${BASE}/trends/refresh`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey || createIdempotencyKey(),
        body: JSON.stringify({
          region: scope.region,
          category: scope.category,
        }),
      });
    },
  },

  /**
   * Image generation, in the only order the server accepts: draft the brief,
   * preflight it, confirm it, then poll the durable job.
   *
   * The model, the provider and the spending limits are never sent from here:
   * the client chooses the brief, one of three formats, and optionally one
   * asset the workspace already owns.
   */
  images: {
    /** Free and provider-free. Answers even when generation is unavailable. */
    draftBrief(data: {
      business_id: string;
      publication_text?: string;
      trend_title?: string;
    }): Promise<ImageBriefDraft> {
      return request<ImageBriefDraft>(`${BASE}/images/brief`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** Estimates and authorizes. Spends nothing and calls no provider. */
    preflight(data: {
      brief: VisualBrief;
      aspect_ratio: ImageAspectRatio;
      reference_asset_id?: string | null;
    }): Promise<ImagePreflight> {
      return request<ImagePreflight>(`${BASE}/images/preflight`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /**
     * The only paid step, and the only one that needs an explicit `confirmed`.
     * It runs with a single attempt: the idempotency key already makes a
     * replay safe, and a refused confirmation (no budget, capability down)
     * must surface to the user instead of being retried behind their back.
     */
    createJob(
      data: {
        brief: VisualBrief;
        aspect_ratio: ImageAspectRatio;
        approval_token: string;
        confirmed: true;
        reference_asset_id?: string | null;
        project_id?: string | null;
      },
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ): Promise<ImageJob> {
      return request<ImageJob>(`${BASE}/images/jobs`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey || createIdempotencyKey(),
        maxAttempts: 1,
        body: JSON.stringify(data),
      });
    },

    /** One poll. Mints a fresh short-lived link on every successful read. */
    job(id: string): Promise<ImageJob> {
      return request<ImageJob>(`${BASE}/images/jobs/${encodeURIComponent(id)}`);
    },

    /**
     * The project's most recent job, or `null`.
     *
     * A reloaded page has lost the job id but not the generation, which is
     * durable on the server and may already have been paid for. Asking for it
     * is the only honest way back: generating again to find out would spend a
     * second image.
     */
    async latestJob(projectId: string): Promise<ImageJob | null> {
      const { job } = await request<{ job: ImageJob | null }>(
        `${BASE}/images/jobs?project_id=${encodeURIComponent(projectId)}&latest=true`
      );
      return job ?? null;
    },
  },

  /**
   * Video generation follows the same free-draft, preflight, confirmation and
   * durable polling sequence as images, with a vertical storyboard fallback.
   * The model, the provider and the spending limits are never sent from here.
   */
  videos: {
    /** Free and provider-free. Answers with an editable storyboard when disabled. */
    draftStoryboard(data: {
      business_id: string;
      publication_text?: string;
      trend_title?: string;
      duration_seconds?: number;
    }): Promise<VideoStoryboardDraft> {
      return request<VideoStoryboardDraft>(`${BASE}/videos/storyboard`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** Estimates and authorizes. Spends nothing and calls no provider. */
    preflight(data: {
      storyboard: VideoStoryboard;
      prompt: string;
      negative_prompt?: string | null;
      duration_seconds: number;
      source_asset_id?: string | null;
      project_id?: string | null;
    }): Promise<VideoPreflight> {
      return request<VideoPreflight>(`${BASE}/videos/preflight`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /**
     * The only paid step. A single attempt is deliberate: the idempotency key
     * protects a replay, while an automatic retry could duplicate a charge.
     */
    createJob(
      data: {
        storyboard: VideoStoryboard;
        prompt: string;
        negative_prompt?: string | null;
        duration_seconds: number;
        source_asset_id?: string | null;
        project_id?: string | null;
        confirmed: true;
        approval_token: string;
      },
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ): Promise<VideoJob> {
      return request<VideoJob>(`${BASE}/videos/jobs`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey || createIdempotencyKey(),
        maxAttempts: 1,
        body: JSON.stringify(data),
      });
    },

    /** One poll. A successful read may mint a fresh short-lived video link. */
    job(id: string): Promise<VideoJob> {
      return request<VideoJob>(`${BASE}/videos/jobs/${encodeURIComponent(id)}`);
    },

    /** The project's most recent durable job, or `null`. */
    async latestJob(projectId: string): Promise<VideoJob | null> {
      const { job } = await request<{ job: VideoJob | null }>(
        `${BASE}/videos/jobs?project_id=${encodeURIComponent(projectId)}&latest=true`
      );
      return job ?? null;
    },
  },

  conversations: {
    create(
      data: Record<string, unknown>,
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ) {
      return request<Record<string, unknown>>(`${BASE}/conversations`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey,
        body: JSON.stringify(data),
      });
    },

    list(
      params?: Record<string, string>
    ): Promise<Array<Record<string, unknown>>> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";

      return request(`${BASE}/conversations${qs}`);
    },

    get(id: string) {
      return request<Record<string, unknown>>(`${BASE}/conversations/${id}`);
    },

    update(
      id: string,
      data: {
        title?: string;
        status?: "active" | "archived";
      }
    ) {
      return request<Record<string, unknown>>(`${BASE}/conversations/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    sendMessage(
      conversationId: string,
      text: string,
      // Mirrors the four intents the endpoint accepts. `ask_advisor` is what
      // the weekly plan is asked for, and it was missing here.
      uiIntent?:
        | "create_social_post"
        | "create_short_video_script"
        | "analyze_visual"
        | "ask_advisor",
      attachmentIds: string[] = [],
      options: Pick<
        ApiRequestOptions,
        "idempotencyKey" | "signal" | "onRetry" | "maxAttempts"
      > = {},
      generation?: {
        platform?: string;
        objective?: string;
        qualityLevel?: "fast" | "balanced" | "quality";
        locale?: "es" | "en" | "pt";
      }
    ) {
      return request<Record<string, unknown>>(
        `${BASE}/conversations/${conversationId}/messages`,
        {
          method: "POST",
          ...options,
          body: JSON.stringify({
            text,
            ...(uiIntent ? { ui_intent: uiIntent } : {}),
            ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
            ...(generation?.platform ? { platform: generation.platform } : {}),
            ...(generation?.objective
              ? { objective: generation.objective }
              : {}),
            ...(generation?.qualityLevel
              ? { quality_level: generation.qualityLevel }
              : {}),
            ...(generation?.locale ? { locale: generation.locale } : {}),
          }),
        }
      );
    },
  },

  artifacts: {
    createVariation(
      conversationId: string,
      artifactId: string,
      kind: string,
      options: Pick<
        ApiRequestOptions,
        "idempotencyKey" | "signal" | "onRetry"
      > = {}
    ) {
      return request<Record<string, unknown>>(
        `${BASE}/conversations/${conversationId}/artifacts/${artifactId}/variations`,
        {
          method: "POST",
          ...options,
          idempotencyKey: options.idempotencyKey || createIdempotencyKey(),
          body: JSON.stringify({ kind }),
        }
      );
    },

    feedback(artifactId: string, rating: "useful" | "not_useful") {
      return request<Record<string, unknown>>(
        `${BASE}/conversations/artifacts/${artifactId}/feedback`,
        {
          method: "POST",
          body: JSON.stringify({ rating }),
        }
      );
    },

    event(artifactId: string, eventType: "copied" | "saved") {
      return request<Record<string, unknown>>(
        `${BASE}/conversations/artifacts/${artifactId}/events`,
        {
          method: "POST",
          body: JSON.stringify({
            event_type: eventType,
          }),
        }
      );
    },
  },

  projects: {
    create(
      data: Record<string, unknown>,
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ) {
      return request<Record<string, unknown>>(`${BASE}/projects`, {
        method: "POST",
        idempotencyKey: options.idempotencyKey,
        body: JSON.stringify(data),
      });
    },

    list(
      params?: Record<string, string>
    ): Promise<Array<Record<string, unknown>>> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";

      return request(`${BASE}/projects${qs}`);
    },

    get(id: string) {
      return request<Record<string, unknown>>(`${BASE}/projects/${id}`);
    },

    update(id: string, data: Record<string, unknown>) {
      return request<Record<string, unknown>>(`${BASE}/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    duplicate(
      id: string,
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ) {
      return request<Record<string, unknown>>(
        `${BASE}/projects/${id}/duplicate`,
        {
          method: "POST",
          idempotencyKey: options.idempotencyKey || createIdempotencyKey(),
        }
      );
    },

    export(id: string) {
      return request<Record<string, unknown>>(`${BASE}/projects/${id}/export`);
    },

    versions(id: string) {
      return request<Array<Record<string, unknown>>>(
        `${BASE}/projects/${id}/versions`
      );
    },

    restoreVersion(projectId: string, versionId: string) {
      return request<Record<string, unknown>>(
        `${BASE}/projects/${projectId}/versions/${versionId}/restore`,
        {
          method: "POST",
        }
      );
    },

    updateArtifactVersion(projectId: string, data: Record<string, unknown>) {
      return request<Record<string, unknown>>(
        `${BASE}/projects/${projectId}/artifact-version`,
        {
          method: "PUT",
          body: JSON.stringify(data),
        }
      );
    },
    startCreationFlow(
      businessId: string,
      options: Pick<ApiRequestOptions, "idempotencyKey"> = {}
    ) {
      return request<{ id: string; flow_started_at: string }>(
        `${BASE}/projects/flow-events`,
        {
          method: "POST",
          idempotencyKey: options.idempotencyKey,
          body: JSON.stringify({ business_id: businessId }),
        }
      );
    },
    completeCreationFlow(
      eventId: string,
      status: "generation_completed" | "completed" | "failed"
    ) {
      return request<Record<string, unknown>>(
        `${BASE}/projects/flow-events/${eventId}`,
        { method: "PATCH", body: JSON.stringify({ status }) }
      );
    },
  },

  assets: {
    list(): Promise<Array<Record<string, unknown>>> {
      return request(`${BASE}/assets`);
    },

    get(id: string) {
      return request<Record<string, unknown>>(`${BASE}/assets/${id}`);
    },

    contentUrl(id: string) {
      return `${BASE}/assets/${id}/content`;
    },

    async upload(file: File): Promise<Record<string, unknown>> {
      const init = await request<{
        upload_id: string;
        upload_url: string;
      }>(`${BASE}/assets/uploads`, {
        method: "POST",
      });

      const form = new FormData();
      form.append("file", file);

      return requestForm(init.upload_url, form);
    },

    analyze(assetId: string) {
      return request<Record<string, unknown>>(
        `${BASE}/assets/${assetId}/analyses`,
        {
          method: "POST",
        }
      );
    },
  },

  templates: {
    list(
      params?: Record<string, string>
    ): Promise<Array<Record<string, unknown>>> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";

      return request(`${BASE}/templates${qs}`);
    },

    get(id: string) {
      return request<Record<string, unknown>>(`${BASE}/templates/${id}`);
    },

    recommend(data: {
      platform: string;
      objective: string;
      category?: string;
      limit?: number;
    }) {
      return request<Array<Record<string, unknown>>>(
        `${BASE}/templates/recommendations`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      );
    },
  },

  businesses: {
    create(data: Record<string, unknown>) {
      return request<Record<string, unknown>>(`${BASE}/businesses`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    list(): Promise<Array<Record<string, unknown>>> {
      return request(`${BASE}/businesses`);
    },

    get(id: string) {
      return request<Record<string, unknown>>(`${BASE}/businesses/${id}`);
    },

    update(id: string, data: Record<string, unknown>) {
      return request<Record<string, unknown>>(`${BASE}/businesses/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    brandProfile: {
      upsert(businessId: string, data: Record<string, unknown>) {
        return request<Record<string, unknown>>(
          `${BASE}/businesses/${businessId}/brand-profile`,
          {
            method: "PUT",
            body: JSON.stringify(data),
          }
        );
      },

      get(businessId: string) {
        return request<Record<string, unknown>>(
          `${BASE}/businesses/${businessId}/brand-profile`
        );
      },
    },
  },

  auth: {
    register(data: {
      email: string;
      name: string;
      password: string;
      workspace_name: string;
      invite_code?: string;
    }) {
      return resetCsrfAfter(
        request(`${BASE}/auth/register`, {
          method: "POST",
          body: JSON.stringify(data),
        })
      );
    },

    login(data: { email: string; password: string }) {
      return resetCsrfAfter(
        request(`${BASE}/auth/login`, {
          method: "POST",
          body: JSON.stringify(data),
        })
      );
    },

    passwordReset: {
      request(email: string) {
        return resetCsrfAfter(
          request<{ message: string; dev_reset_url?: string }>(`${BASE}/auth/password-reset/request`, {
            method: "POST",
            body: JSON.stringify({ email }),
          })
        );
      },
      confirm(token: string, password: string) {
        return resetCsrfAfter(
          request<{ status: "reset" }>(`${BASE}/auth/password-reset/confirm`, {
            method: "POST",
            body: JSON.stringify({ token, password }),
          })
        );
      },
    },

    google: {
      status() {
        return request<GoogleSignInStatus>(`${BASE}/auth/google/status`);
      },

      start() {
        return request<GoogleAuthorizationStart>(`${BASE}/auth/google/start`);
      },
    },

    signup: {
      start(data: {
        email: string;
        name: string;
        password: string;
        interface_locale: "es" | "en" | "pt";
        invite_code?: string;
      }) {
        return resetCsrfAfter(
          request<SignupProgress>(`${BASE}/auth/signup/start`, {
            method: "POST",
            body: JSON.stringify(data),
          })
        );
      },

      get() {
        return request<SignupProgress>(`${BASE}/auth/signup`);
      },

      saveDraft(payload: SignupDraftPayload, expectedVersion: number) {
        return request<SignupProgress>(`${BASE}/auth/signup`, {
          method: "PATCH",
          body: JSON.stringify({
            ...payload,
            expected_version: expectedVersion,
          }),
        });
      },

      cancel() {
        return resetCsrfAfter(
          request<void>(`${BASE}/auth/signup`, {
            method: "DELETE",
          })
        );
      },

      complete(
        options: Pick<
          ApiRequestOptions,
          "idempotencyKey" | "signal" | "onRetry"
        > = {}
      ) {
        return resetCsrfAfter(
          request<Record<string, unknown>>(`${BASE}/auth/signup/complete`, {
            method: "POST",
            ...options,
            idempotencyKey: options.idempotencyKey,
          })
        );
      },
    },

    logout() {
      return resetCsrfAfter(
        request<void>(`${BASE}/auth/logout`, {
          method: "POST",
        })
      );
    },

    me() {
      return request<{
        user: AccountUser;
        workspaces: { id: string; role: string }[];
      }>(`${BASE}/auth/me`);
    },
    updateAccount(data: { name: string; interface_locale: InterfaceLocale }) {
      return request<{ user: AccountUser }>(`${BASE}/auth/account`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    usage() {
      return request<{ period_days: number; items: UsageItem[] }>(
        `${BASE}/auth/usage`
      );
    },
    /**
     * The status token is minted by the caller, so a retry of this request
     * resolves to the same purge job. The response never echoes it back.
     */
    deleteAccount(confirmation: string, statusToken: string) {
      return resetCsrfAfter(
        request<{ status: DeletionStatus }>(`${BASE}/auth/account/delete`, {
          method: "POST",
          body: JSON.stringify({ confirmation, status_token: statusToken }),
        })
      );
    },
    deletionStatus(statusToken: string) {
      return request<{ status: DeletionStatus }>(
        `${BASE}/auth/account/deletion-status`,
        {
          headers: { "X-Deletion-Status-Token": statusToken },
        }
      );
    },
  },
};
