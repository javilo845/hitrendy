"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AppShell } from "@/components/shell/app-shell";
import {
  SocialConnections,
  type SocialCallbackNotice,
} from "@/components/settings/social-connections";
import { api, ApiError, type AccountUser, type UsageItem } from "@/lib/api";
import {
  clearDeletionStatusToken,
  ensureDeletionStatusToken,
} from "@/lib/deletion-status";
import {
  formatCost,
  formatNumber,
  localeLabels,
  optionLabel,
  readStoredLocale,
  setStoredLocale,
  supportedLocales,
  translate,
  type AppLocale,
} from "@/lib/i18n";
import { platformLabels, platformOrder } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { BrandProfile, Tone } from "@/types/brand";
import type {
  BusinessProfile,
  Category,
  ContentLocale,
  Objective,
  Platform,
  UpdateBusinessRequest,
} from "@/types/business";
import type { SocialCallbackReason, SocialProviderName } from "@/types/social";

type Tab =
  | "account"
  | "business"
  | "brand"
  | "social"
  | "language"
  | "usage"
  | "privacy"
  | "delete";

const TABS: Tab[] = [
  "account",
  "business",
  "brand",
  "social",
  "language",
  "usage",
  "privacy",
  "delete",
];

const CATEGORIES: Category[] = [
  "fashion",
  "art",
  "lifestyle",
  "health",
  "gastronomy",
  "services",
  "retail",
  "technology",
  "other",
];

const OBJECTIVES: Objective[] = [
  "reach",
  "engagement",
  "sales",
  "store_visits",
  "launch",
  "brand_awareness",
  "community",
];

const TONES: Tone[] = [
  "friendly",
  "professional",
  "youthful",
  "elegant",
  "fun",
  "direct",
  "inspiring",
];

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;

/** Draft of the brand form: the word lists stay as raw text while editing. */
interface BrandDraft {
  voice_tones: Tone[];
  value_proposition: string;
  preferred_words: string;
  forbidden_words: string;
  primary_color: string;
  secondary_color: string;
}

const SOCIAL_PROVIDERS = new Set<SocialProviderName>([
  "instagram",
  "tiktok",
  "x",
  "demo",
]);

const SOCIAL_CALLBACK_REASONS = new Set<SocialCallbackReason>([
  "invalid_request",
  "denied",
  "provider_error",
  "unavailable",
]);

interface SearchParamsLike {
  getAll(name: string): string[];
  toString(): string;
}

function singleSearchParam(
  searchParams: SearchParamsLike,
  name: string
): string | null {
  const values = searchParams.getAll(name);
  return values.length === 1 ? (values[0] ?? null) : null;
}

function isSocialProvider(value: string): value is SocialProviderName {
  return SOCIAL_PROVIDERS.has(value as SocialProviderName);
}

function isSocialCallbackReason(value: string): value is SocialCallbackReason {
  return SOCIAL_CALLBACK_REASONS.has(value as SocialCallbackReason);
}

function readSocialCallback(
  searchParams: SearchParamsLike
): SocialCallbackNotice | null {
  const outcome = singleSearchParam(searchParams, "social");
  const provider = singleSearchParam(searchParams, "provider");
  const reason = singleSearchParam(searchParams, "reason");

  if (
    outcome === "connected" &&
    provider &&
    isSocialProvider(provider) &&
    reason === null
  ) {
    return { outcome, provider };
  }
  if (
    outcome === "error" &&
    reason &&
    isSocialCallbackReason(reason) &&
    (provider === null || isSocialProvider(provider))
  ) {
    return {
      outcome,
      ...(provider ? { provider } : {}),
      reason,
    };
  }
  return null;
}

function toBrandDraft(profile: BrandProfile | null): BrandDraft {
  return {
    voice_tones: profile?.voice_tones ?? [],
    value_proposition: profile?.value_proposition ?? "",
    preferred_words: (profile?.preferred_words ?? []).join(", "),
    forbidden_words: (profile?.forbidden_words ?? []).join(", "),
    primary_color: profile?.primary_color ?? "",
    secondary_color: profile?.secondary_color ?? "",
  };
}

