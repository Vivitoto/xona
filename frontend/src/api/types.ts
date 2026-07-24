export const REDACTED_PLACEHOLDER = "********";

export type OrganizationMode =
  | "preview"
  | "in_place"
  | "move"
  | "copy"
  | "hardlink"
  | "symlink";

export interface StorageRootRead {
  id: number;
  path: string;
  source: string;
  enabled: boolean;
}

export interface StorageRootList {
  roots: StorageRootRead[];
}

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseResponse {
  root: StorageRootRead;
  entries: BrowseEntry[];
}

export interface EmbyPathMapping {
  container_root: string;
  emby_root: string;
}

export interface AppSettings {
  storage: {
    roots: string[];
    env_roots: string[];
  };
  xchina: {
    base_url: string;
    flaresolverr_url: string | null;
    proxy_url: string | null;
    cache_dir: string | null;
  };
  emby: {
    enabled: boolean;
    server_url: string | null;
    api_key: string | null;
    path_mappings: EmbyPathMapping[];
    upload_actor_portraits: boolean;
  };
  naming: {
    folder_templates: string[];
    filename_template: string;
  };
  metadata_assets: {
    write_nfo: boolean;
    include_source_snapshot: boolean;
    asset_policy: string;
    max_asset_bytes: number;
  };
  confidence_safety: {
    confidence_threshold: number;
    refuse_destination_collisions: boolean;
    refuse_unresolved_multipart: boolean;
    cache_dir: string | null;
  };
  auth: {
    enabled: boolean;
    username: string | null;
  };
}

export type AppSettingsUpdate = Partial<{
  storage: Partial<AppSettings["storage"]>;
  xchina: Partial<AppSettings["xchina"]>;
  emby: Partial<AppSettings["emby"]>;
  naming: Partial<AppSettings["naming"]>;
  metadata_assets: Partial<AppSettings["metadata_assets"]>;
  confidence_safety: Partial<AppSettings["confidence_safety"]>;
  auth: Partial<AppSettings["auth"]>;
}>;

export interface TemplatePreviewResponse {
  folder_path: string | null;
  filename: string | null;
  validation_errors: string[];
  warnings: string[];
}

export interface ManualMediaItemRead {
  path: string;
  group_key: string;
  identity: string;
  size_bytes: number;
  multipart_index: number | null;
}

export interface ManualJobSummary {
  job_id: number;
  state: string;
  media_identity: string;
  media_items: ManualMediaItemRead[];
}

export interface ManualScanResponse {
  scanned_count: number;
  jobs: ManualJobSummary[];
}

export interface ManualCandidateCard {
  candidate_id: number;
  source: string;
  source_candidate_id: string;
  title: string;
  image_url: string | null;
  actors: string[];
  studio: string | null;
  series: string | null;
  release_date: string | null;
  url: string;
  confidence_score: number;
  score_breakdown: Record<string, number>;
}

export interface ManualSearchResponse {
  job_id: number;
  search_query_id: number;
  query: string;
  normalized_query: string;
  candidates: ManualCandidateCard[];
}

export interface ManualSelectCandidateResponse {
  job_id: number;
  accepted: boolean;
  reasons: string[];
  selected_candidate: ManualCandidateCard | null;
  metadata_record_id: number | null;
  metadata: Record<string, unknown>;
}

export interface OperationFileSnapshot {
  path: string;
  kind: string;
  expected_size_bytes: number | null;
  mtime_ns: number | null;
  sha256: string | null;
  sidecar: boolean;
  materialized_asset: boolean;
  generated_artifact: boolean;
  actor_output: boolean;
}

export interface OperationConflict {
  target_path: string;
  reason: string;
  source_path: string | null;
  allowed: boolean;
}

export interface OperationSafetyWarning {
  code: string;
  message: string;
  path: string | null;
}

export interface OperationStep {
  step_id: string;
  operation: string;
  category: string;
  source_path: string | null;
  target_path: string;
  temp_parent_path: string;
  expected_size_bytes: number | null;
  mtime_ns: number | null;
  sha256: string | null;
  sidecar: boolean;
  materialized_asset: boolean;
  generated_artifact: boolean;
  actor_output: boolean;
  destructive: boolean;
  allow_existing_generated_replacement: boolean;
  metadata: Record<string, unknown>;
}

