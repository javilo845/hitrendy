const FIRST_PROMPT_KEY = "hitrendy:first-prompt";

function read(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // The creation flow remains available when browser storage is blocked.
  }
}

function remove(key: string) {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Nothing else is required when browser storage is blocked.
  }
}

export interface FirstPromptPayload {
  text: string;
  intent?: "create_social_post" | "create_short_video_script" | "analyze_visual" | "ask_advisor";
  attachmentIds?: string[];
}

export function saveFirstPrompt(
  prompt: string | FirstPromptPayload,
  intent?: FirstPromptPayload["intent"],
  attachmentIds?: string[]
) {
  if (typeof prompt === "object") {
    write(FIRST_PROMPT_KEY, JSON.stringify(prompt));
  } else if (intent || attachmentIds?.length) {
    write(FIRST_PROMPT_KEY, JSON.stringify({ text: prompt.trim(), intent, attachmentIds }));
  } else {
    write(FIRST_PROMPT_KEY, prompt.trim());
  }
}

export function takeFirstPrompt(): FirstPromptPayload | null {
  const raw = read(FIRST_PROMPT_KEY);
  remove(FIRST_PROMPT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && typeof parsed.text === "string") {
      return parsed as FirstPromptPayload;
    }
  } catch {
    // raw string
  }
  return { text: raw };
}

export function peekFirstPrompt(): string | null {
  const raw = read(FIRST_PROMPT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && typeof parsed.text === "string") {
      return parsed.text;
    }
  } catch {
    // raw string
  }
  return raw;
}
