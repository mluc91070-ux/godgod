export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  is_demo: boolean;
};

export type SystemStateName =
  | "IDLE"
  | "OBSERVING"
  | "ANALYZING"
  | "HYPOTHESIZING"
  | "TESTING"
  | "REJECTED"
  | "SUPPORTED"
  | "LEARNING";

export type Live = {
  state: SystemStateName;
  is_demo: boolean;
  updated_at: string;
  current_observation: {
    id: string;
    seq: number | null;
    summary: string;
    observed_at: string;
    novelty_score: number | null;
  } | null;
  current_hypothesis: {
    id: string;
    seq: number | null;
    question: string;
    status: string;
    confidence: number | null;
  } | null;
  current_experiment: {
    id: string;
    seq: number | null;
    title: string;
    status: string;
    sample_size: number | null;
  } | null;
  last_event: { event_type: string; message: string; occurred_at: string } | null;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  streaming: boolean;
};

export type Status = {
  name: string;
  version: string;
  environment: string;
  phase: string;
  state: SystemStateName;
  mode: {
    demo_mode: boolean;
    autonomy_level: number;
    autonomy_label: string;
    x_mode: string;
    x_stage: string;
    wallet_execution_enabled: boolean;
    external_content_is_untrusted: boolean;
  };
  memory: {
    embedding_provider: string;
    embedding_model: string | null;
    embedding_dim: number;
    vector_search: boolean;
    semantic: boolean;
    backend: string;
  };
  pipeline: {
    implemented: boolean;
    source: string;
    source_is_demo: boolean;
    window_hours: number;
    detectors: string[];
    llm_in_loop: boolean;
    last_run_at: string | null;
  };
  research: {
    implemented: boolean;
    hypothesis_templates: number;
    critic_version: string;
    critic_checks: string[];
    min_group_size: number;
    unit_of_analysis: string;
    horizons_hours: number[];
    llm_in_loop: boolean;
    last_run_at: string | null;
  };
  collection: {
    live_tokens: number;
    tokens_promoted: number;
    tokens_migrated: number;
    tokens_unrecorded_frame: number;
    migrations_available: boolean;
    live_snapshots: number;
    live_posts: number;
    deepest_history: number;
    needed_to_observe: number;
    observing_live: boolean;
    scheduler_running: boolean;
    scheduler_interval_seconds: number | null;
    last_chain_run_at: string | null;
    last_x_run_at: string | null;
    measuring_since: string | null;
    running_since: string | null;
  };
  providers: { name: string; configured: boolean; implemented: boolean; note: string | null }[];
  counts: Record<string, number>;
  server_time: string;
};

export type Anomaly = {
  id: string;
  observation_id: string | null;
  anomaly_type: string;
  detector: string;
  score: number | null;
  baseline: Record<string, unknown> | null;
  measured: Record<string, unknown> | null;
  detected_at: string;
  is_demo: boolean;
};

export type Observation = {
  id: string;
  seq: number | null;
  kind: string;
  summary: string;
  subject_type: string | null;
  subject_ref: string | null;
  payload: Record<string, unknown> | null;
  novelty_score: number | null;
  importance: number | null;
  confidence: number | null;
  observed_at: string;
  source: string | null;
  llm_reviewed: boolean;
  is_demo: boolean;
  anomalies?: Anomaly[];
};

export type Hypothesis = {
  id: string;
  seq: number | null;
  statement: string;
  question: string;
  variables: Record<string, unknown> | null;
  population: string;
  sample_definition: string;
  timeframe: string;
  baseline: string;
  expected_result: string;
  falsification_condition: string;
  confidence: number | null;
  status: string;
  origin_observation_id: string | null;
  created_at: string;
  is_demo: boolean;
  experiments?: Experiment[];
};

export type ExperimentResult = {
  id: string;
  experiment_id: string;
  outcome: string;
  summary: string;
  metrics: Record<string, number> | null;
  effect_size: number | null;
  p_value: number | null;
  confidence: number | null;
  critic_verdict: string | null;
  critic_notes: string | null;
  critic_checks: Record<string, string> | null;
  limitations: string | null;
  created_at?: string;
  is_demo?: boolean;
};

