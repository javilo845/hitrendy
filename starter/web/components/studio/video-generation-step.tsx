"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, createIdempotencyKey } from "@/lib/api";
import type { instagramFlowCopy } from "@/lib/instagram-flow-copy";
import {
  isTerminalVideoJob,
  videoAspectRatios,
  videoShotFields,
  videoStoryboardLimits,
  type VideoAspectRatio,
  type VideoBudget,
  type VideoCapabilityState,
  type VideoJob,
  type VideoPreflight,
  type VideoShot,
  type VideoSourceImage,
  type VideoStoryboard,
} from "@/types/videos";

export type VideoStepCopy = (typeof instagramFlowCopy)["es"]["video"];

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 60;
const usableStatuses = new Set(["available", "degraded"]);

export interface VideoGenerationStepProps {
  businessId: string;
  copy: VideoStepCopy;
  publicationText?: string;
  trendTitle?: string;
  projectId?: string | null;
}

type VideoShotField = (typeof videoShotFields)[number];

function emptyStoryboard(): VideoStoryboard {
  return {
    hook: "",
    duration_seconds: 5,
    aspect_ratio: videoAspectRatios[0],
    voiceover: "",
    music_direction: "",
    shots: [],
  };
}

function reasonText(copy: VideoStepCopy, code: string | null | undefined): string {
  if (!code) return copy.reason.error;
  return copy.reason[code as keyof VideoStepCopy["reason"]] ?? copy.reason.error;
}

function statusText(copy: VideoStepCopy, status: VideoJob["status"]): string {
  return copy.status[status as keyof VideoStepCopy["status"]] ?? copy.status.execution_unknown;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toLocaleString();
}

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match
  );
}

function shotLabel(copy: VideoStepCopy, field: VideoShotField): string {
  switch (field) {
    case "visual":
      return copy.visual;
    case "camera":
      return copy.camera;
    case "on_screen_text":
      return copy.on_screen_text;
    case "voiceover":
      return copy.shot_voiceover;
    case "transition":
      return copy.transition;
  }
}

function shotLimit(field: VideoShotField): number {
  if (field === "voiceover") return videoStoryboardLimits.shot_voiceover;
  return videoStoryboardLimits[field];
}

function sourceLabel(
  copy: VideoStepCopy,
  sources: VideoSourceImage[],
  id: string | null | undefined
): string {
  if (!id) return copy.sourceNone;
  const position = sources.findIndex((source) => source.id === id);
  return position < 0
    ? copy.sourceNone
    : fill(copy.sourceImageOption, { number: position + 1 });
}

function capabilityText(copy: VideoStepCopy, status: VideoCapabilityState["status"]): string {
  if (status === "available") return copy.capabilityAvailable;
  if (status === "degraded") return copy.capabilityDegraded;
  return reasonText(copy, status);
}

/** Keep backend error codes out of the UI while still giving known safe codes a useful translation. */
function safeErrorText(copy: VideoStepCopy, job: VideoJob): string {
  if (job.safe_error) return job.safe_error;
  const code = job.safe_error_code?.toLowerCase() ?? "";
  if (code.includes("quota")) return copy.reason.quota_exhausted;
  if (code.includes("disabled")) return copy.reason.disabled;
  if (code.includes("restricted")) return copy.reason.restricted;
  if (code.includes("payment")) return copy.reason.payment_required;
  return copy.safeErrorFallback;
}

function isExpired(value: string | null): boolean {
  if (!value) return false;
  const timestamp = Date.parse(value);
  return !Number.isNaN(timestamp) && timestamp <= Date.now();
}

/**
 * Video generation is deliberately a sibling of the image step: the
 * storyboard is always editable, while an actual job requires a fresh
 * preflight and an explicit confirmation tied to a saved project.
 */
