"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import {
  ASSISTANT_STATUS_CHECKING,
  ASSISTANT_STATUS_UNREACHABLE,
  assistantStatusFrom,
  type AssistantStatus,
} from "@/lib/assistant-status";

/**
 * Reads the real capability snapshot instead of assuming the assistant is up.
 *
 * It re-reads when the tab comes back to the foreground and whenever the caller
 * asks — a generation that fails with a provider error is the moment the
 * snapshot is most likely to have changed.
 */
export function useAssistantStatus(): {
  assistant: AssistantStatus;
  refreshAssistant: () => void;
} {
  const [assistant, setAssistant] = useState<AssistantStatus>(
    ASSISTANT_STATUS_CHECKING
  );
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    void api.capabilities
      .get()
      .then((capabilities) => {
        if (active) setAssistant(assistantStatusFrom(capabilities));
      })
      .catch(() => {
        if (active) setAssistant(ASSISTANT_STATUS_UNREACHABLE);
      });
    return () => {
      active = false;
    };
  }, [reload]);

  const refreshAssistant = useCallback(() => setReload((n) => n + 1), []);

  useEffect(() => {
    function onVisibility() {
      if (document.visibilityState === "visible") refreshAssistant();
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () =>
      document.removeEventListener("visibilitychange", onVisibility);
  }, [refreshAssistant]);

  return { assistant, refreshAssistant };
}
