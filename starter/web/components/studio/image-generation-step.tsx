"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, createIdempotencyKey } from "@/lib/api";
import type { instagramFlowCopy } from "@/lib/instagram-flow-copy";
import {
  imageAspectRatios,
  isTerminalImageJob,
  visualBriefFields,
  visualBriefLimits,
  type ImageAspectRatio,
  type ImageBudget,
  type ImageCapabilityState,
  type ImageJob,
  type ImagePreflight,
  type ImageReference,
  type VisualBrief,
} from "@/types/images";

export type ImageStepCopy = (typeof instagramFlowCopy)["es"]["image"];

/**
 * How long we are willing to watch a job before handing control back.
 *
 * The job is durable on the server, so giving up here costs nothing: the user
 * keeps a button to ask again. Two seconds is slow enough not to hammer the
 * API and fast enough that a normal generation resolves without a manual step.
 */
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 45;

/** The states in which the server will actually accept a paid generation. */
const usableStatuses = new Set(["available", "degraded"]);

export interface ImageGenerationStepProps {
  businessId: string;
  copy: ImageStepCopy;
  /** The caption already written, used only to describe the scene. */
  publicationText?: string;
  /** The trend headline, when the post came from one. Context, never a trigger. */
  trendTitle?: string;
  projectId?: string | null;
}

function emptyBrief(): VisualBrief {
  return { subject: "", setting: "", style: "", palette: "", mood: "", avoid: "" };
}

function reasonText(copy: ImageStepCopy, code: string | null | undefined): string {
  if (!code) return copy.reason.error;
  return copy.reason[code as keyof ImageStepCopy["reason"]] ?? copy.reason.error;
}

