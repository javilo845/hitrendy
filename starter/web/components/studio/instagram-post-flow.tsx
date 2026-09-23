"use client";

import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { ImageGenerationStep } from "@/components/studio/image-generation-step";
import { VideoGenerationStep } from "@/components/studio/video-generation-step";
import { ApiError, api, createIdempotencyKey } from "@/lib/api";
import { instagramFlowCopy, type InstagramFlowLocale } from "@/lib/instagram-flow-copy";
import { useInterfaceLocale } from "@/lib/i18n";
import { trendsCopy } from "@/lib/trends-copy";
import type { GeneratedSocialPost } from "@/types/artifact";
import type { BrandProfile } from "@/types/brand";
import type { BusinessProfile, Objective } from "@/types/business";
import type { QualityLevel } from "@/types/capabilities";
import type { Template } from "@/types/template";
import type { TrendDetail } from "@/types/trends";

const objectives: Objective[] = ["engagement", "sales", "reach", "store_visits", "launch", "brand_awareness", "community"];
const allowedCanvaUrls = new Set(["https://canva.link/jxr6r3xdtdx3p18", "https://canva.link/d5gnf0tsot7t70m", "https://canva.link/2hk1wscap0jikce", "https://canva.link/9667338l5l4mgwg", "https://canva.link/7ped4en1xal5yk7"]);

export function isApprovedCanvaUrl(url: string | undefined) {
  return typeof url === "string" && allowedCanvaUrls.has(url);
}

type EditablePost = Pick<GeneratedSocialPost, "caption" | "call_to_action" | "hashtags" | "visual_direction">;
type StoredProject = { id: string; artifact_id?: string; source_template_id?: string; artifact_snapshot?: GeneratedSocialPost };

function editable(post: GeneratedSocialPost): EditablePost {
  return { caption: post.caption, call_to_action: post.call_to_action, hashtags: post.hashtags, visual_direction: post.visual_direction };
}

export function validateInstagramDraft(draft: EditablePost, copy: typeof instagramFlowCopy.es) {
  if (!draft.caption.trim() || draft.caption.length > 2200) return copy.validationCaption;
  if (!draft.visual_direction.trim() || draft.visual_direction.length > 700) return copy.validationVisual;
  if (!draft.call_to_action.trim() || draft.call_to_action.length > 240) return copy.validationCta;
  if (draft.hashtags.length < 1 || draft.hashtags.length > 5 || draft.hashtags.some((tag) => !tag.trim() || tag.length > 100)) return copy.validationHashtags;
  return "";
}

