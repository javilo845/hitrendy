"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { TemplateLibrary } from "@/components/templates/template-library";
import { api, ApiError } from "@/lib/api";
import { surfaceCopy, useInterfaceLocale } from "@/lib/i18n";
import type { Template } from "@/types/template";

export default function TemplatesPage() {
  const router = useRouter();
  const copy = surfaceCopy[useInterfaceLocale()].templates;
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.templates
      .list()
      .then((items) => setTemplates(items as unknown as Template[]))
      .catch((reason) =>
        setError(
          reason instanceof ApiError
            ? reason.message
            : copy.error
        )
      )
      .finally(() => setLoading(false));
  }, [copy.error]);

  async function useTemplate(template: Template) {
    router.push(`/studio/new?template=${encodeURIComponent(template.id)}`);
  }

  return (
    <AppShell>
      <main className="app-page templates-page">
        {error ? (
          <p className="page-error" role="alert">
            {error}
          </p>
        ) : null}
        {loading ? (
          <p className="route-status">{copy.loading}</p>
        ) : (
          <TemplateLibrary templates={templates} onUse={useTemplate} copy={copy} />
        )}
      </main>
    </AppShell>
  );
}
