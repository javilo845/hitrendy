"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { RouteSplash } from "@/components/auth/route-splash";
import { SignupRoute } from "@/components/auth/signup-route";
import { Logo } from "@/components/brand/logo";
import { ProgressBar } from "@/components/onboarding/progress-bar";
import {
  StepBusiness,
  type BusinessFormData,
} from "@/components/onboarding/step-business";
import { StepChannels } from "@/components/onboarding/step-channels";
import { StepBrand } from "@/components/onboarding/step-brand";
import { StepReview } from "@/components/onboarding/step-review";
import {
  api,
  ApiError,
  createIdempotencyKey,
  type SignupBrandDraft,
  type SignupBusinessDraft,
  type SignupChannelsDraft,
  type SignupProgress,
  type SignupStep,
} from "@/lib/api";
import { routes } from "@/lib/routes";
import { surfaceCopy, useInterfaceLocale } from "@/lib/i18n";
import { defaultBrandColors } from "@/lib/brand-defaults";
import type { Category, Objective, Platform } from "@/types/business";
import type { Tone } from "@/types/brand";

type InterfaceLocale = "es" | "en" | "pt";

interface OnboardingData {
  business: BusinessFormData;
  channels: {
    preferred_platforms: Platform[];
    primary_objective: Objective | "";
  };
  brand: {
    voice_tones: Tone[];
    value_proposition: string;
    preferred_words: string;
    forbidden_words: string;
    primary_color: string;
    secondary_color: string;
    content_locale: InterfaceLocale;
  };
  confirmed: boolean;
}

const INITIAL: OnboardingData = {
  business: {
    name: "",
    category: "",
    country: "",
    city: "",
    description: "",
    primary_product: "",
    target_audience: "",
    website_url: "",
  },
  channels: {
    preferred_platforms: [],
    primary_objective: "",
  },
  brand: {
    voice_tones: [],
    value_proposition: "",
    preferred_words: "",
    forbidden_words: "",
    primary_color: defaultBrandColors.primary,
    secondary_color: defaultBrandColors.secondary,
    content_locale: "es",
  },
  confirmed: false,
};

const STEP_INDEX: Record<SignupStep | "completed", number> = {
  business: 0,
  channels: 1,
  brand: 2,
  review: 3,
  completed: 3,
};

const LAST_STEP = STEP_INDEX.review;

function wordsToList(value: string) {
  return value
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean);
}

function listToWords(value: string[] | undefined) {
  return value?.join(", ") || "";
}

function progressToData(progress: SignupProgress, current: OnboardingData) {
  const draft = progress.signup.draft;
  return {
    ...current,
    business: {
      ...current.business,
      ...(draft.business || {}),
      description: draft.business?.description || "",
      website_url: draft.business?.website_url || "",
    },
    channels: {
      ...current.channels,
      ...(draft.channels || {}),
    },
    brand: {
      ...current.brand,
      ...(draft.brand || {}),
      preferred_words: listToWords(draft.brand?.preferred_words),
      forbidden_words: listToWords(draft.brand?.forbidden_words),
      content_locale:
        draft.brand?.content_locale || current.brand.content_locale,
    },
    confirmed: draft.review?.confirmed || false,
  };
}

function isMissingSignup(error: unknown) {
  return error instanceof ApiError && [404, 410].includes(error.status);
}