function statusText(copy: ImageStepCopy, job: ImageJob): string {
  switch (job.status) {
    case "queued":
      return copy.statusQueued;
    case "running":
      return copy.statusRunning;
    case "provider_started":
      return copy.statusProviderStarted;
    case "succeeded":
      return copy.statusSucceeded;
    case "failed":
      return copy.statusFailed;
    case "cancelled":
      return copy.statusCancelled;
    default:
      return copy.statusUnknown;
  }
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

/**
 * The image step of the Instagram flow.
 *
 * It always draws the visual brief, which is free and provider-free, and only
 * ever reaches a paid generation through an explicit confirmation of a
 * preflight the user has seen. Nothing here starts on its own.
 */
export function ImageGenerationStep({
  businessId,
  copy,
  publicationText,
  trendTitle,
  projectId,
}: ImageGenerationStepProps) {
  const [brief, setBrief] = useState<VisualBrief>(emptyBrief);
  const [ratio, setRatio] = useState<ImageAspectRatio>("4:5");
  const [ratios, setRatios] = useState<readonly ImageAspectRatio[]>(imageAspectRatios);
  const [capability, setCapability] = useState<ImageCapabilityState | null>(null);
  const [budget, setBudget] = useState<ImageBudget | null>(null);
  const [references, setReferences] = useState<ImageReference[]>([]);
  const [referenceId, setReferenceId] = useState<string>("");
  const [preflight, setPreflight] = useState<ImagePreflight | null>(null);
  const [stale, setStale] = useState(false);
  const [job, setJob] = useState<ImageJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [checking, setChecking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [polling, setPolling] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState("");
  const attemptsRef = useRef(0);
  const confirmRef = useRef(false);
  const jobKeyRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    // Two free reads. Neither reaches a provider and neither spends anything,
    // so the brief is on screen before the user decides whether to generate.
    void Promise.all([
      api.images.draftBrief({
        business_id: businessId,
        publication_text: publicationText,
        trend_title: trendTitle,
      }),
      api.assets.list().catch(() => [] as Array<Record<string, unknown>>),
    ])
      .then(([draft, assets]) => {
        if (!active) return;
        setBrief({ ...emptyBrief(), ...draft.brief });
        setCapability(draft.capability);
        setBudget(draft.budget);
        const offered = draft.aspect_ratios?.length ? draft.aspect_ratios : imageAspectRatios;
        setRatios(offered);
        if (!offered.includes(ratio)) setRatio(offered[0]);
        setReferences(
          assets
            .filter((asset) => asset.asset_type === "image" && typeof asset.id === "string")
            .map((asset) => ({
              id: asset.id as string,
              original_name: (asset.original_name as string) || (asset.id as string),
            }))
        );
      })
      .catch((reason) =>
        active && setError(reason instanceof ApiError ? reason.message : copy.briefError)
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // The brief is drafted once per post. Editing the caption afterwards must
    // not silently rewrite what the user already adjusted here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId]);

  /**
   * A reload does not lose the generation, so do not buy it again.
   *
   * The job is durable and tied to the project, so the way back is to ask for
   * it. This only ever reads: whatever comes back is displayed, an unfinished
   * job resumes its poll, and a finished one shows its image. Nothing here can
   * start a generation, so a reload can never turn into a second charge.
   */
  useEffect(() => {
    if (!projectId) return;
    let active = true;
    setRecovering(true);
    void api.images
      .latestJob(projectId)
      .then((existing) => {
        if (!active || !existing) return;
        attemptsRef.current = 0;
        setExhausted(false);
        setJob(existing);
        setRecovered(true);
      })
      // A failed recovery is not worth an alert: the step still works, and the
      // only thing lost is the shortcut back to a job the user can re-check.
      .catch(() => undefined)
      .finally(() => active && setRecovering(false));
    return () => {
      active = false;
    };
  }, [projectId]);

  /** Any change to what would be generated retires the approval it was signed for. */
  const invalidate = useCallback(() => {
    setPreflight((current) => {
      if (current) setStale(true);
      return null;
    });
  }, []);

  function updateBrief(field: keyof VisualBrief, value: string) {
    setBrief((current) => ({ ...current, [field]: value }));
    invalidate();
  }

  function chooseRatio(value: ImageAspectRatio) {
    setRatio(value);
    invalidate();
  }

  function chooseReference(value: string) {
    setReferenceId(value);
    invalidate();
  }

  const readJob = useCallback(
    async (id: string) => {
      const next = await api.images.job(id);
      setJob(next);
      return next;
    },
    []
  );

  useEffect(() => {
    if (!job || isTerminalImageJob(job.status)) {
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
      attemptsRef.current += 1;
      void readJob(job.id).catch((reason) => {
        if (cancelled) return;
        // Stop the loop instead of hammering a failing endpoint; the manual
        // check stays available and the job keeps running on the server.
        setPolling(false);
        setError(reason instanceof ApiError ? reason.message : copy.statusError);
      });
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // Unmounting clears the timer, so a closed step never keeps polling.
  }, [job, readJob, copy.statusError]);

  async function runPreflight() {
    if (loading || checking) return;
    setChecking(true);
    setError("");
    setStale(false);
    try {
      const result = await api.images.preflight({
        brief,
        aspect_ratio: ratio,
        reference_asset_id: referenceId || null,
      });
      setPreflight(result);
      setCapability(result.capability);
      setBudget(result.budget);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.briefError);
    } finally {
      setChecking(false);
    }
  }

  async function confirm() {
    // No durable parent, no paid generation: an image whose project was never
    // saved cannot be found again after a reload, and it would still be billed.
    if (!projectId) return;
    if (!preflight?.allowed || !preflight.approval_token || confirmRef.current) return;
    confirmRef.current = true;
    setConfirming(true);
    setError("");
    try {
      // One key per confirmed generation: a replay of this exact click returns
      // the same job, while a later retry deliberately takes a fresh key.
      jobKeyRef.current ??= createIdempotencyKey();
      const created = await api.images.createJob(
        {
          brief: preflight.brief,
          aspect_ratio: preflight.aspect_ratio,
          approval_token: preflight.approval_token,
          confirmed: true,
          reference_asset_id: preflight.reference_asset_id,
          project_id: projectId,
        },
        { idempotencyKey: jobKeyRef.current }
      );
      attemptsRef.current = 0;
      setExhausted(false);
      setRecovered(false);
      setJob(created);
      setPreflight(null);
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
      setExhausted(false);
      await readJob(job.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.statusError);
    } finally {
      setChecking(false);
    }
  }

  /** A new attempt is a new generation, so it takes a new key and a new preflight. */
  function retry() {
    jobKeyRef.current = null;
    attemptsRef.current = 0;
    setJob(null);
    setExhausted(false);
    setRecovered(false);
    setError("");
    void runPreflight();
  }

  const status = capability?.status;
  const usable = Boolean(status && usableStatuses.has(status));
  const budgetSpent = Boolean(budget && budget.remaining <= 0);
  const blocked = !usable || budgetSpent;
  const blockedReason = budgetSpent && usable ? "quota_exhausted" : status;
  // Derived from the brief the user already edits, so there is no second copy
  // of it to keep in sync and no control that pretends to save what it cannot.
  const altValue = [brief.subject, brief.setting].filter(Boolean).join(". ");
  const active = Boolean(job && !isTerminalImageJob(job.status));

  return (
    <section className="image-step" aria-busy={loading || confirming || polling}>
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
        <p role="status">{copy.briefLoading}</p>
      ) : (
        <>
          <fieldset className="image-brief">
            <legend>{copy.briefHeading}</legend>
            {visualBriefFields.map((field) => (
              <label key={field}>
                {copy[field]}
                <textarea
                  value={brief[field]}
                  onChange={(event) => updateBrief(field, event.target.value)}
                  maxLength={visualBriefLimits[field]}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="image-ratios">
            <legend>{copy.formatHeading}</legend>
            <p id="image-format-hint">{copy.formatHint}</p>
            <div role="radiogroup" aria-describedby="image-format-hint" aria-label={copy.formatHeading}>
              {ratios.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={ratio === value}
                  data-selected={ratio === value}
                  onClick={() => chooseRatio(value)}
                >
                  {copy.ratioLabels[value]}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="image-reference">
            <label htmlFor="image-reference-select">{copy.referenceHeading}</label>
            <select
              id="image-reference-select"
              value={referenceId}
              aria-describedby="image-reference-hint"
              onChange={(event) => chooseReference(event.target.value)}
            >
              <option value="">{copy.referenceNone}</option>
              {references.map((reference) => (
                <option key={reference.id} value={reference.id}>
                  {reference.original_name}
                </option>
              ))}
            </select>
            <small id="image-reference-hint">{copy.referenceHint}</small>
          </div>

          {blocked ? (
            <div className="image-fallback" role="status">
              <h3>{copy.fallbackHeading}</h3>
              <p>{reasonText(copy, blockedReason)}</p>
              <p>{copy.fallbackHint}</p>
            </div>
          ) : (
            <div className="image-actions">
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

          {preflight && !blocked ? (
            <div className="image-preflight">
              <h3>{copy.preflightHeading}</h3>
              {preflight.allowed ? (
                <>
                  <p>
                    <strong>{copy.costHeading}:</strong> {copy.costValue}
                  </p>
                  <p>
                    <strong>{copy.budget}:</strong>{" "}
                    {fill(copy.budgetValue, {
                      remaining: preflight.budget.remaining,
                      total: preflight.budget.total,
                    })}
                  </p>
                  <p>{fill(copy.budgetReset, { date: formatDate(preflight.budget.next_reset_at) })}</p>
                  <label>
                    {copy.promptPreview}
                    <textarea value={preflight.prompt_preview} readOnly />
                  </label>
                  {/* Shown apart because it is sent apart, and signed with the
                      rest: what is approved is everything that will be used. */}
                  <label>
                    {copy.avoidPreview}
                    <textarea
                      value={preflight.negative_prompt_preview || copy.avoidPreviewNone}
                      readOnly
                    />
                  </label>
                  <p>{copy.confirmHint}</p>
                  <button
                    type="button"
                    className="button-primary"
                    onClick={() => void confirm()}
                    disabled={confirming || !projectId}
                  >
                    {confirming ? copy.confirming : copy.confirm}
                  </button>
                </>
              ) : (
                <p role="status">{preflight.message || reasonText(copy, preflight.reason_code)}</p>
              )}
            </div>
          ) : null}

          {job ? (
            <div className="image-job">
              <h3>{copy.statusHeading}</h3>
              {recovered ? <p role="status">{copy.recovered}</p> : null}
              <p role="status" aria-live="polite">
                {statusText(copy, job)}
              </p>
              {job.error ? <p className="page-error">{job.error}</p> : null}
              {exhausted && active ? <p role="status">{copy.pollTimeout}</p> : null}
              {job.status === "succeeded" && job.image_url ? (
                <>
                  {/* Deliberately not next/image: the source is a short-lived
                      signed link that must not be proxied or cached. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={job.image_url} alt={altValue} className="image-result" />
                  {/* A note, not a field: the alt text is the brief the user
                      already edits above, and no contract stores a second one.
                      An input here would look like it saves and would not. */}
                  <small className="image-alt">{copy.altNote}</small>
                  <small>{copy.linkExpires}</small>
                </>
              ) : null}
              <div className="image-job-actions">
                {active ? (
                  <button type="button" onClick={() => void checkStatus()} disabled={checking}>
                    {copy.checkStatus}
                  </button>
                ) : null}
                {job.status === "succeeded" ? (
                  // The link expires, the image does not. Re-reading the job
                  // mints a fresh one; it never reaches a provider.
                  <button type="button" onClick={() => void checkStatus()} disabled={checking}>
                    {copy.refreshLink}
                  </button>
                ) : null}
                {job.status === "failed" || job.status === "cancelled" ? (
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
