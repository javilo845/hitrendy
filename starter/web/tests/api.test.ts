import { beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, api, createIdempotencyKey, resetCsrfToken } from "@/lib/api";
import { isDemoModeEnabled } from "@/lib/demo-mode";

vi.mock("@/lib/demo-mode", () => ({
  isDemoModeEnabled: vi.fn(() => false),
  readDemoProjects: vi.fn((projects: unknown) => projects),
  saveDemoProjects: vi.fn(),
}));

type FetchMock = ReturnType<typeof vi.fn>;

const fetchMock = vi.fn() as FetchMock;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

function errorResponse(
  code: string,
  status = 403,
  retryable = false,
  headers?: HeadersInit
): Response {
  return jsonResponse(
    {
      error: {
        code,
        message: code,
        retryable,
      },
    },
    { status, headers }
  );
}

function requestInitAt(index: number): RequestInit {
  const call = fetchMock.mock.calls[index];
  expect(call).toBeDefined();
  return (call?.[1] ?? {}) as RequestInit;
}

function requestHeadersAt(index: number): Headers {
  return new Headers(requestInitAt(index).headers);
}

beforeEach(() => {
  resetCsrfToken();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("API client", () => {
  test("uses the authenticated trends Home and sends manual refresh with CSRF", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "empty", items: [] }))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-trends" }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: "run-1",
          status: "completed",
          refresh_allowed: false,
        })
      );

    // The Home refresh scope is sent verbatim: nothing more, nothing less.
    const refreshScope = { region: "HN", category: "gastronomy" };
    await api.trends.home();
    await api.trends.refresh(refreshScope, {
      idempotencyKey: "trend-refresh-once",
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/trends/home");
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/trends/refresh");
    expect(requestHeadersAt(2).get("X-CSRF-Token")).toBe("csrf-trends");
    expect(requestHeadersAt(2).get("Idempotency-Key")).toBe(
      "trend-refresh-once"
    );
    expect(requestInitAt(2).body).toBe(JSON.stringify(refreshScope));
  });

  test("crea claves de idempotencia no vacías", () => {
    const first = createIdempotencyKey();
    const second = createIdempotencyKey();

    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(first).not.toBe(second);
  });

  test("una petición GET no solicita token CSRF", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.projects.list();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/projects");
  });

  test("obtiene CSRF con credentials include y cache no-store", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.projects.create({ name: "Proyecto" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/auth/csrf");
    expect(requestInitAt(0)).toMatchObject({
      credentials: "include",
      cache: "no-store",
    });
  });

  test("adjunta X-CSRF-Token en mutaciones", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.projects.create({ name: "Proyecto" });

    expect(requestHeadersAt(1).get("X-CSRF-Token")).toBe("csrf-one");
    expect(requestInitAt(1).credentials).toBe("include");
  });

  test("envía la clave estable de idempotencia al guardar un proyecto", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.projects.create(
      { artifact_id: "artifact-1" },
      { idempotencyKey: "save-once" }
    );

    expect(requestHeadersAt(1).get("Idempotency-Key")).toBe("save-once");
  });

  test("mantiene el token CSRF únicamente en memoria", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-memory" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-2" }));

    await api.projects.create({ name: "Uno" });
    await api.projects.create({ name: "Dos" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  test("resetCsrfToken obliga a obtener un token nuevo", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-two" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-2" }));

    await api.projects.create({ name: "Uno" });
    resetCsrfToken();
    await api.projects.create({ name: "Dos" });

    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/auth/csrf");
    expect(requestHeadersAt(3).get("X-CSRF-Token")).toBe("csrf-two");
  });

  test("reintenta una vez un error CSRF aunque maxAttempts sea 1", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-old" }))
      .mockResolvedValueOnce(errorResponse("CSRF_TOKEN_INVALID"))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-new" }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const result = await api.conversations.sendMessage(
      "conversation-1",
      "Hola",
      undefined,
      [],
      { maxAttempts: 1 }
    );

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(requestHeadersAt(1).get("X-CSRF-Token")).toBe("csrf-old");
    expect(requestHeadersAt(3).get("X-CSRF-Token")).toBe("csrf-new");
  });

  test("no entra en bucle ante un segundo error CSRF", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-old" }))
      .mockResolvedValueOnce(errorResponse("CSRF_TOKEN_INVALID"))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-new" }))
      .mockResolvedValueOnce(errorResponse("CSRF_TOKEN_INVALID"));

    await expect(
      api.conversations.sendMessage("conversation-1", "Hola", undefined, [], {
        maxAttempts: 1,
      })
    ).rejects.toMatchObject({
      status: 403,
      code: "CSRF_TOKEN_INVALID",
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  test("elimina el header CSRF anterior antes del refresco", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-stale" }))
      .mockResolvedValueOnce(errorResponse("CSRF_TOKEN_MISMATCH"))
      .mockResolvedValueOnce(jsonResponse({ token: null }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    await api.projects.create({ name: "Proyecto" });

    expect(requestHeadersAt(1).get("X-CSRF-Token")).toBe("csrf-stale");
    expect(requestHeadersAt(3).has("X-CSRF-Token")).toBe(false);
  });

  test("agrega Content-Type JSON cuando el body es texto", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.projects.create({ name: "Proyecto" });

    expect(requestHeadersAt(1).get("Content-Type")).toBe("application/json");
  });

  test("no agrega Content-Type a una petición GET sin body", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.projects.list();

    expect(requestHeadersAt(0).has("Content-Type")).toBe(false);
  });

  test("envía Idempotency-Key y reintenta respuestas retryable", async () => {
    const onRetry = vi.fn();

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(
        errorResponse("TEMPORARY", 503, true, { "Retry-After": "0" })
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const result = await api.conversations.sendMessage(
      "conversation-1",
      "Hola",
      undefined,
      [],
      {
        idempotencyKey: "idem-1",
        maxAttempts: 2,
        onRetry,
      }
    );

    expect(result).toEqual({ ok: true });
    expect(requestHeadersAt(1).get("Idempotency-Key")).toBe("idem-1");
    expect(requestHeadersAt(2).get("Idempotency-Key")).toBe("idem-1");
    expect(onRetry).toHaveBeenCalledWith(2);
  });

  test("no reintenta errores retryable sin clave de idempotencia", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(errorResponse("TEMPORARY", 503, true));

    await expect(
      api.projects.create({ name: "Proyecto" })
    ).rejects.toBeInstanceOf(ApiError);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("devuelve undefined para respuestas 204", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(api.auth.logout()).resolves.toBeUndefined();
  });

  test("login rota el token CSRF después de crear sesión", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-before" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }))
      .mockResolvedValueOnce(jsonResponse({ user: { id: "u1" } }))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-session" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-2" }));

    await api.projects.create({ name: "Antes" });
    await api.auth.login({
      email: "user@example.com",
      password: "secret",
    });
    await api.projects.create({ name: "Después" });

    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/v1/auth/csrf");
    expect(requestHeadersAt(4).get("X-CSRF-Token")).toBe("csrf-session");
  });

  test("signup start rota el token hacia el contexto pending signup", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: null }))
      .mockResolvedValueOnce(
        jsonResponse({
          signup: {
            status: "pending",
            current_step: "business",
            expires_at: "2026-07-29T00:00:00Z",
            updated_at: null,
            version: 1,
            draft: {},
          },
        })
      )
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-signup" }))
      .mockResolvedValueOnce(
        jsonResponse({
          signup: {
            status: "pending",
            current_step: "channels",
            expires_at: "2026-07-29T00:00:00Z",
            updated_at: "2026-07-28T00:00:00Z",
            version: 2,
            draft: {},
          },
        })
      );

    await api.auth.signup.start({
      email: "user@example.com",
      name: "User",
      password: "secret",
      interface_locale: "es",
    });

    await api.auth.signup.saveDraft(
      {
        step: "business",
        business: {
          name: "Negocio",
          category: "other" as never,
          country: "HN",
          city: "Tegucigalpa",
          primary_product: "Servicio",
          target_audience: "Clientes",
        },
      },
      1
    );

    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/auth/csrf");
    expect(requestHeadersAt(3).get("X-CSRF-Token")).toBe("csrf-signup");
  });

  test("signup complete limpia el token pending signup", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-signup" }))
      .mockResolvedValueOnce(jsonResponse({ user_id: "u1" }))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-session" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.auth.signup.complete({
      idempotencyKey: "signup-complete-1",
    });
    await api.projects.create({ name: "Proyecto" });

    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/auth/csrf");
    expect(requestHeadersAt(3).get("X-CSRF-Token")).toBe("csrf-session");
  });

  test("no usa document.cookie para obtener CSRF", async () => {
    const cookieGetter = vi.spyOn(document, "cookie", "get");

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-one" }))
      .mockResolvedValueOnce(jsonResponse({ id: "project-1" }));

    await api.projects.create({ name: "Proyecto" });

    expect(cookieGetter).not.toHaveBeenCalled();
    cookieGetter.mockRestore();
  });

  describe("video generation", () => {
    const storyboard = {
      hook: "Un hook editable",
      duration_seconds: 5,
      aspect_ratio: "9:16" as const,
      voiceover: "Una voz clara",
      music_direction: "Ritmo cálido",
      shots: [
        {
          order: 1,
          duration_seconds: 5,
          visual: "Producto en primer plano",
          camera: "Acercamiento estable",
          on_screen_text: "Conoce más",
          voiceover: "Descubre la idea",
          transition: "Corte suave",
        },
      ],
    };

    const payload = {
      storyboard,
      prompt: "Video vertical 9:16",
      negative_prompt: "Sin texto ilegible",
      duration_seconds: 5,
      source_asset_id: null,
      project_id: "project-1",
      confirmed: true as const,
      approval_token: "approval-video-1",
    };

    test("latestJob desenvuelve el job del envelope del proyecto", async () => {
      const latest = {
        id: "video-job-1",
        status: "queued",
        aspect_ratio: "9:16",
        duration_seconds: 5,
        source_asset_id: null,
        asset_id: null,
        video_url: null,
        video_expires_at: null,
        created_at: "2026-08-02T12:00:00Z",
        completed_at: null,
        safe_error: null,
        safe_error_code: null,
      };
      fetchMock.mockResolvedValueOnce(jsonResponse({ job: latest }));

      await expect(api.videos.latestJob("project/1")).resolves.toEqual(latest);
      expect(fetchMock.mock.calls[0]?.[0]).toBe(
        "/api/v1/videos/jobs?project_id=project%2F1&latest=true"
      );
    });

    test("createJob sends Idempotency-Key and does not retry a paid failure", async () => {
      fetchMock
        .mockResolvedValueOnce(jsonResponse({ token: "csrf-video" }))
        .mockResolvedValueOnce(errorResponse("VIDEO_TEMPORARY", 503, true));

      await expect(
        api.videos.createJob(payload, { idempotencyKey: "video-once" })
      ).rejects.toMatchObject({ code: "VIDEO_TEMPORARY" });

      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(requestHeadersAt(1).get("Idempotency-Key")).toBe("video-once");
      expect(requestInitAt(1).body).toBe(JSON.stringify(payload));
    });
  });

  describe("capabilities", () => {
    test("obtiene snapshot de capacidades vía GET", async () => {
      const snapshot = {
        advisor: {
          status: "available",
          tier: "free",
          quality_levels: ["fast"],
        },
        copywriter: {
          status: "available",
          tier: "free",
          quality_levels: ["fast"],
        },
      };
      fetchMock.mockResolvedValueOnce(jsonResponse(snapshot));

      const result = await api.capabilities.get();

      expect(result).toMatchObject(snapshot);
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/capabilities",
        expect.objectContaining({ credentials: "include" })
      );
    });

    test("incluye las seis capacidades esperadas", async () => {
      const snapshot = {
        advisor: {
          status: "available",
          tier: "free",
          quality_levels: ["fast"],
        },
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
        trend_analysis: {
          status: "disabled",
          tier: "free",
          quality_levels: [],
        },
      };
      fetchMock.mockResolvedValueOnce(jsonResponse(snapshot));

      const result = await api.capabilities.get();

      expect(Object.keys(result)).toHaveLength(6);
      expect(result.advisor?.status).toBe("available");
      expect(result.image_generation?.status).toBe("disabled");
    });

    test("parsea los ocho estados posibles", async () => {
      const snapshot = {
        advisor: {
          status: "available",
          tier: "free",
          quality_levels: ["fast"],
        },
        copywriter: {
          status: "unconfigured",
          tier: "free",
          quality_levels: [],
        },
        vision_review: {
          status: "degraded",
          tier: "free",
          quality_levels: ["fast"],
        },
        image_generation: {
          status: "disabled",
          tier: "paid",
          quality_levels: [],
        },
        video_generation: {
          status: "payment_required",
          tier: "paid",
          quality_levels: [],
        },
        trend_analysis: {
          status: "quota_exhausted",
          tier: "free",
          quality_levels: [],
        },
      };
      fetchMock.mockResolvedValueOnce(jsonResponse(snapshot));

      const result = await api.capabilities.get();
      expect(result.advisor.status).toBe("available");
      expect(result.copywriter.status).toBe("unconfigured");
      expect(result.vision_review.status).toBe("degraded");
      expect(result.image_generation.status).toBe("disabled");
      expect(result.video_generation.status).toBe("payment_required");
      expect(result.trend_analysis.status).toBe("quota_exhausted");
    });

    test("devuelve las seis capacidades deterministas en modo demo", async () => {
      vi.mocked(isDemoModeEnabled).mockReturnValueOnce(true);

      const result = await api.capabilities.get();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(Object.keys(result)).toHaveLength(6);
      expect(result.advisor.status).toBe("available");
      expect(result.image_generation.tier).toBe("paid");
    });

    test("carga y actualiza la cuenta demo sin solicitar un backend", async () => {
      vi.mocked(isDemoModeEnabled).mockReturnValueOnce(true);
      await expect(api.auth.usage()).resolves.toEqual({
        period_days: 30,
        items: [],
      });

      vi.mocked(isDemoModeEnabled).mockReturnValueOnce(true);
      await expect(
        api.auth.updateAccount({ name: "Ana Local", interface_locale: "pt" })
      ).resolves.toMatchObject({
        user: {
          name: "Ana Local",
          email: "demo@hitrendy.local",
          interface_locale: "pt",
        },
      });

      expect(fetchMock).not.toHaveBeenCalled();
    });

    test("no solicita CSRF para GET", async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({}));

      await api.capabilities.get();

      const csrfCalls = fetchMock.mock.calls.filter(
        (c: unknown[]) => c[0] === "/api/v1/auth/csrf"
      );
      expect(csrfCalls.length).toBe(0);
    });

    test("error de API devuelve ApiError", async () => {
      fetchMock.mockResolvedValueOnce(
        new Response("Not Found", { status: 404 })
      );

      await expect(api.capabilities.get()).rejects.toThrow(ApiError);
    });
  });

  describe("social connections", () => {
    const connection = {
      id: "connection/1",
      provider: "demo",
      display_name: "Cuenta demo",
      account_type: "business",
      status: "connected",
      connected_at: "2026-08-01T12:00:00Z",
      last_checked_at: null,
      safe_error: null,
    };

    test("obtiene el catálogo y las conexiones vía GET", async () => {
      const payload = {
        enabled: true,
        providers: [{ name: "demo", status: "available", reason_code: null }],
        connections: [connection],
      };
      fetchMock.mockResolvedValueOnce(jsonResponse(payload));

      await expect(api.social.connections()).resolves.toEqual(payload);
      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/social/connections");
      expect(requestInitAt(0).method).toBeUndefined();
    });

    test("autoriza con provider codificado, return_path y POST", async () => {
      fetchMock
        .mockResolvedValueOnce(jsonResponse({ token: "csrf-social" }))
        .mockResolvedValueOnce(
          jsonResponse({
            provider: "demo",
            authorization_url: "https://provider.example/authorize",
          })
        );

      await api.social.authorize("demo/account", "/settings");

      expect(fetchMock.mock.calls[1]?.[0]).toBe(
        "/api/v1/social/demo%2Faccount/authorize"
      );
      expect(requestInitAt(1).method).toBe("POST");
      expect(requestInitAt(1).body).toBe(
        JSON.stringify({ return_path: "/settings" })
      );
      expect(requestHeadersAt(1).get("X-CSRF-Token")).toBe("csrf-social");
      expect(requestHeadersAt(1).has("Idempotency-Key")).toBe(false);
    });

    test("check y disconnect codifican el id, usan su método y desenvuelven connection", async () => {
      fetchMock
        .mockResolvedValueOnce(jsonResponse({ token: "csrf-check" }))
        .mockResolvedValueOnce(jsonResponse({ connection }))
        .mockResolvedValueOnce(jsonResponse({ connection }));

      await expect(api.social.check("connection/with space")).resolves.toEqual(
        connection
      );
      await expect(
        api.social.disconnect("connection/with space")
      ).resolves.toEqual(connection);

      expect(fetchMock.mock.calls[1]?.[0]).toBe(
        "/api/v1/social/connections/connection%2Fwith%20space/check"
      );
      expect(requestInitAt(1).method).toBe("POST");
      expect(requestInitAt(1).body).toBeUndefined();
      expect(fetchMock.mock.calls[2]?.[0]).toBe(
        "/api/v1/social/connections/connection%2Fwith%20space"
      );
      expect(requestInitAt(2).method).toBe("DELETE");
      expect(requestInitAt(2).body).toBeUndefined();
    });

    test("propaga ApiError desde cada operación social", async () => {
      const operations: Array<{
        run: () => Promise<unknown>;
        responses: Response[];
      }> = [
        {
          run: () => api.social.connections(),
          responses: [errorResponse("SOCIAL_FAILURE", 409)],
        },
        {
          run: () => api.social.authorize("demo"),
          responses: [
            jsonResponse({ token: "csrf-social" }),
            errorResponse("SOCIAL_FAILURE", 409),
          ],
        },
        {
          run: () => api.social.check("connection-1"),
          responses: [
            jsonResponse({ token: "csrf-social" }),
            errorResponse("SOCIAL_FAILURE", 409),
          ],
        },
        {
          run: () => api.social.disconnect("connection-1"),
          responses: [
            jsonResponse({ token: "csrf-social" }),
            errorResponse("SOCIAL_FAILURE", 409),
          ],
        },
      ];

      for (const operation of operations) {
        resetCsrfToken();
        fetchMock.mockReset();
        fetchMock.mockImplementationOnce(() =>
          Promise.resolve(operation.responses[0] as Response)
        );
        for (const response of operation.responses.slice(1)) {
          fetchMock.mockImplementationOnce(() => Promise.resolve(response));
        }

        await expect(operation.run()).rejects.toMatchObject({
          code: "SOCIAL_FAILURE",
        });
      }
    });
  });
});
