export type TrendHomeStatus =
  | "fresh"
  | "stale"
  | "empty"
  | "disabled"
  | "unconfigured"
  | "degraded"
  | "failed";

export interface TrendEvidence {
  source: string;
  source_name: string;
  source_url: string;
  observed_at: string;
}

export interface TrendCard {
  id: string;
  title: string;
  summary: string;
  region: string;
  category: string | null;
  observed_at: string;
  freshness: "fresh" | "stale";
  freshness_score: number;
  total_score: number;
  workspace_relevance?: {
    score: number;
    calculated_at: string;
  };
  evidence: TrendEvidence[];
}

export interface TrendDetailEvidence {
  source: string;
  source_url: string;
  observed_at: string;
  region: string;
  confidence: number;
}

export interface TrendDetail {
  id: string;
  title: string;
  summary: string;
  region: string;
  category: string | null;
  observed_at: string;
  freshness_score: number;
  scoring_version: string;
  component_scores: Record<string, number>;
  total_score: number;
  calculated_at: string;
  workspace_relevance?: {
    score: number;
    component_scores: Record<string, number>;
    calculated_at: string;
  };
  evidence: TrendDetailEvidence[];
}

export interface TrendSourceSummary {
  total: number;
  available: number;
  degraded: number;
  quota_exhausted: number;
  unavailable: number;
  unconfigured: number;
  disabled: number;
}

/**
 * The single scope the manual refresh button collects. It describes the
 * business, never the aggregated cards, and is sent verbatim to
 * `POST /trends/refresh`.
 */
export interface TrendRefreshScope {
  region: string;
  category: string | null;
}

export interface TrendHome {
  status: TrendHomeStatus;
  /** Only the scope the refresh button will collect. Not a card filter. */
  refresh_scope: TrendRefreshScope;
  /** Aggregated visible data, not necessarily `refresh_scope`. */
  updated_at: string | null;
  /** Belongs to `refresh_scope`. */
  refresh_allowed: boolean;
  /** Belongs to `refresh_scope`. */
  next_refresh_at: string | null;
  sources: TrendSourceSummary;
  /**
   * Aggregated, workspace-private list: it may contain cards from several
   * scopes and each card declares its own `region`/`category`.
   */
  items: TrendCard[];
}

export interface TrendSource {
  identifier: string;
  public_name: string;
  source_type: string;
  configured: boolean;
  status:
    | "available"
    | "degraded"
    | "quota_exhausted"
    | "unavailable"
    | "unconfigured"
    | "disabled";
  next_reset_at: string | null;
}

export interface TrendRefreshResult {
  id: string;
  status: string;
  refresh_allowed: boolean;
  next_refresh_at: string | null;
  retry_after_seconds: number | null;
}
