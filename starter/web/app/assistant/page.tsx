"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { RouteSplash } from "@/components/auth/route-splash";

function AssistantRedirectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  useEffect(() => {
    const conversation = searchParams.get("conversation");
    router.replace(
      conversation
        ? `/studio/${encodeURIComponent(conversation)}`
        : "/studio/new"
    );
  }, [router, searchParams]);
  return <RouteSplash label="Abriendo Studio…" />;
}

export default function AssistantRedirect() {
  return (
    <Suspense fallback={<RouteSplash label="Abriendo Studio…" />}>
      <AssistantRedirectContent />
    </Suspense>
  );
}
