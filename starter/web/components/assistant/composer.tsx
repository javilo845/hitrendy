"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";

import { ChatIcon } from "@/components/assistant/chat-icon";

const DRAFT_STORAGE_PREFIX = "hitrendy:composer-draft:";

/** Mirrors the backend's allow-list, so a rejected file is refused up front. */
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const ACCEPT_ATTRIBUTE = ACCEPTED_TYPES.join(",");

/** Sent when an image arrives with no accompanying question. */
const DEFAULT_VISUAL_PROMPT = "Analiza esta imagen para mi negocio.";

interface Attachment {
  key: string;
  name: string;
  previewUrl: string;
  assetId?: string;
  status: "uploading" | "ready" | "error";
}

interface Props {
  /** `attachmentIds` is empty unless the user attached something. */
  onSend: (text: string, attachmentIds: string[]) => void;
  disabled: boolean;
  placeholder?: string;
  /** Identifies the conversation whose local draft is being edited. */
  draftKey?: string;
  /**
   * Uploads one image and resolves to its asset id. Providing this turns on the
   * whole attachment surface: the picker, clipboard paste and drag-and-drop.
   */
  onUploadImage?: (file: File) => Promise<string>;
  /**
   * Fallback for surfaces that cannot hold an attachment yet — the empty state,
   * where there is no conversation to upload into. Ignored when
   * `onUploadImage` is given.
   */
  onAttach?: () => void;
  attachLabel?: string;
  attachBusy?: boolean;
  /**
   * Turns the field into an image request instead of a message. Optional on
   * purpose: generating an image is one thing the assistant can do, not the
   * way the composer works.
   */
  onGenerateImage?: (prompt: string) => void;
  imageBusy?: boolean;
}

