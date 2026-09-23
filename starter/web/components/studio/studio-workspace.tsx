"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";

import { ChatIcon, type ChatIconName } from "@/components/assistant/chat-icon";
import { Composer } from "@/components/assistant/composer";
import { Logo } from "@/components/brand/logo";
import { MessageList } from "@/components/assistant/message-list";
import { useAssistantStatus } from "@/components/studio/use-assistant-status";
import { api, ApiError, createIdempotencyKey } from "@/lib/api";
import {
  imageGenerationMessage,
  runImageGeneration,
  DEFAULT_ASPECT_RATIO,
} from "@/lib/image-generation";
import {
  peekFirstPrompt,
  saveFirstPrompt,
  takeFirstPrompt,
} from "@/lib/creation-draft";
import { routes } from "@/lib/routes";
import type { GeneratedArtifact, GeneratedSocialPost } from "@/types/artifact";
import type { AdvisorData } from "@/components/advisor-response-card";
import type { ChatImage } from "@/components/assistant/generated-image-card";
import type { VisualAnalysis } from "@/components/visual-review-card";

type ConversationStatus = "active" | "archived";

interface ConversationItem {
  id: string;
  title: string;
  status: ConversationStatus;
  last_message?: string | null;
  updated_at?: string | null;
}
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifact?: GeneratedArtifact;
  analysis?: VisualAnalysis;
  advisor?: AdvisorData;
  image?: ChatImage;
  artifactId?: string;
}
interface ConversationData {
  messages?: Array<{
    id: string;
    role: string;
    content: string;
    metadata?: { analysis?: VisualAnalysis; advisor?: AdvisorData } | null;
    artifact?: GeneratedArtifact;
    artifact_id?: string | null;
  }>;
}
interface SendResult {
  type: string;
  message?: string;
  assistant_message?: { id: string; content: string };
  artifact?: GeneratedArtifact;
  artifact_id?: string;
  analysis?: VisualAnalysis;
  advisor?: AdvisorData;
}

type GenerationIntent =
  | "create_social_post"
  | "create_short_video_script"
  | "analyze_visual"
  | "ask_advisor";

interface GenerationOperation {
  key: string;
  text: string;
  intent: GenerationIntent;
  attachmentIds: string[];
  token: number;
}

/**
 * The quick actions seed the conversation with the request they name, so each
 * button must produce a prompt that will pass validation as an initial turn.
 */
const QUICK_ACTIONS: Array<{
  label: string;
  hint: string;
  prompt: string;
  intent?: GenerationIntent;
}> = [
  {
    label: "Auditar diseño y sugerir Canva",
    hint: "Detecta errores/IA y recomienda plantillas de Canva.",
    prompt: "Quiero auditar el diseño de una imagen o volante para mi negocio y usar una plantilla de Canva.",
    intent: "analyze_visual",
  },
  {
    label: "Crear publicación para redes",
    hint: "Texto, gancho y llamado a la acción comercial.",
    prompt: "Quiero crear una publicación para las redes de mi negocio.",
    intent: "create_social_post",
  },
  {
    label: "Planear contenido de la semana",
    hint: "Ideas y estrategia semanal adaptadas a tu negocio.",
    prompt: "Ayúdame a planear el contenido de las próximas semanas.",
    intent: "ask_advisor",
  },
];

const RAIL_LINKS: Array<{ href: string; label: string; icon: ChatIconName }> = [
  { href: routes.templates, label: "Plantillas", icon: "gallery" },
  { href: routes.library, label: "Biblioteca", icon: "library" },
];