export function VideoGenerationStep({
  businessId,
  copy,
  publicationText,
  trendTitle,
  projectId,
}: VideoGenerationStepProps) {
  const [storyboard, setStoryboard] = useState<VideoStoryboard>(emptyStoryboard);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [allowedDurations, setAllowedDurations] = useState<number[]>([]);
  const [aspectRatio, setAspectRatio] = useState<VideoAspectRatio>(videoAspectRatios[0]);
  const [capability, setCapability] = useState<VideoCapabilityState | null>(null);
  const [budget, setBudget] = useState<VideoBudget | null>(null);
  const [sourceImages, setSourceImages] = useState<VideoSourceImage[]>([]);
  const [sourceAssetId, setSourceAssetId] = useState("");
  const [preflight, setPreflight] = useState<VideoPreflight | null>(null);
  const [stale, setStale] = useState(false);
  const [job, setJob] = useState<VideoJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [checking, setChecking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [polling, setPolling] = useState(false);
  const [refreshingVideo, setRefreshingVideo] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState("");
  const attemptsRef = useRef(0);
  const confirmRef = useRef(false);
  const jobKeyRef = useRef<string | null>(null);
  const refreshingVideoRef = useRef(false);
  const refreshSignatureRef = useRef("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    // Two free reads. Neither reaches a provider and neither spends anything.
    void Promise.all([
      api.videos.draftStoryboard({
        business_id: businessId,
        publication_text: publicationText,
        trend_title: trendTitle,
      }),
      api.assets.list().catch(() => [] as Array<Record<string, unknown>>),
    ])
      .then(([draft, assets]) => {
        if (!active) return;
        const nextDurations = [...draft.allowed_durations];
        if (nextDurations.length === 0) {
          throw new Error("El servidor no ofreció duraciones de video.");
        }
        const nextDuration = nextDurations.includes(draft.storyboard.duration_seconds)
          ? draft.storyboard.duration_seconds
          : nextDurations[0];
        setStoryboard({
          ...emptyStoryboard(),
          ...draft.storyboard,
          duration_seconds: nextDuration,
          aspect_ratio: draft.aspect_ratio,
        });
        setPrompt(draft.prompt_preview);
        setNegativePrompt(draft.negative_prompt_preview);
        setDuration(nextDuration);
        setAllowedDurations(nextDurations);
        setAspectRatio(draft.aspect_ratio);
        setCapability(draft.capability);
        setBudget(draft.budget);
        setSourceImages(
          assets
            .filter((asset) => asset.asset_type === "image" && typeof asset.id === "string")
            .map((asset) => ({
              id: asset.id as string,
              url: typeof asset.url === "string" ? asset.url : null,
              created_at: typeof asset.created_at === "string" ? asset.created_at : "",
            }))
        );
      })
      .catch((reason) => {
        if (active) setError(reason instanceof ApiError ? reason.message : copy.storyboardError);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // The storyboard is drafted once per post; later edits stay local.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId]);

  useEffect(() => {
    if (!projectId) return;
    let active = true;
    setRecovering(true);
    void api.videos
      .latestJob(projectId)
      .then((existing) => {
        if (!active || !existing) return;
        attemptsRef.current = 0;
        setExhausted(false);
        setJob(existing);
        setRecovered(true);
      })
      // Recovery is read-only. A failed read should not block a new preflight.
      .catch(() => undefined)
      .finally(() => active && setRecovering(false));
    return () => {
      active = false;
    };
  }, [projectId]);

  /** Any generation input change retires the approval signed for the old input. */
  const invalidate = useCallback(() => {
    setPreflight(null);
    setStale(true);
  }, []);

  function updateStoryboard(field: "hook" | "voiceover" | "music_direction", value: string) {
    setStoryboard((current) => ({ ...current, [field]: value }));
    invalidate();
  }

  function updateShot(index: number, field: VideoShotField, value: string) {
    setStoryboard((current) => ({
      ...current,
      shots: current.shots.map((shot, shotIndex) =>
        shotIndex === index ? { ...shot, [field]: value } : shot
      ),
    }));
    invalidate();
  }

  function chooseDuration(value: number) {
    if (!allowedDurations.includes(value)) return;
    setDuration(value);
    setStoryboard((current) => ({ ...current, duration_seconds: value }));
    invalidate();
  }

  function chooseSource(value: string) {
    setSourceAssetId(value);
    invalidate();
  }

  const readJob = useCallback(async (id: string) => {
    const next = await api.videos.job(id);
    setJob(next);
    return next;
  }, []);

  const requestFreshVideo = useCallback(
    async (current: VideoJob) => {
      if (!current.video_url || refreshingVideoRef.current) return;
      const signature = `${current.id}:${current.video_url}:${current.video_expires_at ?? ""}`;
      if (refreshSignatureRef.current === signature) return;
      refreshSignatureRef.current = signature;
      refreshingVideoRef.current = true;
      setRefreshingVideo(true);
      setError("");
      try {
        const next = await readJob(current.id);
        if (next.status !== "succeeded") {
          setError(safeErrorText(copy, next));
        } else if (!next.video_url) {
          setError(copy.noVideo);
        }
      } catch (reason) {
        setError(reason instanceof ApiError ? reason.message : copy.statusError);
      } finally {
        refreshingVideoRef.current = false;
        setRefreshingVideo(false);
      }
    },
    [copy, readJob]
  );

  useEffect(() => {
    if (!job || job.status !== "succeeded" || !job.video_url || !isExpired(job.video_expires_at)) {
      return;
    }
    void requestFreshVideo(job);
  }, [job, requestFreshVideo]);

  useEffect(() => {
    if (!job || isTerminalVideoJob(job.status)) {
      setPolling(false);
      return;
    }
    if (attemptsRef.current >= MAX_POLL_ATTEMPTS) {
      setPolling(false);
      setExhausted(true);
      return;
    }
    let cancelled = false;
    setPolling(true);
    const timer = setTimeout(() => {
      if (cancelled) return;
      attemptsRef.current += 1;
      void readJob(job.id).catch((reason) => {
        if (cancelled) return;
        setPolling(false);
        setError(reason instanceof ApiError ? reason.message : copy.statusError);
      });
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [job, readJob, copy.statusError]);

  async function runPreflight() {
    if (loading || checking || active) return;
    setChecking(true);
    setError("");
    try {
      const result = await api.videos.preflight({
        storyboard,
        prompt,
        negative_prompt: negativePrompt.trim() || null,
        duration_seconds: duration,
        source_asset_id: sourceAssetId || null,
        project_id: projectId,
      });
      setPreflight(result);
      setStoryboard(result.storyboard);
      setPrompt(result.prompt_preview);
      setNegativePrompt(result.negative_prompt_preview);
      setDuration(result.duration_seconds);
      setAspectRatio(result.aspect_ratio);
      setCapability(result.capability);
      setBudget(result.budget);
      setStale(false);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.preflightError);
    } finally {
      setChecking(false);
    }
  }

  async function confirm() {
    // Without a durable project there is nowhere honest to recover a paid job.
    if (!projectId) return;
    if (
      !preflight?.allowed ||
      !preflight.approval_token ||
      stale ||
      blocked ||
      confirmRef.current
    ) {
      return;
    }
    confirmRef.current = true;
    setConfirming(true);
    setError("");
    try {
      jobKeyRef.current ??= createIdempotencyKey();
      const created = await api.videos.createJob(
        {
          storyboard: preflight.storyboard,
          prompt: preflight.prompt_preview,
          negative_prompt: preflight.negative_prompt_preview || null,
          duration_seconds: preflight.duration_seconds,
          source_asset_id: preflight.source_asset_id,
          project_id: projectId,
          confirmed: true,
          approval_token: preflight.approval_token,
        },
        { idempotencyKey: jobKeyRef.current }
      );
      attemptsRef.current = 0;
      refreshSignatureRef.current = "";
      setExhausted(false);
      setRecovered(false);
      setJob(created);
      setPreflight(null);
      setStale(false);
    } catch (reason) {
      jobKeyRef.current = null;
      setError(reason instanceof ApiError ? reason.message : copy.confirmError);
    } finally {
      confirmRef.current = false;
      setConfirming(false);
    }
  }

  async function checkStatus() {
    if (!job || checking) return;
    setChecking(true);
    setError("");
    try {
      attemptsRef.current = 0;
      refreshSignatureRef.current = "";
      setExhausted(false);
      await readJob(job.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.statusError);
    } finally {
      setChecking(false);
    }
  }

  /** A retry is manual and starts a fresh preflight/key cycle. */
  function retry() {
    jobKeyRef.current = null;
    attemptsRef.current = 0;
    refreshSignatureRef.current = "";
    setJob(null);
    setPreflight(null);
    setExhausted(false);
    setRecovered(false);
    setStale(false);
    setError("");
    void runPreflight();
  }

  const status = capability?.status;
  const usable = Boolean(status && usableStatuses.has(status));
  const budgetSpent = Boolean(budget && budget.remaining <= 0);
  const blocked = !usable || budgetSpent;
  const blockedReason = budgetSpent && usable ? "quota_exhausted" : status;
  const active = Boolean(job && !isTerminalVideoJob(job.status));
  const videoVisible = Boolean(
    job?.status === "succeeded" && job.video_url && !isExpired(job.video_expires_at)
  );

  return (
    <section className="video-step" aria-busy={loading || confirming || polling || refreshingVideo}>
      <div>
        <h2>{copy.heading}</h2>
        <p>{copy.intro}</p>
      </div>

      {error ? (
        <p className="page-error" role="alert">
          {error}
        </p>
      ) : null}

      {recovering ? <p role="status">{copy.recovering}</p> : null}

      {loading ? (
        <p role="status">{copy.storyboardLoading}</p>
      ) : (
        <>
          <fieldset className="video-storyboard">
            <legend>{copy.storyboardHeading}</legend>
            <label htmlFor="video-hook">
              {copy.hook}
              <textarea
                id="video-hook"
                value={storyboard.hook}
                onChange={(event) => updateStoryboard("hook", event.target.value)}
                maxLength={videoStoryboardLimits.hook}
              />
            </label>
            <label htmlFor="video-voiceover">
              {copy.voiceover}
              <textarea
                id="video-voiceover"
                value={storyboard.voiceover}
                onChange={(event) => updateStoryboard("voiceover", event.target.value)}
                maxLength={videoStoryboardLimits.voiceover}
              />
            </label>
            <label htmlFor="video-music-direction">
              {copy.music_direction}
              <textarea
                id="video-music-direction"
                value={storyboard.music_direction}
                onChange={(event) => updateStoryboard("music_direction", event.target.value)}
                maxLength={videoStoryboardLimits.music_direction}
              />
            </label>

            <div className="video-shots">
              <h3>{copy.shotsHeading}</h3>
              {storyboard.shots.length ? (
                storyboard.shots.map((shot: VideoShot, index) => (
                  <fieldset className="video-shot" key={`${shot.order}-${index}`}>
                    <legend>{fill(copy.shotLabel, { number: shot.order })}</legend>
                    {videoShotFields.map((field) => (
                      <label key={field} htmlFor={`video-shot-${index}-${field}`}>
                        {shotLabel(copy, field)}
                        <textarea
                          id={`video-shot-${index}-${field}`}
                          value={shot[field]}
                          onChange={(event) => updateShot(index, field, event.target.value)}
                          maxLength={shotLimit(field)}
                        />
                      </label>
                    ))}
                  </fieldset>
                ))
              ) : (
                <p role="status">{copy.storyboardEmpty}</p>
              )}
            </div>
          </fieldset>

          <fieldset className="video-prompts">
            <legend>{copy.promptHeading}</legend>
            <label htmlFor="video-prompt">
              {copy.promptHeading}
              <textarea
                id="video-prompt"
                value={prompt}
                onChange={(event) => {
                  setPrompt(event.target.value);
                  invalidate();
                }}
                maxLength={4000}
              />
            </label>
            <label htmlFor="video-negative-prompt">
              {copy.negativePromptHeading}
              <textarea
                id="video-negative-prompt"
                value={negativePrompt}
                onChange={(event) => {
                  setNegativePrompt(event.target.value);
                  invalidate();
                }}
                maxLength={600}
              />
            </label>
          </fieldset>

          <fieldset className="video-durations">
            <legend>{copy.durationHeading}</legend>
            <p id="video-duration-hint">{copy.durationHint}</p>
            <div
              role="radiogroup"
              aria-label={copy.durationHeading}
              aria-describedby="video-duration-hint"
            >
              {allowedDurations.map((value, index) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={duration === value}
                  tabIndex={duration === value ? 0 : -1}
                  data-selected={duration === value}
                  onClick={() => chooseDuration(value)}
                  onKeyDown={(event) => {
                    const nextIndex =
                      event.key === "ArrowRight" || event.key === "ArrowDown"
                        ? (index + 1) % allowedDurations.length
                        : event.key === "ArrowLeft" || event.key === "ArrowUp"
                          ? (index - 1 + allowedDurations.length) % allowedDurations.length
                          : event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? allowedDurations.length - 1
                              : null;
                    if (nextIndex === null) return;
                    event.preventDefault();
                    chooseDuration(allowedDurations[nextIndex]);
                  }}
                >
                  {copy.durationLabels[value as keyof typeof copy.durationLabels] ??
                    `${value} segundos`}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="video-source">
            <label htmlFor="video-source-select">{copy.sourceHeading}</label>
            <select
              id="video-source-select"
              value={sourceAssetId}
              aria-describedby="video-source-hint"
              onChange={(event) => chooseSource(event.target.value)}
            >
              <option value="">{copy.sourceNone}</option>
              {sourceImages.map((source, index) => (
                <option key={source.id} value={source.id}>
                  {fill(copy.sourceImageOption, { number: index + 1 })}
                </option>
              ))}
            </select>
            <small id="video-source-hint">{copy.sourceHint}</small>
          </div>

          {blocked ? (
            <div className="video-fallback" role="status">
              <h3>{copy.fallbackHeading}</h3>
              <p>{reasonText(copy, blockedReason)}</p>
              <p>{copy.fallbackHint}</p>
              <button type="button" className="button-primary" disabled>
                {copy.confirm}
              </button>
            </div>
          ) : (
            <div className="video-actions">
              {stale ? <p role="status">{copy.editedAfterPreflight}</p> : null}
              {projectId ? null : <p role="status">{copy.savePostFirst}</p>}
              <button
                type="button"
                onClick={() => void runPreflight()}
                disabled={checking || confirming || active}
              >
                {checking ? copy.preflighting : copy.preflight}
              </button>
            </div>
          )}

          {preflight ? (
            <div className="video-preflight">
              <h3>{copy.preflightHeading}</h3>
              <div className="video-summary">
                <p>
                  <strong>{copy.formatSummary}:</strong>{" "}
                  <span data-aspect-ratio={aspectRatio}>{copy.formatLabel}</span>
                </p>
                <p>
                  <strong>{copy.durationSummary}:</strong>{" "}
                  {copy.durationLabels[
                    preflight.duration_seconds as keyof typeof copy.durationLabels
                  ] ?? `${preflight.duration_seconds} segundos`}
                </p>
                <p>
                  <strong>{copy.sourceSummary}:</strong>{" "}
                  {sourceLabel(copy, sourceImages, preflight.source_asset_id)}
                </p>
                <p>
                  <strong>{copy.costHeading}:</strong>{" "}
                  {fill(copy.costValue, { units: preflight.estimated_units })}
                </p>
                <p>
                  <strong>{copy.budget}:</strong>{" "}
                  {fill(copy.budgetValue, {
                    remaining: preflight.budget.remaining,
                    total: preflight.budget.total,
                  })}
                </p>
                <p>
                  {fill(copy.budgetReset, { date: formatDate(preflight.budget.next_reset_at) })}
                </p>
                <p>
                  <strong>{copy.capabilityHeading}:</strong>{" "}
                  {capabilityText(copy, preflight.capability.status)}
                </p>
              </div>

              <label htmlFor="video-preflight-prompt">
                {copy.promptPreview}
                <textarea
                  id="video-preflight-prompt"
                  value={preflight.prompt_preview}
                  readOnly
                />
              </label>
              <label htmlFor="video-preflight-negative-prompt">
                {copy.negativePromptPreview}
                <textarea
                  id="video-preflight-negative-prompt"
                  value={preflight.negative_prompt_preview || copy.negativePromptNone}
                  readOnly
                />
              </label>

              <div className="video-storyboard-preview">
                <h4>{copy.storyboardPreview}</h4>
                <p>
                  <strong>{copy.hook}:</strong> {preflight.storyboard.hook}
                </p>
                <p>
                  <strong>{copy.voiceover}:</strong> {preflight.storyboard.voiceover}
                </p>
                <p>
                  <strong>{copy.music_direction}:</strong> {preflight.storyboard.music_direction}
                </p>
                {preflight.storyboard.shots.map((shot) => (
                  <div key={shot.order}>
                    <strong>{fill(copy.shotLabel, { number: shot.order })}</strong>
                    <p>
                      <strong>{copy.visual}:</strong> {shot.visual}
                    </p>
                    <p>
                      <strong>{copy.camera}:</strong> {shot.camera}
                    </p>
                    <p>
                      <strong>{copy.on_screen_text}:</strong> {shot.on_screen_text}
                    </p>
                    <p>
                      <strong>{copy.shot_voiceover}:</strong> {shot.voiceover}
                    </p>
                    <p>
                      <strong>{copy.transition}:</strong> {shot.transition}
                    </p>
                  </div>
                ))}
              </div>

              {preflight.allowed ? (
                <>
                  <p>{copy.confirmHint}</p>
                  <button
                    type="button"
                    className="button-primary"
                    onClick={() => void confirm()}
                    disabled={confirming || !projectId || stale || blocked}
                  >
                    {confirming ? copy.confirming : copy.confirm}
                  </button>
                </>
              ) : (
                <p role="status">
                  {preflight.message || reasonText(copy, preflight.reason_code)}
                </p>
              )}
            </div>
          ) : null}

          {job ? (
            <div className="video-job">
              <h3>{copy.statusHeading}</h3>
              {recovered ? <p role="status">{copy.recovered}</p> : null}
              <p role="status" aria-live="polite">
                {statusText(copy, job.status)}
              </p>
              {job.safe_error || job.safe_error_code ? (
                <p className="page-error" role="alert">
                  {safeErrorText(copy, job)}
                </p>
              ) : null}
              {exhausted && active ? <p role="status">{copy.pollTimeout}</p> : null}
              {job.status === "succeeded" ? (
                videoVisible ? (
                  <video
                    controls
                    playsInline
                    className="video-result"
                    src={job.video_url ?? undefined}
                    aria-label={copy.videoAlt}
                    onError={() => void requestFreshVideo(job)}
                  />
                ) : (
                  <p role="status">
                    {refreshingVideo ? copy.refreshingLink : copy.noVideo}
                  </p>
                )
              ) : null}
              {job.status === "succeeded" && job.video_url ? (
                <small>{copy.linkExpires}</small>
              ) : null}
              <div className="video-job-actions">
                {active ? (
                  <button type="button" onClick={() => void checkStatus()} disabled={checking}>
                    {copy.checkStatus}
                  </button>
                ) : null}
                {job.status === "succeeded" ? (
                  <button
                    type="button"
                    onClick={() => void checkStatus()}
                    disabled={checking || refreshingVideo}
                  >
                    {copy.refreshLink}
                  </button>
                ) : null}
                {job.status === "failed" ||
                job.status === "cancelled" ||
                job.status === "execution_unknown" ? (
                  <button type="button" onClick={retry} disabled={checking || blocked}>
                    {copy.retry}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