export function InstagramPostFlow() {
  const router = useRouter();
  const interfaceLocale = useInterfaceLocale();
  const searchParams = useSearchParams();
  const requestedProjectId = searchParams.get("project");
  const requestedTrendId = searchParams.get("trend");
  /**
   * Opening a folder is a request for a new brief, not for the saved draft:
   * the project travels as context — its template and its topic — while the
   * form stays open so the next generation is a new post. Without the flag the
   * same link still reopens the stored version, which is what saving needs.
   */
  const briefMode = searchParams.get("brief") === "1";
  const operationRef = useRef(false);
  const saveRef = useRef(false);
  const duplicateRef = useRef(false);
  const saveKeyRef = useRef<string | null>(null);
  const duplicateKeyRef = useRef<string | null>(null);
  const flowKeyRef = useRef(createIdempotencyKey());
  const [locale, setLocale] = useState<InstagramFlowLocale>("es");
  const copy = instagramFlowCopy[locale];
  const [business, setBusiness] = useState<BusinessProfile | null>(null);
  const [brand, setBrand] = useState<BrandProfile | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);
  const [levels, setLevels] = useState<QualityLevel[]>([]);
  const [quality, setQuality] = useState<QualityLevel>("fast");
  const [objective, setObjective] = useState<Objective>("engagement");
  const [theme, setTheme] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [artifact, setArtifact] = useState<GeneratedSocialPost | null>(null);
  const [generated, setGenerated] = useState<EditablePost | null>(null);
  const [draft, setDraft] = useState<EditablePost | null>(null);
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(briefMode ? null : requestedProjectId);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [trendContext, setTrendContext] = useState<TrendDetail | null>(null);
  const isDirty = useMemo(() => Boolean(draft && generated && JSON.stringify(draft) !== JSON.stringify(generated)), [draft, generated]);

  useEffect(() => {
    setLocale(interfaceLocale);
  }, [interfaceLocale]);

  useEffect(() => {
    function warn(event: BeforeUnloadEvent) {
      if (isDirty) { event.preventDefault(); event.returnValue = ""; }
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.businesses.list(),
      api.templates.list({ platform: "instagram", format: "static_post" }),
      api.capabilities.get(),
      requestedProjectId ? api.projects.get(requestedProjectId) : Promise.resolve(null),
      requestedTrendId ? api.trends.detail(requestedTrendId) : Promise.resolve(null),
    ])
      .then(async ([businesses, items, capabilities, stored, observedTrend]) => {
        if (!active) return;
        const first = businesses[0] as unknown as BusinessProfile | undefined;
        if (!first) throw new ApiError(400, "NO_BUSINESS", copy.noBusiness, false);
        const approved = (items as unknown as Template[]).filter((item) => item.aspect_ratio === "4:5" && isApprovedCanvaUrl(item.canva_url));
        const context = await api.businesses.brandProfile.get(first.id) as unknown as BrandProfile;
        if (!active) return;
        setBusiness(first); setBrand(context); setTemplates(approved);
        const available = capabilities.copywriter?.quality_levels || [];
        setLevels(available); setQuality(available.includes("fast") ? "fast" : available[0] || "fast");
        const project = stored as unknown as StoredProject | null;
        const trend = observedTrend as TrendDetail | null;
        if (trend) {
          setTrendContext(trend);
          setTheme(
            `${trendsCopy[interfaceLocale].draftPrefix}: “${trend.title}”. ${trend.summary}`
          );
        }
        if (briefMode && project?.artifact_snapshot?.artifact_type === "social_post") {
          const post = project.artifact_snapshot;
          setSelected(approved.find((item) => item.id === project.source_template_id) || approved[0] || null);
          if (!trend) setTheme(`${copy.briefFromProject}: “${post.hook}”. ${post.caption}`.slice(0, 4000));
          const restart = await api.projects.startCreationFlow(first.id, { idempotencyKey: flowKeyRef.current });
          if (active) setFlowId(restart.id);
          return;
        }
        if (project?.artifact_snapshot?.artifact_type === "social_post") {
          const post = project.artifact_snapshot;
          setProjectId(project.id); setArtifactId(project.artifact_id || null); setArtifact(post); setGenerated(editable(post)); setDraft(editable(post));
          setSelected(approved.find((item) => item.id === project.source_template_id) || null);
          return;
        }
        setSelected(approved.find((item) => item.id === searchParams.get("template")) || approved[0] || null);
        const flow = await api.projects.startCreationFlow(first.id, { idempotencyKey: flowKeyRef.current });
        if (active) setFlowId(flow.id);
      })
      .catch((reason) => active && setError(reason instanceof ApiError ? reason.message : copy.noBusiness))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  // Reloading a saved project must not start another flow; all other source data loads once.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedProjectId, requestedTrendId, briefMode]);

  function updateDraft(field: keyof EditablePost, value: string) {
    setDraft((current) => current ? { ...current, [field]: field === "hashtags" ? value.split(",").map((tag) => tag.trim()) : value } : current);
  }

  async function markFlow(status: "generation_completed" | "completed" | "failed") {
    if (!flowId) return;
    try { await api.projects.completeCreationFlow(flowId, status); } catch { /* generation and draft remain usable */ }
  }

  async function generate() {
    if (!business || !selected || !theme.trim() || !levels.includes(quality) || operationRef.current) return;
    operationRef.current = true; setGenerating(true); setError(""); setNotice("");
    try {
      const conversation = await api.conversations.create({ business_id: business.id, title: selected.title });
      const id = conversation.id as string; setConversationId(id);
      const response = await api.conversations.sendMessage(id, `${theme.trim()} — usa la plantilla “${selected.title}” como referencia visual 4:5.`, "create_social_post", [], { idempotencyKey: createIdempotencyKey(), maxAttempts: 1 }, { platform: "instagram", objective, qualityLevel: quality, locale }) as { artifact?: GeneratedSocialPost; artifact_id?: string };
      if (!response.artifact || response.artifact.platform !== "instagram") throw new ApiError(502, "INVALID_RESPONSE", copy.invalidResponse, true);
      setArtifact(response.artifact); setGenerated(editable(response.artifact)); setDraft(editable(response.artifact)); setArtifactId(response.artifact_id || null);
      await markFlow("generation_completed");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.generationError);
      await markFlow("failed");
    } finally { operationRef.current = false; setGenerating(false); }
  }

  async function save() {
    const validation = draft ? validateInstagramDraft(draft, instagramFlowCopy.es as typeof instagramFlowCopy.es) : copy.validationCaption;
    if (!artifact || !draft || !artifactId || !selected || saving || saveRef.current || validation) { if (validation) setError(locale === "es" ? validation : validateInstagramDraft(draft!, copy as typeof instagramFlowCopy.es)); return; }
    saveRef.current = true; setSaving(true); setError("");
    try {
      let id = projectId;
      if (!id) {
        saveKeyRef.current ??= createIdempotencyKey();
        const project = await api.projects.create({ artifact_id: artifactId, template_id: selected.id }, { idempotencyKey: saveKeyRef.current });
        id = project.id as string; setProjectId(id);
      }
      if (isDirty) { await api.projects.updateArtifactVersion(id, { ...artifact, ...draft, format_recommendation: "static_post" }); setGenerated(draft); }
      await markFlow("completed"); setNotice(copy.saved); router.replace(`/studio/new?project=${id}`);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : copy.saveError); }
    finally { saveRef.current = false; setSaving(false); }
  }

  async function duplicate() {
    if (!projectId || duplicateRef.current) return;
    duplicateRef.current = true; setDuplicating(true); setError("");
    try { duplicateKeyRef.current ??= createIdempotencyKey(); const item = await api.projects.duplicate(projectId, { idempotencyKey: duplicateKeyRef.current }); router.push(`/studio/new?project=${item.id as string}`); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : copy.duplicateError); }
    finally { duplicateRef.current = false; setDuplicating(false); }
  }

  async function variation() {
    if (!conversationId || !artifactId || generating || operationRef.current) return;
    operationRef.current = true; setGenerating(true); setError("");
    try {
      const response = await api.artifacts.createVariation(conversationId, artifactId, "more_friendly", { idempotencyKey: createIdempotencyKey() }) as { artifact?: GeneratedSocialPost };
      if (!response.artifact) throw new ApiError(502, "INVALID_RESPONSE", copy.invalidResponse, true);
      setArtifact(response.artifact); setGenerated(editable(response.artifact)); setDraft(editable(response.artifact)); setNotice(copy.variationNotice);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : copy.variationError); }
    finally { operationRef.current = false; setGenerating(false); }
  }

  if (loading) return <div className="route-status" role="status">{copy.loading}</div>;
  return <main className="instagram-flow" aria-busy={generating || saving || duplicating}>
    <header><div><p className="eyebrow">INSTAGRAM 4:5</p><h1>{copy.title}</h1><p>{copy.subtitle}</p></div><label>{copy.locale}<select value={locale} onChange={(event) => setLocale(event.target.value as InstagramFlowLocale)}>{(["es", "en", "pt"] as const).map((item) => <option key={item} value={item}>{item.toUpperCase()}</option>)}</select></label></header>
    {error ? <p className="page-error" role="alert">{error}</p> : null}{notice ? <p className="flow-notice" role="status">{notice}</p> : null}
    <section><h2>{copy.template}</h2><div className="instagram-template-grid">{templates.map((template) => <article key={template.id} data-selected={selected?.id === template.id}><button type="button" onClick={() => setSelected(template)} aria-pressed={selected?.id === template.id}>{template.thumbnail_url ? <Image src={template.thumbnail_url} alt="" width={160} height={200} /> : null}<strong>{template.title}</strong><span>{copy.format}</span></button>{isApprovedCanvaUrl(template.canva_url) ? <button type="button" className="button-link" onClick={() => { const target = window.open(template.canva_url!, "_blank", "noopener,noreferrer"); if (target) target.opener = null; }}>{copy.openCanva}</button> : null}</article>)}</div></section>
    {trendContext ? <section className="flow-context trend-studio-context"><p className="eyebrow">{trendsCopy[locale].studioContext}</p><h2>{trendContext.title}</h2><p>{trendContext.summary}</p><small>{trendsCopy[locale].basedOnSignal}</small></section> : null}
    {/* A brand profile can come back without a voice yet, so the context block
        renders what exists instead of assuming every field is filled. */}
    {business && brand ? <section className="flow-context"><h2>{copy.context}</h2><p><strong>{business.name}</strong> · {business.primary_product} · {business.target_audience}</p><p>{[brand.value_proposition, (brand.voice_tones || []).join(", ")].filter(Boolean).join(" · ")}</p></section> : null}
    {!projectId ? <section className="flow-controls"><label>{copy.theme}<textarea value={theme} onChange={(event) => setTheme(event.target.value)} maxLength={4000} placeholder={copy.theme} /></label><label>{copy.quality}<select value={quality} onChange={(event) => setQuality(event.target.value as QualityLevel)}>{levels.map((level) => <option key={level} value={level}>{copy.qualityLabels[level]}</option>)}</select></label><label>{copy.objective}<select value={objective} onChange={(event) => setObjective(event.target.value as Objective)}>{objectives.map((item) => <option key={item} value={item}>{copy.objectiveLabels[item]}</option>)}</select></label><button type="button" className="button-primary" onClick={() => void generate()} disabled={!selected || !theme.trim() || !levels.includes(quality) || generating}>{generating ? copy.generating : copy.generate}</button></section> : null}
    {artifact && draft ? <section className="flow-result"><div><p className="eyebrow">{copy.result}</p><h2>{artifact.hook}</h2><span>{copy.format}</span></div><label>{copy.caption}<textarea value={draft.caption} onChange={(event) => updateDraft("caption", event.target.value)} maxLength={2200} /></label><label>{copy.cta}<input value={draft.call_to_action} onChange={(event) => updateDraft("call_to_action", event.target.value)} maxLength={240} /></label><label>{copy.hashtags}<input value={draft.hashtags.join(", ")} onChange={(event) => updateDraft("hashtags", event.target.value)} /></label><label>{copy.visualBrief}<textarea value={draft.visual_direction} onChange={(event) => updateDraft("visual_direction", event.target.value)} maxLength={700} /><small>{copy.visualNote}</small></label>{isDirty ? <p role="status">{copy.unsaved}</p> : null}<div className="flow-actions"><button type="button" className="button-primary" onClick={() => void save()} disabled={saving}>{saving ? copy.saving : copy.save}</button><button type="button" onClick={() => generated && setDraft(generated)}>{copy.restore}</button>{projectId ? <button type="button" onClick={() => void duplicate()} disabled={duplicating}>{duplicating ? copy.duplicating : copy.duplicate}</button> : null}<button type="button" onClick={() => void variation()} disabled={generating}>{copy.variation}</button></div></section> : null}
    {/* The image step only appears once there is a post to illustrate, and it
        starts nothing by itself: a trend or a caption is context, not a trigger. */}
    {artifact && draft && business ? <ImageGenerationStep businessId={business.id} copy={copy.image} publicationText={draft.caption} trendTitle={trendContext?.title} projectId={projectId} /> : null}
    {/* The video step only appears once there is a publication to turn into a
        storyboard, and it starts nothing by itself. */}
    {artifact && draft && business ? <VideoGenerationStep businessId={business.id} copy={copy.video} publicationText={draft.caption} trendTitle={trendContext?.title} projectId={projectId} /> : null}
  </main>;
}
