"use client";

import { useEffect, useRef } from "react";
import { Markdown } from "@/components/assistant/markdown";
import { AdvisorResponseCard, type AdvisorData } from "@/components/advisor-response-card";
import { GeneratedArtifactCard } from "@/components/generated-artifact-card";
import { GeneratedImageCard, type ChatImage } from "@/components/assistant/generated-image-card";
import { GeneratedVideoScriptCard } from "@/components/generated-video-script-card";
import { VisualReviewCard, type VisualAnalysis } from "@/components/visual-review-card";
import type { GeneratedArtifact } from "@/types/artifact";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifact?: GeneratedArtifact;
  analysis?: VisualAnalysis;
  advisor?: AdvisorData;
  image?: ChatImage;
  artifactId?: string;
}

interface Props {
  messages: Message[];
  loading: boolean;
  loadingLabel?: string;
  onCancel?: () => void;
  onSave?: (artifactId: string | undefined) => void;
  onVariation?: (artifactId: string | undefined, kind: string) => void;
  onFeedback?: (
    artifactId: string | undefined,
    rating: "useful" | "not_useful"
  ) => void;
  onCopy?: (artifactId: string | undefined) => void;
}

export function MessageList({
  messages,
  loading,
  loadingLabel = "Preparando una propuesta para tu negocio…",
  onCancel,
  onSave,
  onVariation,
  onFeedback,
  onCopy,
}: Props) {
  const logRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const container = logRef.current;
    if (container && typeof container.scrollTo === "function") {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: reducedMotion ? "auto" : "smooth",
      });
    } else if (bottomRef.current && typeof bottomRef.current.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
      });
    } else if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="assistant-empty-state">
        <span className="empty-state-mark" aria-hidden="true">+</span>
        <h2>
          ¿Qué quieres crear hoy?
        </h2>
        <p>Empieza con una idea, un objetivo o un diseño que quieras mejorar.</p>
      </div>
    );
  }

  return (
    <div
      ref={logRef}
      role="log"
      aria-label="Conversación"
      aria-live="polite"
      aria-relevant="additions text"
      aria-busy={loading}
      className="message-log"
    >
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`message-row message-row--${msg.role}`}
        >
          <div
            className={`message-bubble message-bubble--${msg.role}`}
          >
            {msg.image ? (
              <GeneratedImageCard image={msg.image} />
            ) : msg.analysis ? (
              <VisualReviewCard analysis={msg.analysis} />
            ) : msg.advisor ? (
              <AdvisorResponseCard advisor={msg.advisor} />
            ) : msg.artifact?.artifact_type === "social_post" ? (
              <GeneratedArtifactCard
                artifact={msg.artifact}
                onSave={() => onSave?.(msg.artifactId)}
                onVariation={(kind) => onVariation?.(msg.artifactId, kind)}
                onFeedback={(rating) => onFeedback?.(msg.artifactId, rating)}
                onCopy={() => onCopy?.(msg.artifactId)}
              />
            ) : msg.artifact?.artifact_type === "short_video_script" ? (
              <GeneratedVideoScriptCard
                artifact={msg.artifact}
                onSave={() => onSave?.(msg.artifactId)}
                onFeedback={(rating) => onFeedback?.(msg.artifactId, rating)}
                onCopy={() => onCopy?.(msg.artifactId)}
              />
            ) : msg.role === "assistant" ? (
              // Assistant turns are markdown; user turns are literal text and
              // stay in the pre-wrapped paragraph so their line breaks survive.
              <div className="message-text message-prose">
                <Markdown>{msg.content}</Markdown>
              </div>
            ) : (
              <p className="message-text">{msg.content}</p>
            )}
          </div>
        </div>
      ))}

      {loading && (
        <div
          role="status"
          className="message-loading"
        >
          <span>{loadingLabel}</span>
          {onCancel ? (
            <button type="button" onClick={onCancel} className="button-secondary">
              Cancelar
            </button>
          ) : null}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
