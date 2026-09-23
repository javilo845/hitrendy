"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { InstagramPostFlow } from "@/components/studio/instagram-post-flow";
import { StudioWorkspace } from "@/components/studio/studio-workspace";

/**
 * `/studio/new` is the chat. The guided Instagram flow still owns the route
 * when it is reached through one of its own deep links (a saved project, an
 * observed trend, a chosen template), so every existing link keeps working.
 */
function NewStudioSurface() {
  const searchParams = useSearchParams();
  const guided =
    searchParams.has("project") ||
    searchParams.has("trend") ||
    searchParams.has("template");

  return guided ? <InstagramPostFlow /> : <StudioWorkspace />;
}

export default function NewStudioPage() {
  return (
    <AppShell>
      <Suspense
        fallback={
          <div className="route-status" role="status">
            Abriendo Studio…
          </div>
        }
      >
        <NewStudioSurface />
      </Suspense>
    </AppShell>
  );
}
