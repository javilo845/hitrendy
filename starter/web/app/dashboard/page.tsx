"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { ProjectFolderCard, NewProjectFolderCard } from "@/components/projects/project-folder-card";
import { TemplateLibrary } from "@/components/templates/template-library";
import { TemplateCarousel } from "@/components/templates/template-carousel";
import { api, ApiError } from "@/lib/api";
import { routes } from "@/lib/routes";
import { toTemplatePresentation } from "@/lib/template-catalog";
import {
  loadRecommendedTemplates,
  readBusinessTargeting,
  type RecommendedTemplate,
} from "@/lib/template-recommendations";
import type { Template } from "@/types/template";
import {
  appCopy,
  formatDate,
  isSupportedLocale,
  readStoredLocale,
  surfaceCopy,
  translate,
  type AppLocale,
} from "@/lib/i18n";

interface ProjectItem {
  id: string;
  name: string;
  platform: string;
  status: "active" | "archived";
  updated_at: string | null;
  artifact_snapshot?: { hook?: string } | null;
}

function dateLabel(value: string | null, locale: AppLocale, empty: string) {
  return formatDate(locale, value) || empty;
}

/**
 * The three covers the hero shows before the catalogue answers.
 *
 * They are the shipped artwork, not placeholders: the rail is decorative, and
 * a hero that starts empty and fills in later moves the whole page under the
 * reader. Once the catalogue arrives the real templates take their place.
 */
const HERO_FALLBACK_COVERS = [
  "/templates/flores.png",
  "/templates/coffee.png",
  "/templates/amor.png",
];

