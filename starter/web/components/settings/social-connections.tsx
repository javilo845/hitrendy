"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatDate, translate, type AppLocale } from "@/lib/i18n";
import type {
  SocialAccountType,
  SocialCallbackOutcome,
  SocialCallbackReason,
  SocialConnection,
  SocialConnectionError,
  SocialConnectionStatus,
  SocialProviderDescriptor,
  SocialProviderName,
  SocialProviderReason,
  SocialProviderStatus,
} from "@/types/social";

export interface SocialCallbackNotice {
  outcome: SocialCallbackOutcome;
  provider?: SocialProviderName;
  reason?: SocialCallbackReason;
}

interface SocialConnectionsProps {
  locale: AppLocale;
  callbackOutcome?: SocialCallbackNotice | null;
  onCallbackProcessed?: () => void;
  navigateToAuthorization?: (authorizationUrl: string) => void;
}

const PROVIDER_LABEL_KEYS: Record<SocialProviderName, string> = {
  instagram: "providers.instagram",
  tiktok: "providers.tiktok",
  x: "providers.x",
  demo: "providers.demo",
};

const PROVIDER_STATUS_KEYS: Record<SocialProviderStatus, string> = {
  available: "providerStatus.available",
  unconfigured: "providerStatus.unconfigured",
  disabled: "providerStatus.disabled",
};

const PROVIDER_REASON_KEYS: Record<SocialProviderReason, string> = {
  requires_platform_approval: "providerReason.requires_platform_approval",
  requires_paid_plan: "providerReason.requires_paid_plan",
  not_configured: "providerReason.not_configured",
};

const CONNECTION_STATUS_KEYS: Record<SocialConnectionStatus, string> = {
  connected: "connectionStatus.connected",
  expired: "connectionStatus.expired",
  revoked: "connectionStatus.revoked",
  degraded: "connectionStatus.degraded",
  error: "connectionStatus.error",
  disconnected: "connectionStatus.disconnected",
};

const ACCOUNT_TYPE_KEYS: Record<SocialAccountType, string> = {
  business: "accountType.business",
  creator: "accountType.creator",
  personal: "accountType.personal",
  unknown: "accountType.unknown",
};

const CONNECTION_ERROR_KEYS: Record<SocialConnectionError, string> = {
  provider_unavailable: "errors.provider_unavailable",
  token_unreadable: "errors.token_unreadable",
  revoke_unconfirmed: "errors.revoke_unconfirmed",
  invalid_grant: "errors.invalid_grant",
  token_expired: "errors.token_expired",
  token_revoked: "errors.token_revoked",
  insufficient_scope: "errors.insufficient_scope",
  unexpected_scope: "errors.unexpected_scope",
  no_eligible_account: "errors.no_eligible_account",
  provider_error: "errors.provider_error",
};

function hasKey<T extends string>(
  map: Record<T, string>,
  value: string
): value is T {
  return Object.prototype.hasOwnProperty.call(map, value);
}