export function Composer({
  onSend,
  disabled,
  placeholder,
  draftKey,
  onUploadImage,
  onAttach,
  attachLabel = "Adjuntar una imagen",
  attachBusy = false,
  onGenerateImage,
  imageBusy = false,
}: Props) {
  const [value, setValue] = useState("");
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [listening, setListening] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [multiline, setMultiline] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [attachError, setAttachError] = useState("");
  const [imageMode, setImageMode] = useState(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const recognitionRef = useRef<{ start: () => void; stop: () => void } | null>(
    null
  );
  const activeDraftKeyRef = useRef(draftKey);
  const hasText = Boolean(value.trim());
  const canAttachFiles = Boolean(onUploadImage);
  const uploading = attachments.some((item) => item.status === "uploading");
  const readyAttachments = attachments.filter((item) => item.assetId);
  const canSend = (hasText || readyAttachments.length > 0) && !uploading;

  const updateDraft = useCallback(
    (nextValue: string | ((current: string) => string)) => {
      setValue((current) => {
        const resolved =
          typeof nextValue === "function" ? nextValue(current) : nextValue;
        const key = activeDraftKeyRef.current;

        if (key) {
          try {
            if (resolved) {
              window.localStorage.setItem(`${DRAFT_STORAGE_PREFIX}${key}`, resolved);
            } else {
              window.localStorage.removeItem(`${DRAFT_STORAGE_PREFIX}${key}`);
            }
          } catch {
            // The composer remains usable when browser storage is unavailable.
          }
        }

        return resolved;
      });
    },
    []
  );

  useEffect(() => {
    activeDraftKeyRef.current = draftKey;
    if (!draftKey) {
      setValue("");
      return;
    }

    try {
      setValue(window.localStorage.getItem(`${DRAFT_STORAGE_PREFIX}${draftKey}`) || "");
    } catch {
      setValue("");
    }
  }, [draftKey]);

  useEffect(() => {
    const VoiceRecognition = (
      window as typeof window & {
        webkitSpeechRecognition?: new () => {
          lang: string;
          interimResults: boolean;
          start: () => void;
          stop: () => void;
          onresult: (event: {
            results: ArrayLike<ArrayLike<{ transcript: string }>>;
          }) => void;
          onend: () => void;
        };
      }
    ).webkitSpeechRecognition;
    if (!VoiceRecognition) return;
    const recognition = new VoiceRecognition();
    recognition.lang = "es-ES";
    recognition.interimResults = false;
    recognition.onresult = (event) =>
      updateDraft((current) =>
        `${current} ${event.results[0][0].transcript}`.trim()
      );
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setVoiceAvailable(true);
    return () => recognition.stop();
  }, [updateDraft]);

  // Previews are object URLs; nothing else releases them.
  const previewUrlsRef = useRef<string[]>([]);
  previewUrlsRef.current = attachments.map((item) => item.previewUrl);
  useEffect(
    () => () => {
      previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    },
    []
  );

  /**
   * The single entry point for picked, pasted and dropped images. Each file is
   * shown immediately and uploaded in the background, so the user sees what
   * they attached before the network has finished with it.
   */
  const addFiles = useCallback(
    (files: File[]) => {
      if (!onUploadImage || files.length === 0) return;
      const accepted = files.filter((file) => ACCEPTED_TYPES.includes(file.type));
      if (accepted.length < files.length) {
        setAttachError("Solo aceptamos imágenes JPG, PNG o WebP.");
      } else {
        setAttachError("");
      }

      accepted.forEach((file) => {
        const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const entry: Attachment = {
          key,
          name: file.name || "Imagen pegada",
          previewUrl: URL.createObjectURL(file),
          status: "uploading",
        };
        setAttachments((current) => [...current, entry]);

        void onUploadImage(file)
          .then((assetId) =>
            setAttachments((current) =>
              current.map((item) =>
                item.key === key ? { ...item, assetId, status: "ready" } : item
              )
            )
          )
          .catch(() => {
            setAttachError("No pudimos subir la imagen. Inténtalo de nuevo.");
            setAttachments((current) =>
              current.map((item) =>
                item.key === key ? { ...item, status: "error" } : item
              )
            );
          });
      });
    },
    [onUploadImage]
  );

  function removeAttachment(key: string) {
    setAttachments((current) => {
      const target = current.find((item) => item.key === key);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.key !== key);
    });
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (!canAttachFiles) return;
    const files = Array.from(event.clipboardData.files);
    if (files.length === 0) return;
    // Screenshots arrive as files with no text alternative, so keeping the
    // default would paste nothing at all.
    event.preventDefault();
    addFiles(files);
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    if (!canAttachFiles || !event.dataTransfer.types.includes("Files")) return;
    dragDepthRef.current += 1;
    setDragOver(true);
  }

  function handleDragLeave() {
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragOver(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (!canAttachFiles) return;
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragOver(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    if (disabled || !canSend) return;
    const trimmed = value.trim();
    const assetIds = readyAttachments
      .map((item) => item.assetId)
      .filter((id): id is string => Boolean(id));
    const text = trimmed || DEFAULT_VISUAL_PROMPT;

    // Image mode needs a description of its own; an attachment is a different
    // request, so the two never travel together.
    if (imageMode && onGenerateImage && !assetIds.length) {
      if (!trimmed) return;
      onGenerateImage(trimmed);
      setImageMode(false);
      updateDraft("");
      setMultiline(false);
      if (textRef.current) textRef.current.style.height = "auto";
      return;
    }

    onSend(text, assetIds);
    updateDraft("");
    attachments.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    setAttachments([]);
    setAttachError("");
    setMultiline(false);
    if (textRef.current) {
      textRef.current.style.height = "auto";
    }
  }

  function handleInput() {
    const field = textRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight}px`;
    setMultiline(field.scrollHeight > 56);
  }

  const expanded = attachments.length > 0 || multiline || Boolean(attachError);

  return (
    <div
      className="conversation-composer"
      data-expanded={expanded || undefined}
      data-dragover={dragOver || undefined}
      onDragEnter={handleDragEnter}
      onDragOver={(event) => {
        if (canAttachFiles && event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
        }
      }}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {canAttachFiles ? (
        <input
          ref={fileRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          className="visually-hidden"
          aria-label={attachLabel}
          onChange={(event) => {
            addFiles(Array.from(event.target.files || []));
            event.target.value = "";
          }}
        />
      ) : null}

      {attachments.length > 0 ? (
        <ul className="composer-attachments" aria-label="Imágenes adjuntas">
          {attachments.map((item) => (
            <li
              key={item.key}
              className="composer-attachment"
              data-status={item.status}
            >
              {/* Local preview of a file the user just chose; next/image would
                  route an object URL through the optimizer for nothing. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.previewUrl} alt="" />
              <span className="composer-attachment-name">
                {item.status === "uploading"
                  ? "Subiendo…"
                  : item.status === "error"
                    ? "Falló la subida"
                    : item.name}
              </span>
              <button
                type="button"
                className="composer-attachment-remove"
                onClick={() => removeAttachment(item.key)}
                aria-label={`Quitar ${item.name}`}
              >
                <ChatIcon name="close" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="composer-row">
        {canAttachFiles || onAttach ? (
          <button
            type="button"
            onClick={() =>
              canAttachFiles ? fileRef.current?.click() : onAttach?.()
            }
            disabled={disabled || attachBusy}
            aria-label={attachLabel}
            title={attachLabel}
            className="composer-attach"
          >
            <ChatIcon name={attachBusy ? "spinner" : "plus"} />
          </button>
        ) : null}
        <textarea
          ref={textRef}
          value={value}
          onChange={(e) => updateDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          onPaste={handlePaste}
          placeholder={
            // With an image attached the field is a question box: the analysis
            // now answers what is written here, so the prompt says so.
            imageMode
              ? "Describe la imagen que quieres generar…"
              : attachments.length > 0
              ? "Pregunta algo sobre esta imagen…"
              : placeholder ||
                (canAttachFiles
                  ? "Escribe tu mensaje o pega una imagen…"
                  : "Escribe tu mensaje…")
          }
          disabled={disabled}
          rows={1}
          aria-label="Mensaje"
          className="composer-input"
        />
        {/* The right slot mirrors the reference: dictation while there is
            nothing to send, sending once there is. Enter submits either way, so
            no control is ever a dead end. */}
        {voiceAvailable && !canSend ? (
          <button
            type="button"
            onClick={() => {
              if (listening) recognitionRef.current?.stop();
              else {
                setListening(true);
                recognitionRef.current?.start();
              }
            }}
            disabled={disabled}
            aria-label={listening ? "Detener dictado" : "Dictar mensaje"}
            aria-pressed={listening}
            className="composer-mic"
            data-listening={listening || undefined}
          >
            <ChatIcon name="microphone" />
          </button>
        ) : null}
        {canSend || !voiceAvailable ? (
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !canSend}
            aria-label="Enviar"
            className="composer-send"
          >
            <ChatIcon name="send" />
          </button>
        ) : null}
      </div>

      {onGenerateImage ? (
        <div className="composer-modes">
          {/* Below the field, off by default: generating an image is an option
              the user opts into for one message, not the composer's mode. */}
          <button
            type="button"
            className="composer-mode"
            onClick={() => setImageMode((current) => !current)}
            aria-pressed={imageMode}
            disabled={disabled || imageBusy || attachments.length > 0}
            data-busy={imageBusy || undefined}
          >
            <ChatIcon name={imageBusy ? "spinner" : "image"} />
            {imageBusy ? "Generando imagen…" : "Generar imagen"}
          </button>
          {imageMode ? (
            <span className="composer-mode-hint">
              Describe la escena y pulsa enviar. Se usará una de tus imágenes
              del día.
            </span>
          ) : null}
        </div>
      ) : null}

      {attachError ? (
        <p className="composer-attach-error" role="alert">
          {attachError}
        </p>
      ) : null}
    </div>
  );
}