export interface OperationPlan {
  plan_id: string;
  version: number;
  database_id?: number | null;
  job_id?: number | null;
  mode: OrganizationMode | string;
  destination_root: string;
  target_directory: string;
  source_snapshot: OperationFileSnapshot[];
  materialized_asset_cache_paths: string[];
  steps: OperationStep[];
  conflicts: OperationConflict[];
  safety_warnings: OperationSafetyWarning[];
  created_at: string;
}

export interface ManualPreviewResponse {
  job_id: number;
  plan_id: string;
  metadata: Record<string, unknown>;
  materialized_assets: Record<string, unknown>[];
  missing_assets: Record<string, unknown>[];
  plan: OperationPlan;
}

export interface ManualExecutePlanResponse {
  plan_id: string;
  job_id: number | null;
  state: string;
}

export interface JobSummaryRead {
  id: number;
  state: string;
  media_identity: string;
  rule_id: string | null;
  manual: boolean;
  attempts: number;
  max_attempts: number;
  next_run_at: string | null;
  last_error_code: string | null;
  payload: Record<string, unknown>;
  plan_id: string | null;
  selected_candidate: Record<string, unknown> | null;
  gate_reasons: string[];
  retryable: boolean;
  retry_emby_available: boolean;
}

export interface JobListResponse {
  jobs: JobSummaryRead[];
}

export interface JobEventRead {
  id: number;
  job_id: number;
  from_state: string | null;
  to_state: string;
  payload: Record<string, unknown>;
}

export interface JobEventsResponse {
  events: JobEventRead[];
}

export interface JobActionResponse {
  job: JobSummaryRead;
}

export interface LogEntryRead {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  source: string;
}

export interface LogListResponse {
  entries: LogEntryRead[];
  docker_logs_note: string;
}

export interface HistoryPlanRead {
  plan_id: string;
  job_id: number | null;
  mode: string;
  status: string;
  verification_status: string;
  target_paths: string[];
  created_at: string;
}

export interface HistoryPlansResponse {
  plans: HistoryPlanRead[];
}

export interface RollbackResponse {
  plan_id: string;
  status: string;
  reversed_steps: string[];
  refusal_reason: string | null;
}

export interface WatchRule {
  rule_id: string;
  source_directory: string;
  destination_directory: string;
  recursive: boolean;
  realtime: boolean;
  polling_interval_seconds: number;
  stability_seconds: number;
  stable_check_count: number;
  organization_mode: OrganizationMode | string;
  folder_templates: string[];
  filename_template: string;
  asset_policy: string;
  emby_options: Record<string, unknown>;
  metadata_options: Record<string, unknown>;
  include_patterns: string[];
  exclude_patterns: string[];
  excluded_destination_prefixes: string[];
  confidence_threshold: number;
  enabled: boolean;
}

export interface WatchRuleList {
  rules: WatchRule[];
}

export interface ScanNowResponse {
  rule_id: string;
  enqueued_jobs: number[];
}

export interface ActorRead {
  id: number;
  canonical_name: string;
  aliases: string[];
  source: string;
  source_id: string | null;
  profile_url: string | null;
  portrait_source_url: string | null;
  portrait_cache_path: string | null;
  portrait_sha256: string | null;
  portrait_size_bytes: number | null;
  biography: string | null;
  profile_fields: Record<string, unknown>;
  associated_works: Record<string, unknown>[];
  emby_person_id: string | null;
  linked_works: Record<string, unknown>[];
}

export interface ActorListResponse {
  actors: ActorRead[];
}

export interface ActorPortraitResponse {
  actor: ActorRead;
  sha256: string;
  size_bytes: number;
}

export interface ActorRefreshResponse {
  actor: ActorRead;
  diagnostics: Record<string, unknown>;
}

export interface ActorWorksResponse {
  actor_id: number;
  works: Record<string, unknown>[];
}

export interface ActorSyncEmbyResponse {
  actor: ActorRead;
  uploaded_portrait: boolean;
  diagnostics: Record<string, unknown>;
}