export default function DashboardPage() {
  const router = useRouter();
  const [status, setStatus] = useState<"active" | "archived">("active");
  const [view, setView] = useState<"projects" | "templates">("projects");
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [recommended, setRecommended] = useState<RecommendedTemplate[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [locale, setLocale] = useState<AppLocale>(readStoredLocale);
  const copy = appCopy[locale];
  const initialProjectError = useRef(copy.dashboard.loadError);
  useEffect(() => {
    const onLocale = (event: Event) => { const next = (event as CustomEvent<AppLocale>).detail; if (isSupportedLocale(next)) setLocale(next); };
    window.addEventListener("hitrendy:locale", onLocale);
    return () => window.removeEventListener("hitrendy:locale", onLocale);
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    void api.projects
      .list({ status })
      .then((items) => setProjects(items as unknown as ProjectItem[]))
      .catch((reason) =>
        setError(
          reason instanceof ApiError
            ? reason.message
            : initialProjectError.current
        )
      )
      .finally(() => setLoading(false));
  }, [status]);

  useEffect(() => {
    void api.templates
      .list()
      .then((items) => setTemplates(items as unknown as Template[]))
      .catch(() => undefined);
  }, []);

  // The recommender reads the business profile, so it can only run once the
  // catalogue is in: that catalogue is also the fallback when the workspace has
  // no platform or objective set yet, or when the recommendation call fails.
  useEffect(() => {
    if (!templates.length) return;
    let active = true;

    async function loadRecommendations() {
      let targeting = {
        platform: null as string | null,
        objective: null as string | null,
      };
      try {
        const businesses = await api.businesses.list();
        targeting = readBusinessTargeting(businesses[0]);
      } catch {
        // No profile reachable: the catalogue fallback still fills the rail.
      }

      const items = await loadRecommendedTemplates({
        platform: targeting.platform,
        objective: targeting.objective,
        // Six is the ceiling the recommendations endpoint accepts; asking for
        // more is a 422, which would silently demote every visitor to the
        // plain catalogue.
        limit: 6,
        fallback: templates,
      });
      if (active) setRecommended(items);
    }

    void loadRecommendations();
    return () => {
      active = false;
    };
  }, [templates]);

  const heroCovers = useMemo(() => {
    // Canva entries carry no bitmap; the rail renders images only, so they are
    // skipped and the seeded covers take over when fewer than three remain.
    const covers = templates
      .slice(0, 3)
      .map((template) => toTemplatePresentation(template).thumbnail_url)
      .filter((cover): cover is string => Boolean(cover));
    return covers.length === 3 ? covers : HERO_FALLBACK_COVERS;
  }, [templates]);

  const carouselItems = useMemo(() => {
    const whyPrefix = surfaceCopy[locale].templates.whyPrefix;
    return recommended.flatMap((template) => {
      const presentation = toTemplatePresentation(template);
      // The carousel card can only show a bitmap, and Canva entries have none.
      if (!presentation.thumbnail_url) return [];
      return {
        id: presentation.id,
        title: presentation.title,
        thumbnailUrl: presentation.thumbnail_url,
        aspectRatio: presentation.aspectRatio,
        badge: presentation.displayCategory,
        // Only the recommender explains itself; catalogue fallbacks carry no
        // rationale and must not be dressed up as if they did.
        reason: template.rationale
          ? `${whyPrefix}: ${template.rationale}`
          : undefined,
      };
    });
  }, [locale, recommended]);

  const filteredProjects = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("es");
    return normalized
      ? projects.filter((project) =>
          `${project.name} ${project.platform}`
            .toLocaleLowerCase("es")
            .includes(normalized)
        )
      : projects;
  }, [projects, query]);

  async function changeStatus(project: ProjectItem) {
    setBusyId(project.id);
    try {
      await api.projects.update(project.id, {
        status: project.status === "active" ? "archived" : "active",
      });
      setProjects((items) => items.filter((item) => item.id !== project.id));
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : translate(locale, "dashboard.updateError")
      );
    } finally {
      setBusyId(null);
    }
  }

  async function useTemplate(template: Template) {
    router.push(`/studio/new?template=${encodeURIComponent(template.id)}`);
  }

  function startTemplate(templateId: string) {
    setStartingId(templateId);
    router.push(`/studio/new?template=${encodeURIComponent(templateId)}`);
  }

  return (
    <AppShell>
      <main className="app-page dashboard-page">
        <header className="dashboard-head">
          <div>
            <p className="eyebrow">{copy.dashboard.eyebrow}</p>
            <h1>{copy.dashboard.title}</h1>
            <p>{copy.dashboard.subtitle}</p>
          </div>
          <div
            className="dashboard-tabs"
            role="tablist"
            aria-label={copy.dashboard.tabsLabel}
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === "projects"}
              onClick={() => setView("projects")}
            >
              {copy.dashboard.projects}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "templates"}
              onClick={() => setView("templates")}
            >
              {copy.dashboard.templates}
            </button>
          </div>
        </header>
        <section className="dashboard-hero">
          <div className="dashboard-hero-rail" aria-hidden="true">
            {heroCovers.map((cover) => (
              <Image key={cover} src={cover} alt="" width={92} height={122} />
            ))}
          </div>
          <p className="eyebrow">{copy.dashboard.startEyebrow}</p>
          <h2>
            {view === "projects"
              ? copy.dashboard.projectsHeadline
              : copy.dashboard.templatesHeadline}
          </h2>
          <p>
            {view === "projects"
              ? copy.dashboard.projectsLead
              : copy.dashboard.templatesLead}
          </p>
          <Link href={routes.studioNew} className="button-secondary">
            {copy.dashboard.createCta} <span aria-hidden="true">→</span>
          </Link>
        </section>
        {view === "templates" ? (
          <TemplateLibrary templates={templates} onUse={useTemplate} copy={surfaceCopy[locale].templates} />
        ) : (
          <>
            <div className="content-title dashboard-project-title"><h2>{copy.dashboard.yourProjects}</h2></div>
            <div className="dashboard-toolbar">
              <div role="tablist" aria-label={copy.dashboard.statusLabel}>
                {(["active", "archived"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={status === value}
                    className="filter-tab"
                    onClick={() => setStatus(value)}
                  >
                    {value === "active"
                      ? copy.dashboard.statusActive
                      : copy.dashboard.statusArchived}
                  </button>
                ))}
              </div>
              <label className="search-field" htmlFor="project-search">
                {copy.dashboard.search}
                <input
                  id="project-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={copy.dashboard.searchPlaceholder}
                />
              </label>
            </div>
            {error ? (
              <p className="page-error" role="alert">
                {error}
              </p>
            ) : null}
            {loading ? (
              <div className="folder-grid" aria-label={copy.dashboard.loadingProjects}>
                {[0, 1, 2].map((index) => (
                  <article
                    className="folder-card folder-card--loading"
                    key={index}
                  >
                    <span className="skeleton-line" />
                    <span className="skeleton-line skeleton-line--short" />
                  </article>
                ))}
              </div>
            ) : null}
            {!loading && !error && filteredProjects.length === 0 ? (
              <section className="empty-state">
                <h2>
                  {projects.length
                    ? copy.dashboard.noResults
                    : status === "archived"
                      ? copy.dashboard.emptyArchived
                      : copy.dashboard.emptyActive}
                </h2>
                <p>
                  {projects.length
                    ? copy.dashboard.noResultsHint
                    : copy.dashboard.emptyHint}
                </p>
                {!projects.length ? (
                  <Link href={routes.templates} className="button-primary">
                    {copy.dashboard.startCta}
                  </Link>
                ) : null}
              </section>
            ) : null}
            <div className="projects-glass-container">
              <section className="folder-grid" aria-label={copy.dashboard.projectsList}>
                {filteredProjects.map((project, index) => (
                  <ProjectFolderCard
                    key={project.id}
                    project={project}
                    variant={index % 2 === 0 ? "blue" : "purple"}
                    locale={locale}
                    isBusy={busyId === project.id}
                    onStatusChange={changeStatus}
                  />
                ))}
                <NewProjectFolderCard locale={locale} />
              </section>
            </div>
            <section className="dashboard-recommended">
              <div className="content-title">
                <h2>{copy.dashboard.recommended}</h2>
                <Link href={routes.templates}>{copy.dashboard.seeAll}</Link>
              </div>
              <TemplateCarousel
                items={carouselItems}
                label={surfaceCopy[locale].templates.carousel}
                useLabel={surfaceCopy[locale].templates.use}
                busyLabel={surfaceCopy[locale].templates.preparing}
                previousLabel={surfaceCopy[locale].templates.previous}
                nextLabel={surfaceCopy[locale].templates.next}
                onSelect={startTemplate}
                busyId={startingId}
              />
            </section>
          </>
        )}
      </main>
    </AppShell>
  );
}