function splitWords(value: string): string[] {
  const seen = new Set<string>();
  const words: string[] = [];
  for (const raw of value.split(",")) {
    const word = raw.trim();
    if (!word) continue;
    const key = word.toLocaleLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    words.push(word);
  }
  return words;
}

function SettingsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<Tab>("account");
  const [locale, setLocale] = useState<AppLocale>(readStoredLocale);
  const t = useCallback(
    (key: string, values?: Record<string, string | number>) =>
      translate(locale, `settings.${key}`, values),
    [locale]
  );
  const loadErrorRef = useRef(translate(locale, "settings.loadError"));

  const [me, setMe] = useState<AccountUser | null>(null);
  const [name, setName] = useState("");
  const [business, setBusiness] = useState<BusinessProfile | null>(null);
  const [brand, setBrand] = useState<BrandDraft>(() => toBrandDraft(null));
  const [usage, setUsage] = useState<UsageItem[]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [deletionRequested, setDeletionRequested] = useState(false);
  const [socialCallback, setSocialCallback] =
    useState<SocialCallbackNotice | null>(null);
  const callbackSeenRef = useRef<string | null>(null);

  const parsedSocialCallback = useMemo(
    () => readSocialCallback(searchParams),
    [searchParams]
  );
  const callbackSignature = parsedSocialCallback
    ? `${parsedSocialCallback.outcome}:${parsedSocialCallback.provider ?? ""}:${
        parsedSocialCallback.reason ?? ""
      }`
    : null;

  useEffect(() => {
    if (
      !parsedSocialCallback ||
      callbackSeenRef.current === callbackSignature
    ) {
      return;
    }
    callbackSeenRef.current = callbackSignature;
    setTab("social");
    setSocialCallback(parsedSocialCallback);
  }, [callbackSignature, parsedSocialCallback]);

  const clearSocialCallback = useCallback(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete("social");
    next.delete("provider");
    next.delete("reason");
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
    setSocialCallback(null);
  }, [pathname, router, searchParams]);

  useEffect(() => {
    void Promise.all([api.auth.me(), api.businesses.list(), api.auth.usage()])
      .then(async ([account, businesses, usageData]) => {
        const current = (businesses[0] as unknown as BusinessProfile) ?? null;
        const nextLocale = account.user.interface_locale ?? "es";
        setLocale(nextLocale);
        setStoredLocale(nextLocale);
        setMe(account.user);
        setName(account.user.name);
        setBusiness(current);
        setUsage(usageData.items);
        if (current) {
          const profile = (await api.businesses.brandProfile.get(
            current.id
          )) as unknown as BrandProfile | null;
          setBrand(toBrandDraft(profile));
        }
      })
      .catch((reason) =>
        setMessage(
          reason instanceof ApiError ? reason.message : loadErrorRef.current
        )
      );
  }, []);

  useEffect(() => {
    // A browser navigation away from a dirty form must not silently discard edits.
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [dirty]);

  const tabs = useMemo(
    () => TABS.map((id) => [id, t(`tabs.${id}`)] as const),
    [t]
  );

  function editBusiness(patch: Partial<BusinessProfile>) {
    setBusiness((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  }

  function editBrand(patch: Partial<BrandDraft>) {
    setBrand((current) => ({ ...current, ...patch }));
    setDirty(true);
  }

  function updateLocale(next: AppLocale) {
    setLocale(next);
    setStoredLocale(next);
    setDirty(true);
  }

  function togglePlatform(platform: Platform) {
    if (!business) return;
    const current = business.preferred_platforms ?? [];
    editBusiness({
      preferred_platforms: current.includes(platform)
        ? current.filter((item) => item !== platform)
        : [...current, platform],
    });
  }

  function toggleTone(tone: Tone) {
    const current = brand.voice_tones;
    if (current.includes(tone)) {
      editBrand({ voice_tones: current.filter((item) => item !== tone) });
    } else if (current.length < 3) {
      editBrand({ voice_tones: [...current, tone] });
    }
  }

  /** Only the fields the API accepts travel: never the whole loaded object. */
  function businessPayload(source: BusinessProfile): UpdateBusinessRequest {
    return {
      name: source.name,
      category: source.category,
      country: source.country,
      city: source.city,
      description: source.description ?? "",
      primary_product: source.primary_product,
      target_audience: source.target_audience,
      preferred_platforms: source.preferred_platforms,
      primary_objective: source.primary_objective,
      content_locale: source.content_locale,
    };
  }

  function failureMessage(reason: unknown): string {
    return reason instanceof ApiError ? reason.message : t("saveError");
  }

  /** Each saver reports its own outcome so a partial failure stays visible. */
  async function persistAccount(): Promise<string | null> {
    if (!me) return null;
    if (!name.trim()) return t("account.nameRequired");
    try {
      const result = await api.auth.updateAccount({
        name: name.trim(),
        interface_locale: locale,
      });
      setMe(result.user);
      setName(result.user.name);
      return null;
    } catch (reason) {
      return failureMessage(reason);
    }
  }

  async function persistBusiness(): Promise<string | null> {
    if (!business) return null;
    if (!business.preferred_platforms?.length) {
      return t("business.platformsRequired");
    }
    try {
      const updated = (await api.businesses.update(
        business.id,
        businessPayload(business) as unknown as Record<string, unknown>
      )) as unknown as BusinessProfile;
      setBusiness(updated);
      return null;
    } catch (reason) {
      return failureMessage(reason);
    }
  }

  async function persistBrand(): Promise<string | null> {
    if (!business) return null;
    if (brand.voice_tones.length < 1 || brand.voice_tones.length > 3) {
      return t("brand.tonesRequired");
    }
    if (!brand.value_proposition.trim()) return t("brand.valueRequired");
    const preferred = splitWords(brand.preferred_words);
    const forbidden = splitWords(brand.forbidden_words);
    const forbiddenKeys = new Set(
      forbidden.map((word) => word.toLocaleLowerCase())
    );
    if (preferred.some((word) => forbiddenKeys.has(word.toLocaleLowerCase()))) {
      return t("brand.wordConflict");
    }
    for (const color of [brand.primary_color, brand.secondary_color]) {
      if (color && !HEX_COLOR.test(color)) return t("brand.colorFormat");
    }
    try {
      const saved = (await api.businesses.brandProfile.upsert(business.id, {
        voice_tones: brand.voice_tones,
        value_proposition: brand.value_proposition.trim(),
        preferred_words: preferred,
        forbidden_words: forbidden,
        ...(brand.primary_color ? { primary_color: brand.primary_color } : {}),
        ...(brand.secondary_color
          ? { secondary_color: brand.secondary_color }
          : {}),
      })) as unknown as BrandProfile;
      setBrand(toBrandDraft(saved));
      return null;
    } catch (reason) {
      return failureMessage(reason);
    }
  }

  /**
   * Run the savers one after another and report honestly: everything saved,
   * nothing saved, or a partial save naming what failed.
   */
  async function save(savers: Array<() => Promise<string | null>>) {
    setSaving(true);
    setMessage("");
    const failures: string[] = [];
    let succeeded = 0;
    try {
      for (const saver of savers) {
        const failure = await saver();
        if (failure) failures.push(failure);
        else succeeded += 1;
      }
    } finally {
      setSaving(false);
    }
    if (!failures.length) {
      setDirty(false);
      setMessage(t("saved"));
      return;
    }
    // A failure leaves the form dirty: the user still has unsaved work.
    setMessage(
      succeeded > 0
        ? `${t("partialSave")} ${failures.join(" ")}`
        : failures.join(" ")
    );
  }

  async function requestDeletion() {
    if (!me) return;
    const phrase = me.deletion_confirmation_phrase;
    if (confirmation.trim() !== phrase) {
      setMessage(t("deletion.confirmError", { phrase }));
      return;
    }
    setSaving(true);
    // Minted before the call and kept in this tab, so a retry lands on the
    // same purge job and the tracker survives the revoked session.
    const token = ensureDeletionStatusToken();
    try {
      await api.auth.deleteAccount(confirmation.trim(), token);
      setDirty(false);
      setDeletionRequested(true);
      setMessage(t("deletion.blocked"));
      // The session is already revoked server-side; clear it locally too and
      // leave for the public tracker, which needs no session at all.
      try {
        await api.auth.logout();
      } catch {
        // Already gone server-side — nothing left to clean up.
      }
      router.replace(routes.accountDeletionStatus);
    } catch (reason) {
      clearDeletionStatusToken();
      setMessage(failureMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  const saveLabel = saving ? translate(locale, "common.saving") : t("save");

  return (
    <AppShell>
      <main
        className="app-page app-page--narrow settings-page"
        aria-labelledby="settings-title"
      >
        <header className="settings-header">
          <h1 id="settings-title">{t("title")}</h1>
        </header>
        {/* Horizontally scrollable rather than wrapping: eight tabs on a phone
            would otherwise take three rows before the panel even starts. */}
        <div className="settings-tabs" role="tablist" aria-label={t("title")}>
          {tabs.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className="settings-tab"
              role="tab"
              id={`settings-tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`settings-panel-${id}`}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        {message ? (
          <p className="settings-status" role="status" aria-live="polite">
            {message}
          </p>
        ) : null}
        {!me ? (
          <p className="settings-status" role="status">
            {translate(locale, "common.loading")}
          </p>
        ) : null}

        {tab === "account" && me ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-account"
            aria-labelledby="settings-tab-account"
          >
            <h2>{t("tabs.account")}</h2>
            <div className="settings-grid">
              <label className="settings-field">
                {t("account.name")}
                <input
                  value={name}
                  maxLength={120}
                  onChange={(event) => {
                    setName(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
              <label className="settings-field">
                {t("account.email")}
                <input value={me.email} readOnly disabled />
                <small className="settings-hint">
                  {t("account.emailHint")}
                </small>
              </label>
              <label className="settings-field">
                {t("language.interface")}
                <select
                  value={locale}
                  onChange={(event) =>
                    updateLocale(event.target.value as AppLocale)
                  }
                >
                  {supportedLocales.map((item) => (
                    <option key={item} value={item}>
                      {localeLabels[item]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="settings-actions">
              <button
                type="button"
                className="button-primary"
                disabled={saving}
                onClick={() => void save([persistAccount])}
              >
                {saveLabel}
              </button>
            </div>
          </section>
        ) : null}

        {tab === "business" ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-business"
            aria-labelledby="settings-tab-business"
          >
            <h2>{t("tabs.business")}</h2>
            {business ? (
              <>
                <div className="settings-grid">
                  <label className="settings-field">
                    {t("business.name")}
                    <input
                      value={business.name}
                      maxLength={120}
                      onChange={(event) =>
                        editBusiness({ name: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("business.category")}
                    <select
                      value={business.category}
                      onChange={(event) =>
                        editBusiness({
                          category: event.target.value as Category,
                        })
                      }
                    >
                      {CATEGORIES.map((item) => (
                        <option key={item} value={item}>
                          {optionLabel(locale, "category", item)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="settings-field">
                    {t("business.country")}
                    <input
                      value={business.country}
                      maxLength={80}
                      onChange={(event) =>
                        editBusiness({ country: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("business.city")}
                    <input
                      value={business.city}
                      maxLength={80}
                      onChange={(event) =>
                        editBusiness({ city: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field settings-field--wide">
                    {t("business.description")}
                    <textarea
                      value={business.description ?? ""}
                      maxLength={500}
                      rows={4}
                      onChange={(event) =>
                        editBusiness({ description: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("business.product")}
                    <input
                      value={business.primary_product}
                      maxLength={160}
                      onChange={(event) =>
                        editBusiness({ primary_product: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("business.audience")}
                    <input
                      value={business.target_audience}
                      maxLength={160}
                      onChange={(event) =>
                        editBusiness({ target_audience: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("business.objective")}
                    <select
                      value={business.primary_objective}
                      onChange={(event) =>
                        editBusiness({
                          primary_objective: event.target.value as Objective,
                        })
                      }
                    >
                      {OBJECTIVES.map((item) => (
                        <option key={item} value={item}>
                          {optionLabel(locale, "objective", item)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <fieldset className="settings-fieldset">
                  <legend>{t("business.platforms")}</legend>
                  <div className="settings-choice-grid">
                    {platformOrder.map((value) => (
                      <label key={value} className="settings-choice">
                        <input
                          type="checkbox"
                          checked={(
                            business.preferred_platforms ?? []
                          ).includes(value)}
                          onChange={() => togglePlatform(value)}
                        />
                        {platformLabels[value]}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="settings-actions">
                  <button
                    type="button"
                    className="button-primary"
                    disabled={saving}
                    onClick={() => void save([persistBusiness])}
                  >
                    {saveLabel}
                  </button>
                </div>
              </>
            ) : (
              <p className="settings-empty">{t("noBusiness")}</p>
            )}
          </section>
        ) : null}

        {tab === "brand" ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-brand"
            aria-labelledby="settings-tab-brand"
          >
            <h2>{t("tabs.brand")}</h2>
            {business ? (
              <>
                <fieldset className="settings-fieldset">
                  <legend>{t("brand.tones")}</legend>
                  <p className="settings-hint">{t("brand.tonesHint")}</p>
                  <div className="settings-choice-grid">
                    {TONES.map((tone) => (
                      <label key={tone} className="settings-choice">
                        <input
                          type="checkbox"
                          checked={brand.voice_tones.includes(tone)}
                          disabled={
                            !brand.voice_tones.includes(tone) &&
                            brand.voice_tones.length >= 3
                          }
                          onChange={() => toggleTone(tone)}
                        />
                        {optionLabel(locale, "tone", tone)}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="settings-grid">
                  <label className="settings-field settings-field--wide">
                    {t("brand.value")}
                    <textarea
                      value={brand.value_proposition}
                      maxLength={500}
                      rows={4}
                      onChange={(event) =>
                        editBrand({ value_proposition: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("brand.preferred")}
                    <input
                      value={brand.preferred_words}
                      onChange={(event) =>
                        editBrand({ preferred_words: event.target.value })
                      }
                    />
                  </label>
                  <label className="settings-field">
                    {t("brand.forbidden")}
                    <input
                      value={brand.forbidden_words}
                      onChange={(event) =>
                        editBrand({ forbidden_words: event.target.value })
                      }
                    />
                  </label>
                  <p className="settings-hint settings-field--wide">
                    {t("brand.wordsHint")}
                  </p>
                  <label className="settings-field">
                    {t("brand.primaryColor")}
                    {/* The swatch mirrors the field instead of replacing it:
                        the API stores a hex string and a colour input cannot
                        represent the empty value a new brand starts with. */}
                    <span className="settings-color">
                      <input
                        value={brand.primary_color}
                        maxLength={7}
                        placeholder="#RRGGBB"
                        onChange={(event) =>
                          editBrand({ primary_color: event.target.value })
                        }
                      />
                      <i
                        aria-hidden="true"
                        className="settings-swatch"
                        style={
                          HEX_COLOR.test(brand.primary_color)
                            ? { background: brand.primary_color }
                            : undefined
                        }
                      />
                    </span>
                  </label>
                  <label className="settings-field">
                    {t("brand.secondaryColor")}
                    <span className="settings-color">
                      <input
                        value={brand.secondary_color}
                        maxLength={7}
                        placeholder="#RRGGBB"
                        onChange={(event) =>
                          editBrand({ secondary_color: event.target.value })
                        }
                      />
                      <i
                        aria-hidden="true"
                        className="settings-swatch"
                        style={
                          HEX_COLOR.test(brand.secondary_color)
                            ? { background: brand.secondary_color }
                            : undefined
                        }
                      />
                    </span>
                  </label>
                </div>
                <div className="settings-actions">
                  <button
                    type="button"
                    className="button-primary"
                    disabled={saving}
                    onClick={() => void save([persistBrand])}
                  >
                    {saveLabel}
                  </button>
                </div>
              </>
            ) : (
              <p className="settings-empty">{t("noBusiness")}</p>
            )}
          </section>
        ) : null}

        {tab === "social" ? (
          <div
            role="tabpanel"
            id="settings-panel-social"
            aria-labelledby="settings-tab-social"
          >
            <SocialConnections
              locale={locale}
              callbackOutcome={socialCallback}
              onCallbackProcessed={clearSocialCallback}
            />
          </div>
        ) : null}

        {tab === "language" && me ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-language"
            aria-labelledby="settings-tab-language"
          >
            <h2>{t("tabs.language")}</h2>
            <div className="settings-grid">
              <label className="settings-field">
                {t("language.interface")}
                <select
                  value={locale}
                  onChange={(event) =>
                    updateLocale(event.target.value as AppLocale)
                  }
                >
                  {supportedLocales.map((item) => (
                    <option key={item} value={item}>
                      {localeLabels[item]}
                    </option>
                  ))}
                </select>
              </label>
              {business ? (
                <label className="settings-field">
                  {t("language.content")}
                  <select
                    value={business.content_locale ?? "es"}
                    onChange={(event) =>
                      editBusiness({
                        content_locale: event.target.value as ContentLocale,
                      })
                    }
                  >
                    {supportedLocales.map((item) => (
                      <option key={item} value={item}>
                        {localeLabels[item]}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
            <p className="settings-hint">{t("language.hint")}</p>
            <div className="settings-actions">
              <button
                type="button"
                className="button-primary"
                disabled={saving}
                onClick={() =>
                  void save(
                    business
                      ? [persistAccount, persistBusiness]
                      : [persistAccount]
                  )
                }
              >
                {saveLabel}
              </button>
            </div>
          </section>
        ) : null}

        {tab === "usage" ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-usage"
            aria-labelledby="settings-tab-usage"
          >
            <h2>{t("usage.title")}</h2>
            <p className="settings-hint">{t("usage.note")}</p>
            <p className="settings-hint">{t("usage.unknownHint")}</p>
            {usage.length ? (
              <ul className="settings-usage-list">
                {usage.map((item) => (
                  <li
                    key={`${item.capability}:${item.quality_level}:${item.currency ?? ""}`}
                    className="settings-usage-item"
                  >
                    <strong>
                      {optionLabel(locale, "capability", item.capability)} ·{" "}
                      {optionLabel(locale, "quality", item.quality_level)}
                    </strong>
                    <span>
                      {t("usage.generations")}:{" "}
                      {formatNumber(locale, item.generations)}
                    </span>
                    <span>
                      {t("usage.tokens")}:{" "}
                      {item.total_tokens === null
                        ? t("usage.unknown")
                        : formatNumber(locale, item.total_tokens)}
                    </span>
                    <span>
                      {t("usage.cost")}:{" "}
                      {item.reported_cost === null
                        ? t("usage.unknown")
                        : formatCost(locale, item.reported_cost, item.currency)}
                    </span>
                    <span>
                      {formatNumber(locale, item.known_cost_count)}{" "}
                      {t("usage.knownCost")} ·{" "}
                      {formatNumber(locale, item.unknown_cost_count)}{" "}
                      {t("usage.unknownCost")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="settings-empty">{t("usage.empty")}</p>
            )}
          </section>
        ) : null}

        {tab === "privacy" ? (
          <section
            className="settings-card"
            role="tabpanel"
            id="settings-panel-privacy"
            aria-labelledby="settings-tab-privacy"
          >
            <h2>{t("privacy.title")}</h2>
            <p>{t("privacy.body")}</p>
            <p className="settings-links">
              <Link href={routes.privacy}>Leer política completa</Link>
              <Link href={routes.terms}>Leer términos de la beta</Link>
              <Link href={routes.feedback}>
                Contactar soporte o enviar feedback
              </Link>
            </p>
          </section>
        ) : null}

        {tab === "delete" && me ? (
          <section
            className="settings-card settings-card--danger"
            role="tabpanel"
            id="settings-panel-delete"
            aria-labelledby="settings-tab-delete"
          >
            <h2>{t("deletion.title")}</h2>
            <p>{t("deletion.body")}</p>
            {deletionRequested ? (
              <p className="settings-links">
                <Link href={routes.accountDeletionStatus}>
                  {t("deletion.followLink")}
                </Link>
              </p>
            ) : (
              <>
                <label className="settings-field">
                  {t("deletion.confirmLabel", {
                    phrase: me.deletion_confirmation_phrase,
                  })}
                  <input
                    value={confirmation}
                    maxLength={64}
                    onChange={(event) => setConfirmation(event.target.value)}
                  />
                </label>
                <div className="settings-actions">
                  <button
                    type="button"
                    className="button-danger"
                    disabled={saving}
                    onClick={() => void requestDeletion()}
                  >
                    {saving
                      ? translate(locale, "common.saving")
                      : t("deletion.request")}
                  </button>
                </div>
              </>
            )}
          </section>
        ) : null}
      </main>
    </AppShell>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsPageContent />
    </Suspense>
  );
}