export function SocialConnections({
  locale,
  callbackOutcome = null,
  onCallbackProcessed,
  navigateToAuthorization = (authorizationUrl) =>
    window.location.assign(authorizationUrl),
}: SocialConnectionsProps) {
  const t = useCallback(
    (key: string, values?: Record<string, string | number>) =>
      translate(locale, `settings.social.${key}`, values),
    [locale]
  );
  const [enabled, setEnabled] = useState(true);
  const [providers, setProviders] = useState<SocialProviderDescriptor[]>([]);
  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [callbackNotice, setCallbackNotice] =
    useState<SocialCallbackNotice | null>(null);
  const requestVersion = useRef(0);
  const initialLoadStarted = useRef(false);
  const handledCallback = useRef<string | null>(null);
  const confirmationRef = useRef<HTMLDivElement | null>(null);

  const loadConnections = useCallback(async (): Promise<boolean> => {
    const version = requestVersion.current + 1;
    requestVersion.current = version;
    setIsLoading(true);
    setLoadError("");

    try {
      const result = await api.social.connections();
      if (version !== requestVersion.current) return true;
      setEnabled(result.enabled);
      setProviders(result.providers);
      setConnections(result.connections);
      setHasLoaded(true);
      return true;
    } catch {
      if (version !== requestVersion.current) return true;
      setLoadError(t("loadError"));
      return false;
    } finally {
      if (version === requestVersion.current) setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (initialLoadStarted.current || callbackOutcome) return;
    initialLoadStarted.current = true;
    void loadConnections();
  }, [callbackOutcome, loadConnections]);

  useEffect(() => {
    if (!callbackOutcome) return;
    const signature = `${callbackOutcome.outcome}:${callbackOutcome.provider}:${
      callbackOutcome.reason ?? ""
    }`;
    if (handledCallback.current === signature) return;
    handledCallback.current = signature;
    initialLoadStarted.current = true;
    setCallbackNotice(callbackOutcome);
    void loadConnections().then(() => onCallbackProcessed?.());
  }, [callbackOutcome, loadConnections, onCallbackProcessed]);

  useEffect(() => {
    if (confirmingId) confirmationRef.current?.focus();
  }, [confirmingId]);

  const providerNames = useMemo(
    () => new Set(providers.map((provider) => provider.name)),
    [providers]
  );
  const orphanConnections = useMemo(
    () =>
      connections.filter(
        (connection) => !providerNames.has(connection.provider)
      ),
    [connections, providerNames]
  );

  function providerLabel(provider: string): string {
    if (!hasKey(PROVIDER_LABEL_KEYS, provider)) return "—";
    return t(PROVIDER_LABEL_KEYS[provider]);
  }

  function providerStatusLabel(status: string): string {
    if (!hasKey(PROVIDER_STATUS_KEYS, status)) return "—";
    return t(PROVIDER_STATUS_KEYS[status]);
  }

  function providerReasonLabel(reason: string): string {
    if (!hasKey(PROVIDER_REASON_KEYS, reason)) return "";
    return t(PROVIDER_REASON_KEYS[reason]);
  }

  function connectionStatusLabel(status: string): string {
    if (!hasKey(CONNECTION_STATUS_KEYS, status)) return "—";
    return t(CONNECTION_STATUS_KEYS[status]);
  }

  function accountTypeLabel(accountType: string): string {
    if (!hasKey(ACCOUNT_TYPE_KEYS, accountType)) return "—";
    return t(ACCOUNT_TYPE_KEYS[accountType]);
  }

  function connectionErrorLabel(error: string | null): string {
    if (!error || !hasKey(CONNECTION_ERROR_KEYS, error)) return "";
    return t(CONNECTION_ERROR_KEYS[error]);
  }

  function callbackMessage(notice: SocialCallbackNotice): string {
    if (notice.outcome === "connected" && notice.provider) {
      return t("callback.connected", {
        provider: providerLabel(notice.provider),
      });
    }
    if (notice.outcome === "connected") return t("callback.invalid_request");
    const reason = notice.reason ?? "provider_error";
    return t(`callback.${reason}`);
  }

  async function connect(provider: SocialProviderDescriptor) {
    if (!enabled || provider.status !== "available" || busyAction) return;
    setActionError("");
    setBusyAction(`connect:${provider.name}`);
    try {
      const result = await api.social.authorize(provider.name, "/settings");
      navigateToAuthorization(result.authorization_url);
    } catch {
      setActionError(t("connectError"));
    } finally {
      setBusyAction(null);
    }
  }

  async function check(connection: SocialConnection) {
    if (!enabled || busyAction) return;
    setActionError("");
    setBusyAction(`check:${connection.id}`);
    try {
      const updated = await api.social.check(connection.id);
      setConnections((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch {
      setActionError(t("checkError"));
    } finally {
      setBusyAction(null);
    }
  }

  async function disconnect(connection: SocialConnection) {
    if (!enabled || busyAction) return;
    setActionError("");
    setBusyAction(`disconnect:${connection.id}`);
    try {
      await api.social.disconnect(connection.id);
      setConfirmingId(null);
      await loadConnections();
    } catch {
      setActionError(t("disconnectError"));
    } finally {
      setBusyAction(null);
    }
  }

  function renderConnection(connection: SocialConnection) {
    const errorLabel = connectionErrorLabel(connection.safe_error);
    const isChecking = busyAction === `check:${connection.id}`;
    const isDisconnecting = busyAction === `disconnect:${connection.id}`;
    const isConfirming = confirmingId === connection.id;

    return (
      <article key={connection.id} className="social-connection">
        <h4>{connection.display_name}</h4>
        <dl className="social-connection-facts">
          <div>
            <dt>{t("accountTypeLabel")}</dt>
            <dd>{accountTypeLabel(connection.account_type)}</dd>
          </div>
          <div>
            <dt>{t("statusLabel")}</dt>
            <dd>{connectionStatusLabel(connection.status)}</dd>
          </div>
          <div>
            <dt>{t("connectedAt")}</dt>
            <dd>{formatDate(locale, connection.connected_at) || "—"}</dd>
          </div>
          <div>
            <dt>{t("lastCheckedAt")}</dt>
            <dd>{formatDate(locale, connection.last_checked_at) || "—"}</dd>
          </div>
        </dl>
        {errorLabel ? (
          <p className="settings-status settings-status--error">{errorLabel}</p>
        ) : null}
        <div className="social-connection-actions">
          <button
            type="button"
            className="button-secondary button-small"
            disabled={!enabled || busyAction !== null}
            aria-busy={isChecking}
            onClick={() => void check(connection)}
          >
            {isChecking ? t("checking") : t("check")}
          </button>
          <button
            type="button"
            className="button-quiet button-small"
            disabled={!enabled || busyAction !== null}
            onClick={() => setConfirmingId(connection.id)}
          >
            {t("disconnect")}
          </button>
        </div>
        {isConfirming ? (
          <div
            className="social-confirm"
            ref={confirmationRef}
            role="group"
            tabIndex={-1}
            aria-label={t("disconnectQuestion")}
          >
            <p>{t("disconnectQuestion")}</p>
            <div className="social-connection-actions">
              <button
                type="button"
                className="button-danger button-small"
                disabled={!enabled || busyAction !== null}
                aria-busy={isDisconnecting}
                onClick={() => void disconnect(connection)}
              >
                {isDisconnecting ? t("disconnecting") : t("confirm")}
              </button>
              <button
                type="button"
                className="button-quiet button-small"
                disabled={!enabled || busyAction !== null}
                onClick={() => setConfirmingId(null)}
              >
                {t("cancel")}
              </button>
            </div>
          </div>
        ) : null}
      </article>
    );
  }

  const showInitialLoading = isLoading && !hasLoaded;
  const showInitialError = Boolean(loadError) && !hasLoaded && !isLoading;
  const showContent = hasLoaded && !showInitialLoading && !showInitialError;

  return (
    <section
      className="settings-card"
      aria-labelledby="social-connections-title"
      aria-busy={isLoading || busyAction !== null}
    >
      <h2 id="social-connections-title">{t("title")}</h2>
      <p className="settings-hint">{t("description")}</p>
      {callbackNotice ? (
        <p
          className={`settings-status settings-status--${
            callbackNotice.outcome === "connected" ? "ok" : "error"
          }`}
          role="status"
          aria-live="polite"
        >
          {callbackMessage(callbackNotice)}
        </p>
      ) : null}
      {showInitialLoading ? (
        <p className="settings-status" role="status" aria-live="polite">
          {t("loading")}
        </p>
      ) : null}
      {showInitialError ? (
        <p
          className="settings-status settings-status--error"
          role="status"
          aria-live="polite"
        >
          {loadError}
        </p>
      ) : null}
      {showContent ? (
        <>
          {!enabled ? (
            <p className="settings-status" role="status" aria-live="polite">
              {t("disabled")}
            </p>
          ) : null}
          {loadError ? (
            <p
              className="settings-status settings-status--error"
              role="status"
              aria-live="polite"
            >
              {loadError}
            </p>
          ) : null}
          {actionError ? (
            <p
              className="settings-status settings-status--error"
              role="status"
              aria-live="polite"
            >
              {actionError}
            </p>
          ) : null}
          {!connections.length ? (
            <p className="settings-empty" role="status" aria-live="polite">
              {t("empty")}
            </p>
          ) : null}
          <ul className="social-provider-list" aria-label={t("title")}>
            {providers.map((provider) => {
              const providerConnections = connections.filter(
                (connection) => connection.provider === provider.name
              );
              const reason = provider.reason_code
                ? providerReasonLabel(provider.reason_code)
                : "";
              const isConnectBusy = busyAction === `connect:${provider.name}`;

              return (
                <li className="social-provider" key={provider.name}>
                  <div className="social-provider-head">
                    <div className="social-provider-title">
                      <h3>{providerLabel(provider.name)}</h3>
                      <p className="social-provider-status">
                        {providerStatusLabel(provider.status)}
                      </p>
                      {reason ? (
                        <p className="settings-hint">{reason}</p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className="button-secondary button-small"
                      disabled={
                        !enabled ||
                        provider.status !== "available" ||
                        busyAction !== null
                      }
                      aria-busy={isConnectBusy}
                      onClick={() => void connect(provider)}
                    >
                      {isConnectBusy ? t("connecting") : t("connect")}
                    </button>
                  </div>
                  {providerConnections.map(renderConnection)}
                </li>
              );
            })}
            {orphanConnections.map((connection) => (
              <li className="social-provider" key={connection.id}>
                {renderConnection(connection)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
