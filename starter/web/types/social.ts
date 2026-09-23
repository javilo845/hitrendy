export type SocialProviderStatus = "available" | "unconfigured" | "disabled";

export type SocialProviderReason =
  "requires_platform_approval" | "requires_paid_plan" | "not_configured";

export type SocialProviderName = "instagram" | "tiktok" | "x" | "demo";

export interface SocialProviderDescriptor {
  name: string;
  status: SocialProviderStatus;
  reason_code: SocialProviderReason | null;
}

export type SocialConnectionStatus =
  "connected" | "expired" | "revoked" | "degraded" | "error" | "disconnected";

export type SocialAccountType = "business" | "creator" | "personal" | "unknown";

export type SocialConnectionError =
  | "provider_unavailable"
  | "token_unreadable"
  | "revoke_unconfirmed"
  | "invalid_grant"
  | "token_expired"
  | "token_revoked"
  | "insufficient_scope"
  | "unexpected_scope"
  | "no_eligible_account"
  | "provider_error";

export interface SocialConnection {
  id: string;
  provider: string;
  display_name: string;
  account_type: SocialAccountType;
  status: SocialConnectionStatus;
  connected_at: string | null;
  last_checked_at: string | null;
  safe_error: SocialConnectionError | null;
}

export interface SocialConnectionsResponse {
  enabled: boolean;
  providers: SocialProviderDescriptor[];
  connections: SocialConnection[];
}

export interface SocialAuthorizeResult {
  provider: string;
  authorization_url: string;
}

export type SocialCallbackOutcome = "connected" | "error";

export type SocialCallbackReason =
  "invalid_request" | "denied" | "provider_error" | "unavailable";