export default function OnboardingPage() {
  const router = useRouter();
  const copy = surfaceCopy[useInterfaceLocale()].onboarding;
  const steps = copy.steps;
  const [step, setStep] = useState(0);
  const [data, setData] = useState<OnboardingData>(INITIAL);
  const [version, setVersion] = useState(1);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const completionKey = useRef<string | null>(null);
  const operationInFlight = useRef(false);

  /**
   * `current_step` is the first section the server still considers incomplete,
   * which is the right place to resume a session but the wrong place to jump to
   * mid-flow: someone who goes back to step 1 and saves it again would be
   * thrown forward to the review, skipping the steps in between. Callers that
   * own the navigation themselves pass `syncStep: false`.
   */
  const applyProgress = useCallback(
    (progress: SignupProgress, { syncStep = true } = {}) => {
      setData((current) => progressToData(progress, current));
      setVersion(progress.signup.version);
      if (syncStep) setStep(STEP_INDEX[progress.signup.current_step]);
    },
    []
  );

  useEffect(() => {
    let active = true;

    void api.auth.signup
      .get()
      .then((progress) => {
        if (!active) return;
        applyProgress(progress);
        setLoaded(true);
      })
      .catch((reason) => {
        if (!active) return;
        if (isMissingSignup(reason)) {
          router.replace(routes.register);
          return;
        }
        setError(
          reason instanceof ApiError
            ? reason.message
            : "No pudimos recuperar tu registro."
        );
        setLoaded(true);
      });

    return () => {
      active = false;
    };
  }, [applyProgress, router]);

  const updateBusiness = useCallback(
    (field: keyof BusinessFormData, value: string) => {
      completionKey.current = null;
      setData((current) => ({
        ...current,
        business: { ...current.business, [field]: value },
      }));
    },
    []
  );

  const update = useCallback((field: string, value: unknown) => {
    completionKey.current = null;
    setData((current) => ({
      ...current,
      ...(field in current.channels
        ? { channels: { ...current.channels, [field]: value } }
        : field in current.brand
          ? { brand: { ...current.brand, [field]: value } }
          : {}),
    }));
  }, []);

  function canProceed() {
    if (step === 0) {
      return Boolean(
        data.business.name.trim() &&
        data.business.category &&
        data.business.country.trim() &&
        data.business.city.trim() &&
        data.business.primary_product.trim() &&
        data.business.target_audience.trim()
      );
    }
    if (step === 1) {
      return (
        data.channels.preferred_platforms.length > 0 &&
        Boolean(data.channels.primary_objective)
      );
    }
    if (step === 2) {
      return (
        data.brand.voice_tones.length > 0 &&
        Boolean(data.brand.value_proposition.trim())
      );
    }
    return data.confirmed;
  }

  /**
   * Explains what is still missing instead of leaving the submit button dead.
   * Native constraint validation covers the text inputs and the objective
   * select; the checkbox-group minimums and the confirmation have no native
   * equivalent, so they need a message of their own.
   */
  function missingRequirement() {
    if (canProceed()) return "";
    if (step === 0) return copy.missingBusiness;
    if (step === 1) return copy.missingChannels;
    if (step === 2) return copy.missingBrand;
    return copy.missingReview;
  }

  function businessPayload(): SignupBusinessDraft {
    const { description, website_url, category, ...required } = data.business;
    return {
      ...required,
      category: category as Category,
      ...(description.trim() ? { description: description.trim() } : {}),
      ...(website_url.trim() ? { website_url: website_url.trim() } : {}),
    };
  }

  function channelsPayload(): SignupChannelsDraft {
    return {
      preferred_platforms: data.channels.preferred_platforms,
      primary_objective: data.channels.primary_objective as Objective,
    };
  }

  function brandPayload(): SignupBrandDraft {
    return {
      voice_tones: data.brand.voice_tones,
      value_proposition: data.brand.value_proposition.trim(),
      preferred_words: wordsToList(data.brand.preferred_words),
      forbidden_words: wordsToList(data.brand.forbidden_words),
      ...(data.brand.primary_color
        ? { primary_color: data.brand.primary_color }
        : {}),
      ...(data.brand.secondary_color
        ? { secondary_color: data.brand.secondary_color }
        : {}),
      content_locale: data.brand.content_locale,
    };
  }

  async function refreshFromServer() {
    const progress = await api.auth.signup.get();
    applyProgress(progress);
  }

  async function saveCurrentStep(
    nextStep: SignupStep,
    options: { syncStep?: boolean } = {}
  ) {
    const payload =
      nextStep === "business"
        ? { step: nextStep, business: businessPayload() }
        : nextStep === "channels"
          ? { step: nextStep, channels: channelsPayload() }
          : nextStep === "brand"
            ? { step: nextStep, brand: brandPayload() }
            : { step: nextStep, review: { confirmed: data.confirmed } };
    const progress = await api.auth.signup.saveDraft(payload, version);
    applyProgress(progress, options);
    return progress;
  }

  async function advance() {
    if (operationInFlight.current || saving || submitting || !canProceed())
      return;
    operationInFlight.current = true;
    setSaving(true);
    setError("");
    try {
      await saveCurrentStep(
        step === 0 ? "business" : step === 1 ? "channels" : "brand",
        { syncStep: false }
      );
      setStep((current) => Math.min(current + 1, LAST_STEP));
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "SIGNUP_CONFLICT") {
        try {
          await refreshFromServer();
          setError(
            "Tu registro cambió en otra pestaña. Cargamos la versión más reciente."
          );
        } catch {
          setError("Tu registro cambió. Actualiza la página para continuar.");
        }
      } else if (isMissingSignup(reason)) {
        router.replace(routes.register);
      } else {
        setError(
          reason instanceof ApiError
            ? reason.message
            : "No pudimos guardar este paso. Intenta de nuevo."
        );
      }
    } finally {
      setSaving(false);
      operationInFlight.current = false;
    }
  }

  async function finish() {
    if (operationInFlight.current || submitting || saving || !canProceed())
      return;
    operationInFlight.current = true;
    setSubmitting(true);
    setRetrying(false);
    setError("");
    try {
      await saveCurrentStep("review", { syncStep: false });
      if (!completionKey.current)
        completionKey.current = createIdempotencyKey();
      await api.auth.signup.complete({
        idempotencyKey: completionKey.current,
        onRetry: () => setRetrying(true),
      });
      await api.auth.me();
      router.replace(routes.dashboard);
      router.refresh();
    } catch (reason) {
      if (isMissingSignup(reason)) {
        router.replace(routes.register);
      } else if (
        reason instanceof ApiError &&
        reason.code === "SIGNUP_CONFLICT"
      ) {
        setError(
          "El registro cambió o ya fue completado. Actualiza para continuar."
        );
      } else {
        setError(
          reason instanceof ApiError
            ? reason.message
            : "No pudimos finalizar tu cuenta. Intenta de nuevo."
        );
      }
    } finally {
      setRetrying(false);
      setSubmitting(false);
      operationInFlight.current = false;
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const blocker = missingRequirement();
    if (blocker) {
      setError(blocker);
      return;
    }
    if (step < LAST_STEP) {
      await advance();
    } else {
      await finish();
    }
  }

  function back() {
    if (saving || submitting || step === 0) return;
    // A message about the step being left behind would only confuse.
    setError("");
    setStep((current) => current - 1);
  }

  async function cancel() {
    if (operationInFlight.current || saving || submitting) return;
    operationInFlight.current = true;
    setSaving(true);
    try {
      await api.auth.signup.cancel();
      router.replace(routes.register);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "No pudimos cancelar este registro."
      );
    } finally {
      setSaving(false);
      operationInFlight.current = false;
    }
  }

  if (!loaded) {
    return <RouteSplash label={copy.loading} />;
  }

  return (
    <SignupRoute>
      <main className="onboarding-page">
        <header className="onboarding-header">
          <Logo inverse />
          <div>
            <p className="eyebrow">{copy.eyebrow}</p>
            <h1>{copy.title}</h1>
          </div>
          <button
            type="button"
            className="onboarding-cancel"
            onClick={() => void cancel()}
            disabled={saving || submitting}
          >
            {copy.exit}
          </button>
        </header>

        <section className="onboarding-card" aria-label={copy.label}>
          <ProgressBar steps={steps} current={step} />
          <div className="onboarding-status" aria-live="polite">
            {retrying
              ? copy.retrying
              : saving
                ? copy.saving
                : submitting
                  ? copy.creating
                  : copy.saved}
          </div>
          {error ? (
            <div className="onboarding-error" role="alert">
              {error}
            </div>
          ) : null}

          <form onSubmit={(event) => void submit(event)}>
            {step === 0 ? (
              <StepBusiness data={data.business} onChange={updateBusiness} />
            ) : null}
            {step === 1 ? (
              <StepChannels data={data.channels} onChange={update} />
            ) : null}
            {step === 2 ? (
              <StepBrand
                data={data.brand}
                onChange={update}
                showContentLocale
              />
            ) : null}
            {step === 3 ? (
              <StepReview
                business={data.business}
                channels={data.channels}
                brand={data.brand}
                confirmed={data.confirmed}
                onConfirm={(confirmed) =>
                  setData((current) => ({ ...current, confirmed }))
                }
              />
            ) : null}

            <div className="onboarding-actions">
              <button
                type="button"
                className="button-secondary"
                onClick={back}
                disabled={step === 0 || saving || submitting}
              >
                {copy.back}
              </button>
              {step < LAST_STEP ? (
                <button
                  type="submit"
                  className="button-primary"
                  disabled={saving || submitting}
                >
                  {saving ? copy.saving : copy.next}
                </button>
              ) : (
                <button
                  type="submit"
                  className="button-primary onboarding-finish-button"
                  disabled={saving || submitting}
                >
                  {submitting ? copy.finishing : copy.finish}
                </button>
              )}
            </div>
          </form>
          <p className="onboarding-required-hint">{copy.requiredHint}</p>
          <p className="onboarding-keyboard-help">{copy.keyboard}</p>
          <p className="onboarding-version">
            {copy.version}: {version}
          </p>
        </section>
      </main>
    </SignupRoute>
  );
}