export type Experiment = {
  id: string;
  seq: number | null;
  hypothesis_id: string;
  title: string;
  method: string;
  features: string[] | null;
  parameters: Record<string, unknown> | null;
  dataset_version: string;
  dataset_hash: string;
  sample_size: number | null;
  train_period: string | null;
  validation_period: string | null;
  out_of_sample_period: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  limitations: string | null;
  is_demo: boolean;
  results?: ExperimentResult[];
  hypothesis?: Hypothesis | null;
};

export type TraceStep = {
  id: string;
  position: number;
  kind: string;
  summary: string;
  ref_type: string | null;
  ref_id: string | null;
  occurred_at: string | null;
};

export type Trace = {
  id: string;
  seq: number | null;
  title: string | null;
  hypothesis_id: string | null;
  experiment_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  steps: TraceStep[];
  is_demo: boolean;
};

export type Pattern = {
  id: string;
  name: string;
  description: string;
  status: string;
  support_count: number;
  contradiction_count: number;
  confidence: number | null;
  first_seen_at: string | null;
  last_confirmed_at: string | null;
  evidence_refs: string[] | null;
};

export type Memory = {
  id: string;
  memory_type: string;
  content: string;
  summary: string | null;
  meta: Record<string, unknown> | null;
  source: string | null;
  confidence: number | null;
  ref_type: string | null;
  ref_id: string | null;
  created_at: string;
  is_demo: boolean;
  embedding_model: string | null;
  has_vector: boolean;
  access_count: number;
};

export type MemoryHit = {
  score: number;
  memory: Memory;
};

export type MemorySearch = {
  query: string;
  method: string;
  vector: boolean;
  semantic: boolean;
  embedding_model: string | null;
  items: MemoryHit[];
  total_candidates: number;
  truncated: boolean;
  is_demo: boolean;
};

export type MemoryCluster = {
  seed_id: string;
  threshold: number;
  method: string;
  items: MemoryHit[];
  is_demo: boolean;
};

export type MemoryDigest = {
  method: string;
  total: number;
  with_vectors: number;
  by_type: Record<string, number>;
  recurring_terms: [string, number][];
  recent_failures: string[];
  sources: Record<string, number>;
  oldest_at: string | null;
  newest_at: string | null;
  note: string;
  is_demo: boolean;
};

export type SystemEvent = {
  id: string;
  seq: number | null;
  event_type: string;
  message: string;
  level: string;
  occurred_at: string;
};

/** One `log` frame from /api/live/stream. `replayed` separates history from now. */
export type StreamEvent = SystemEvent & {
  ref_type: string | null;
  ref_id: string | null;
  is_demo: boolean;
  replayed: boolean;
};

export type AgentInfo = {
  id: string;
  name: string;
  role: string;
  question: string;
  inputs: string[] | null;
  outputs: string[] | null;
  allowed_tools: string[] | null;
  model_role: string | null;
  enabled: boolean;
  implemented: boolean;
  stage: "model" | "beta" | "deterministic";
};

export type Source = {
  id: string;
  kind: string;
  name: string;
  url: string | null;
  description: string | null;
  reliability: number | null;
  last_used_at: string | null;
};

export type TokenInfo = {
  id: string;
  address: string;
  chain: string;
  name: string | null;
  symbol: string | null;
  decimals: number | null;
  launch_time: string | null;
  launchpad: string | null;
  migrated_to_dex: string | null;
  market_cap_usd: number | null;
  liquidity_usd: number | null;
  volume_24h_usd: number | null;
  holders: number | null;
  holder_concentration_top10: number | null;
  source: string | null;
  is_demo: boolean;
};

export type Draft = {
  id: string;
  content_type: string;
  body: string;
  status: string;
  reviewer_verdict: string | null;
  reviewer_notes: string | null;
  rejection_reason: string | null;
  source_kind: string | null;
  source_id: string | null;
  created_at: string;
};