export function StudioWorkspace({
  conversationId,
}: {
  conversationId?: string;
}) {
  const router = useRouter();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const historyToggleRef = useRef<HTMLButtonElement>(null);
  const firstPromptSentRef = useRef(false);
  const operationTokenRef = useRef(0);
  const generationControllerRef = useRef<AbortController | null>(null);
  const generationInFlightRef = useRef(false);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ConversationStatus>("active");
  const [query, setQuery] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [threadReady, setThreadReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState(
    "Preparando una propuesta para tu negocio…"
  );
  const [failedOperation, setFailedOperation] =
    useState<GenerationOperation | null>(null);
  const [creating, setCreating] = useState(false);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [firstPrompt, setFirstPrompt] = useState<string | null>(null);
  /**
   * The history is a dropdown at every width, so this drives the whole layout:
   * the rail toggle owns `aria-expanded`, the panel opens over the canvas and
   * the scrim closes it again.
   */
  const [panelOpen, setPanelOpen] = useState(false);
  const { assistant, refreshAssistant } = useAssistantStatus();

  useEffect(() => {
    return () => {
      operationTokenRef.current += 1;
      generationControllerRef.current?.abort();
      generationControllerRef.current = null;
      generationInFlightRef.current = false;
    };
  }, [conversationId]);

  useEffect(() => {
    let active = true;
    setLoadingList(true);
    void api.conversations
      .list({ status, ...(query.trim() ? { search: query.trim() } : {}) })
      .then((items) => {
        if (active) setConversations(items as unknown as ConversationItem[]);
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof ApiError
              ? reason.message
              : "No pudimos cargar las conversaciones."
          );
      })
      .finally(() => {
        if (active) setLoadingList(false);
      });
    return () => {
      active = false;
    };
  }, [query, status]);

  useEffect(() => {
    let active = true;
    if (!conversationId) {
      setMessages([]);
      setThreadReady(false);
      return () => {
        active = false;
      };
    }
    setLoadingThread(true);
    setThreadReady(false);
    setError("");
    void api.conversations
      .get(conversationId)
      .then((data) => {
        if (!active) return;
        const thread = data as ConversationData;
        setMessages(
          (thread.messages || []).map((message) => ({
            id: message.id,
            role: message.role as "user" | "assistant",
            content: message.content,
            analysis: message.metadata?.analysis,
            advisor: message.metadata?.advisor,
            artifact: message.artifact,
            artifactId: message.artifact_id || undefined,
          }))
        );
      })
      .catch((reason) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) {
          router.replace(routes.studioNew);
          return;
        }
        setError(
          reason instanceof ApiError
            ? reason.message
            : "No pudimos abrir esta conversación."
        );
      })
      .finally(() => {
        if (active) {
          setLoadingThread(false);
          setThreadReady(true);
        }
      });
    return () => {
      active = false;
    };
  }, [conversationId, router]);

  useEffect(() => {
    if (!conversationId) {
      firstPromptSentRef.current = false;
      setFirstPrompt(peekFirstPrompt());
    }
  }, [conversationId]);

  // Opening a conversation from the drawer should leave the thread in view.
  useEffect(() => {
    setPanelOpen(false);
  }, [conversationId]);

  async function createConversation() {
    setCreating(true);
    setError("");
    try {
      const businesses = await api.businesses.list();
      if (!businesses.length) {
        router.push(routes.onboarding);
        return;
      }
      const conversation = await api.conversations.create({
        business_id: businesses[0].id,
        title: "Nueva conversación",
      });
      router.push(`/studio/${encodeURIComponent(conversation.id as string)}`);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "No pudimos crear la conversación."
      );
    } finally {
      setCreating(false);
    }
  }

  /**
   * The empty-state field is the same composer used inside a thread: the text
   * is parked in session storage and the new conversation replays it as its
   * first message once the thread is ready.
   */
  function startConversationWith(
    text: string,
    intent: GenerationIntent = "create_social_post",
    attachmentIds: string[] = []
  ) {
    saveFirstPrompt({ text, intent, attachmentIds });
    setFirstPrompt(text);
    void createConversation();
  }

  function startFromComposer(text: string, attachmentIds: string[] = []) {
    startConversationWith(
      text,
      attachmentIds.length ? "analyze_visual" : "create_social_post",
      attachmentIds
    );
  }

  async function updateConversation(item: ConversationItem) {
    setUpdatingId(item.id);
    setError("");
    try {
      await api.conversations.update(item.id, {
        status: item.status === "active" ? "archived" : "active",
      });
      setConversations((items) =>
        items.filter((conversation) => conversation.id !== item.id)
      );
      if (item.id === conversationId) router.push(routes.studioNew);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "No pudimos actualizar la conversación."
      );
    } finally {
      setUpdatingId(null);
    }
  }

  async function send(
    text: string,
    intent: GenerationIntent = "create_social_post",
    attachmentIds: string[] = [],
    continuation?: GenerationOperation
  ) {
    if (generationInFlightRef.current) return;
    if (!conversationId) {
      startConversationWith(text, intent, attachmentIds);
      return;
    }
    const operation = continuation || {
      key: createIdempotencyKey(),
      text,
      intent,
      attachmentIds: [...attachmentIds],
      token: operationTokenRef.current + 1,
    };
    if (!continuation) {
      operationTokenRef.current = operation.token;
      setMessages((current) => [
        ...current,
        { id: `temp_${operation.token}`, role: "user", content: text },
      ]);
    }
    generationInFlightRef.current = true;
    generationControllerRef.current?.abort();
    const controller = new AbortController();
    generationControllerRef.current = controller;
    setLoading(true);
    setLoadingLabel("Preparando una propuesta para tu negocio…");
    setFailedOperation(null);
    setError("");
    try {
      const result = (await api.conversations.sendMessage(
        conversationId,
        operation.text,
        operation.intent,
        operation.attachmentIds,
        {
          idempotencyKey: operation.key,
          signal: controller.signal,
          onRetry: () =>
            setLoadingLabel("Hubo un problema temporal. Reintentando…"),
        }
      )) as unknown as SendResult;
      if (operation.token !== operationTokenRef.current) return;
      if (result.type === "artifact")
        setMessages((current) => [
          ...current,
          {
            id: result.assistant_message?.id || `msg_${Date.now()}`,
            role: "assistant",
            content: result.assistant_message?.content || "",
            artifact: result.artifact,
            artifactId: result.artifact_id,
          },
        ]);
      else if (result.type === "advisor" && result.advisor) {
        setMessages((current) => [
          ...current,
          {
            id: result.assistant_message?.id || `advisor_${Date.now()}`,
            role: "assistant",
            content: result.assistant_message?.content || result.advisor?.summary || "",
            advisor: result.advisor,
          },
        ]);
      } else if (result.type === "visual_analysis" && result.analysis) {
        const analysis = result.analysis;
        setMessages((current) => [
          ...current,
          {
            id: result.assistant_message?.id || `analysis_${Date.now()}`,
            role: "assistant",
            content: result.assistant_message?.content || analysis.summary,
            analysis,
          },
        ]);
      } else if (result.type === "error")
        setError(result.message || "No pudimos generar contenido.");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError")
        return;
      if (operation.token !== operationTokenRef.current) return;
      // A provider-side failure is exactly when the capability snapshot may
      // have changed, so the header stops claiming the assistant is up.
      if (
        reason instanceof ApiError &&
        (reason.status >= 500 || reason.status === 429 || reason.status === 402)
      )
        refreshAssistant();
      if (reason instanceof ApiError && reason.retryable) {
        setFailedOperation(operation);
        setError("No pudimos generar el contenido en este momento.");
      } else {
        setError(
          reason instanceof ApiError
            ? reason.message
            : "Error de conexión. Tu mensaje sigue disponible en el borrador."
        );
      }
    } finally {
      generationInFlightRef.current = false;
      if (operation.token === operationTokenRef.current) {
        generationControllerRef.current = null;
        setLoading(false);
        setLoadingLabel("Preparando una propuesta para tu negocio…");
      }
    }
  }

  function cancelGeneration() {
    operationTokenRef.current += 1;
    generationControllerRef.current?.abort();
    generationControllerRef.current = null;
    generationInFlightRef.current = false;
    setLoading(false);
    setFailedOperation(null);
    setError("Generación cancelada.");
  }

  function retryFailedGeneration() {
    if (!failedOperation) return;
    void send(
      failedOperation.text,
      failedOperation.intent,
      failedOperation.attachmentIds,
      failedOperation
    );
  }

  useEffect(() => {
    if (!conversationId || !threadReady || firstPromptSentRef.current) return;
    const promptPayload = takeFirstPrompt();
    if (promptPayload && promptPayload.text) {
      firstPromptSentRef.current = true;
      void send(
        promptPayload.text,
        promptPayload.intent || "create_social_post",
        promptPayload.attachmentIds || []
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, threadReady]);

  /**
   * Uploading is now separate from sending: the composer holds the attachment
   * as a preview chip so a pasted screenshot can be captioned, replaced or
   * removed before anything reaches the assistant.
   */
  async function uploadVisual(file: File): Promise<string> {
    const uploaded = await api.assets.upload(file);
    const assetId = uploaded.asset_id as string | undefined;
    if (!assetId) throw new Error("La imagen no se pudo preparar.");
    return assetId;
  }

  /**
   * An attached image is always a request to look at that image, so the intent
   * follows the attachment rather than asking the user to declare it.
   */
  function sendFromComposer(text: string, attachmentIds: string[]) {
    void send(
      text,
      attachmentIds.length ? "analyze_visual" : "create_social_post",
      attachmentIds
    );
  }

  /**
   * Generating an image is a request of its own: it does not go through the
   * conversation endpoint, which has no image intent, so the turn is composed
   * here and the durable job is watched until it lands.
   *
   * The result lives in this thread's view only. The image itself is durable
   * and reachable from the library; the chat is not its record.
   */
  async function generateImage(prompt: string) {
    if (generatingImage) return;
    const token = `image_${Date.now()}`;
    setGeneratingImage(true);
    setError("");
    setMessages((current) => [
      ...current,
      { id: `${token}_user`, role: "user", content: prompt },
      {
        id: token,
        role: "assistant",
        content: "",
        image: {
          state: "working",
          prompt,
          aspectRatio: DEFAULT_ASPECT_RATIO,
          message: "Preparando la descripción visual…",
        },
      },
    ]);

    function update(image: Partial<ChatImage>) {
      setMessages((current) =>
        current.map((message) =>
          message.id === token && message.image
            ? { ...message, image: { ...message.image, ...image } }
            : message
        )
      );
    }

    try {
      const businesses = await api.businesses.list();
      if (!businesses.length) {
        router.push(routes.onboarding);
        return;
      }
      const result = await runImageGeneration(prompt, {
        businessId: businesses[0].id as string,
        onProgress: (message) => update({ message }),
      });
      update({ state: "ready", url: result.url, budget: result.budget });
    } catch (reason) {
      // The capability snapshot is worth re-reading here for the same reason
      // as a failed generation: this is when it changes.
      if (
        reason instanceof ApiError &&
        (reason.status >= 500 || reason.status === 429 || reason.status === 402)
      )
        refreshAssistant();
      update({ state: "failed", message: imageGenerationMessage(reason) });
    } finally {
      setGeneratingImage(false);
    }
  }

  async function saveArtifact(artifactId: string | undefined) {
    if (!artifactId) return;
    try {
      await api.projects.create({ artifact_id: artifactId });
      void api.artifacts.event(artifactId, "saved");
      setError("Proyecto guardado.");
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "No pudimos guardar el proyecto."
      );
    }
  }

  async function createVariation(artifactId: string | undefined, kind: string) {
    if (
      !artifactId ||
      !conversationId ||
      loading ||
      generationInFlightRef.current
    )
      return;
    generationInFlightRef.current = true;
    const controller = new AbortController();
    generationControllerRef.current = controller;
    setLoading(true);
    try {
      const result = (await api.artifacts.createVariation(
        conversationId,
        artifactId,
        kind,
        {
          idempotencyKey: createIdempotencyKey(),
          signal: controller.signal,
          onRetry: () =>
            setLoadingLabel("Hubo un problema temporal. Reintentando…"),
        }
      )) as unknown as SendResult;
      if (result.type === "artifact" && result.artifact)
        setMessages((current) => [
          ...current,
          {
            id: `var_${Date.now()}`,
            role: "assistant",
            content: (result.artifact as GeneratedSocialPost).caption || "",
            artifact: result.artifact,
            artifactId,
          },
        ]);
      else setError(result.message || "No pudimos crear la variación.");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError")
        return;
      setError(
        reason instanceof ApiError
          ? reason.message
          : "No pudimos crear la variación."
      );
    } finally {
      generationInFlightRef.current = false;
      generationControllerRef.current = null;
      setLoading(false);
      setLoadingLabel("Preparando una propuesta para tu negocio…");
    }
  }

  function focusSearch() {
    setPanelOpen(true);
    // The dropdown fades in; focus once it has been painted.
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }

  /**
   * Closing a dropdown has to hand focus back to the control that opened it,
   * otherwise a keyboard user who presses Escape is left on a hidden element
   * and restarts from the top of the document.
   */
  function closePanel() {
    setPanelOpen(false);
    historyToggleRef.current?.focus();
  }

  function handleLayoutKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && panelOpen) {
      event.stopPropagation();
      closePanel();
    }
  }

  const activeConversation = conversations.find(
    (item) => item.id === conversationId
  );

  return (
    <section
      className="studio-layout"
      data-surface="chat"
      aria-label="Studio de contenido"
      onKeyDown={handleLayoutKeyDown}
    >
      {/* Spans the rail and the canvas, as in the reference: the wordmark sits
          above the icon column rather than beside it. */}
      <header className="studio-header">
        <Logo inverse />
        {/* Read from the capability snapshot, never assumed: the pip and the
            wording follow whatever the server reports for the advisor and the
            visual review. */}
        <p
          className="studio-status"
          data-tone={assistant.tone}
          title={assistant.detail}
          aria-live="polite"
        >
          <span aria-hidden="true" /> {assistant.label}
        </p>
        {conversationId ? (
          <h1 className="visually-hidden">
            {activeConversation?.title || "Conversación"}
          </h1>
        ) : null}
        <div className="studio-header-actions">
          <Link
            href={routes.dashboard}
            className="studio-header-button"
            title="Ir al inicio"
          >
            <ChatIcon name="home" />
            <span className="visually-hidden">Ir al inicio</span>
          </Link>
          <Link
            href={routes.settings}
            className="studio-header-button"
            title="Abrir ajustes"
          >
            <ChatIcon name="settings" />
            <span className="visually-hidden">Abrir ajustes</span>
          </Link>
        </div>
      </header>

      {/* The rail is icon-only by design, so every control keeps its label in
          the accessible name and repeats it in `title` for sighted hover. */}
      <nav className="studio-rail" aria-label="Acciones de Studio">
        <button
          type="button"
          className="studio-rail-button"
          ref={historyToggleRef}
          onClick={() => setPanelOpen((open) => !open)}
          aria-expanded={panelOpen}
          aria-controls="studio-history"
          aria-haspopup="true"
          data-active={panelOpen || undefined}
          title="Ver el historial"
        >
          <ChatIcon name="conversations" />
          <span className="visually-hidden">Ver el historial</span>
        </button>
        <button
          type="button"
          className="studio-rail-button"
          onClick={createConversation}
          disabled={creating}
          title="Empezar una conversación"
        >
          <ChatIcon name="compose" />
          <span className="visually-hidden">Empezar una conversación</span>
        </button>
        <button
          type="button"
          className="studio-rail-button"
          onClick={focusSearch}
          title="Buscar en el historial"
        >
          <ChatIcon name="search" />
          <span className="visually-hidden">Buscar en el historial</span>
        </button>
        {RAIL_LINKS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="studio-rail-button"
            title={item.label}
          >
            <ChatIcon name={item.icon} />
            <span className="visually-hidden">{item.label}</span>
          </Link>
        ))}
      </nav>

      {/* A dropdown: anchored to the rail toggle above and laid over the canvas
          instead of taking a column from it. The closed state is `visibility:
          hidden`, which also takes its controls out of the tab order. */}
      <aside
        className="studio-panel"
        id="studio-history"
        data-open={panelOpen || undefined}
        aria-label="Conversaciones"
      >
        <div className="studio-panel-head">
          <h2>Conversaciones</h2>
          <button
            type="button"
            className="studio-panel-close"
            onClick={closePanel}
            title="Cerrar el historial"
          >
            <ChatIcon name="close" />
            <span className="visually-hidden">Cerrar el historial</span>
          </button>
        </div>
        <button
          type="button"
          className="button-primary"
          onClick={createConversation}
          disabled={creating}
        >
          {creating ? "Creando…" : "Nueva creación"}
        </button>
        <label className="search-field" htmlFor="conversation-search">
          Buscar conversaciones
          <input
            id="conversation-search"
            ref={searchInputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Título o mensaje"
          />
        </label>
        <div
          className="studio-sidebar-tabs"
          role="tablist"
          aria-label="Estado de conversaciones"
        >
          <button
            type="button"
            role="tab"
            aria-selected={status === "active"}
            onClick={() => setStatus("active")}
          >
            Recientes
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={status === "archived"}
            onClick={() => setStatus("archived")}
          >
            Archivadas
          </button>
        </div>
        <div className="conversation-list" aria-live="polite">
          {loadingList ? (
            <p className="muted-text">Cargando…</p>
          ) : conversations.length ? (
            conversations.map((item) => (
              <div
                key={item.id}
                className="conversation-list-item"
                data-active={item.id === conversationId || undefined}
              >
                <Link
                  href={`/studio/${encodeURIComponent(item.id)}`}
                  aria-current={item.id === conversationId ? "page" : undefined}
                >
                  <strong>{item.title}</strong>
                  <span>{item.last_message || "Sin mensajes"}</span>
                </Link>
                <button
                  type="button"
                  onClick={() => updateConversation(item)}
                  disabled={updatingId === item.id}
                  aria-label={`${item.status === "active" ? "Archivar" : "Restaurar"} ${item.title}`}
                >
                  {updatingId === item.id
                    ? "…"
                    : item.status === "active"
                      ? "Archivar"
                      : "Restaurar"}
                </button>
              </div>
            ))
          ) : (
            <p className="muted-text">
              {query
                ? "No hay coincidencias."
                : status === "active"
                  ? "Aún no tienes conversaciones."
                  : "No hay conversaciones archivadas."}
            </p>
          )}
        </div>
      </aside>

      {panelOpen ? (
        <button
          type="button"
          className="studio-scrim"
          onClick={closePanel}
          aria-label="Cerrar el historial"
        />
      ) : null}

      <div className="studio-main">
        {conversationId ? (
          <>
            {error ? (
              <p className="studio-error" role="alert">
                {error}
              </p>
            ) : null}
            {loadingThread ? (
              <div className="route-status" role="status">
                Abriendo conversación…
              </div>
            ) : (
              <>
                <MessageList
                  messages={messages}
                  loading={loading}
                  loadingLabel={loadingLabel}
                  onCancel={cancelGeneration}
                  onSave={saveArtifact}
                  onVariation={createVariation}
                  onFeedback={(artifactId, rating) =>
                    artifactId
                      ? api.artifacts
                          .feedback(artifactId, rating)
                          .catch(() =>
                            setError("No pudimos guardar tu feedback.")
                          )
                      : undefined
                  }
                  onCopy={(artifactId) =>
                    artifactId
                      ? void api.artifacts.event(artifactId, "copied")
                      : undefined
                  }
                />
                <div className="studio-composer-dock">
                  {failedOperation ? (
                    <button
                      type="button"
                      className="button-secondary retry-generation"
                      onClick={retryFailedGeneration}
                    >
                      Intentar de nuevo
                    </button>
                  ) : null}
                  <div className="studio-thread-actions">
                    <button
                      type="button"
                      onClick={() =>
                        send(
                          "Crea un guion breve para video vertical sobre mi producto principal.",
                          "create_short_video_script"
                        )
                      }
                      disabled={loading}
                      className="studio-chip"
                    >
                      Crear guion
                    </button>
                  </div>
                  <Composer
                    onSend={sendFromComposer}
                    disabled={loading}
                    draftKey={conversationId}
                    onUploadImage={uploadVisual}
                    attachLabel="Adjuntar una imagen para analizar"
                    onGenerateImage={generateImage}
                    imageBusy={generatingImage}
                  />
                  <p className="composer-hint">
                    Pega una captura con Ctrl+V, arrástrala aquí o usa + para
                    subirla. La analizamos y te proponemos plantillas de Canva.
                  </p>
                </div>
              </>
            )}
          </>
        ) : (
          <section className="studio-empty-state">
            <div className="studio-welcome">
              <Logo inverse className="studio-welcome-logo" />
              <h1>
                {firstPrompt
                  ? "Tu idea está lista para convertirse en contenido."
                  : "¿Qué haremos hoy?"}
              </h1>
              <p>
                {firstPrompt
                  ? `“${firstPrompt}”`
                  : "Cuéntame qué necesitas y construiremos la idea paso a paso."}
              </p>
            </div>
            <div className="studio-composer-dock">
              {error ? (
                <p className="studio-error" role="alert">
                  {error}
                </p>
              ) : null}
              {/* Suggestions first: on an empty screen they are what tells the
                  user what this field is for, so they read before it, not
                  after. */}
              <div className="studio-quick-grid">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    className="studio-chip"
                    onClick={() => startConversationWith(action.prompt)}
                    disabled={creating}
                  >
                    <strong>{action.label}</strong>
                    <span>{action.hint}</span>
                  </button>
                ))}
              </div>
              <Composer
                onSend={startFromComposer}
                disabled={creating}
                draftKey="nueva-conversacion"
                placeholder="Escribe tu idea o pregunta…"
                onAttach={createConversation}
                attachLabel="Adjuntar contenido en una conversación nueva"
                attachBusy={creating}
              />
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
