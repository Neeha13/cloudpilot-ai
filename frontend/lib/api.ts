export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Dashboard = {
  month: string;
  total_spend: number;
  previous_spend: number;
  change_percent: number;
  service_breakdown: Record<string, number>;
  monthly_trend: { month: string; total: number }[];
  data_mode: string;
  dataset_id?: string;
  snapshot_id?: string;
  generated_at?: string;
  comparison?: PeriodComparison;
};

export type PeriodWindow = { period: string; start: string; end: string; days: number; total: number; daily_average: number };

export type PeriodComparison = {
  basis: "full_calendar_month";
  current: PeriodWindow;
  previous: PeriodWindow;
  equivalent_windows: boolean;
  note: string;
};

export type RefreshStatus = "running" | "created" | "unchanged" | "failed";

export type RefreshRun = {
  id: number;
  trigger: "bootstrap" | "manual" | string;
  status: RefreshStatus;
  started_at: string;
  finished_at: string | null;
  previous_snapshot_id: string | null;
  snapshot_id: string | null;
  dataset_id: string | null;
  error: string | null;
};

export type DatasetMeta = {
  snapshot_id: string;
  dataset_id: string;
  snapshot_status: "active" | "superseded";
  seed: number;
  generator_version: string;
  reference_date: string;
  data_source: string;
  data_source_label: string;
  created_at: string;
  activated_at: string;
  superseded_at: string | null;
  billing_period: { start: string; end: string; current: string };
  resource_count: number;
  spend_rows: number;
  freshness: { status: "current" | "stale"; current_calendar_month: string; message: string };
  last_refresh: RefreshRun | null;
};

export type RefreshResult = { status: "created" | "unchanged"; run: RefreshRun; snapshot: DatasetMeta };

export type Level = "High" | "Medium" | "Low";

export type RecStatus = "open" | "investigating" | "planned" | "implemented" | "snoozed" | "dismissed";

export type RecAction = "investigate" | "plan" | "implement" | "snooze" | "dismiss" | "reopen";

export type DismissReason =
  | "business_critical"
  | "incorrect"
  | "already_optimized"
  | "insufficient_information"
  | "not_feasible"
  | "other";

export type ScoreFactor = "savings" | "confidence" | "business_impact" | "ease" | "risk_safety";

export type Recommendation = {
  id: string;
  version: string;
  rule_id: string;
  snapshot_id?: string;
  dataset_id: string;
  resource_id: string;
  service: string;
  region: string;
  environment: string | null;
  owner_team: string | null;
  category: string;
  title: string;
  summary: string;
  detected: string;
  why_it_matters: string;
  suggested_action: string;
  evidence: { label: string; value: string; source: string }[];
  verify_before_acting: string[];
  savings: {
    monthly: number;
    annual: number;
    kind: "estimate";
    method: string;
    formula: string;
    inputs: { monthly_cost: number; reduction_rate: number };
    assumptions: string[];
  };
  confidence: {
    score: number;
    level: Level;
    factors: { name: string; score: number; note: string }[];
    missing_evidence: string[];
    capped_for_missing_evidence: boolean;
  };
  risk: { level: Level; safety_score: number; explanation: string; drivers: string[]; items: string[] };
  effort: { level: "Low" | "Moderate" | "High"; ease_score: number; explanation: string };
  business_impact: { score: number; level: Level; drivers: string[] };
  priority: { score: number; level: Level; factors: Record<ScoreFactor, number>; weights: Record<ScoreFactor, number> };
  status: RecStatus;
  lifecycle: {
    status: RecStatus;
    updated_at: string | null;
    reason: DismissReason | null;
    reason_label?: string | null;
    note: string | null;
    snooze_until: string | null;
  };
  history?: RecEvent[];
  // v1-compatible flat fields
  monthly_savings_estimate: number;
  annual_savings_estimate: number;
};

export type RecEvent = {
  id: number;
  action: RecAction;
  from_status: RecStatus;
  to_status: RecStatus;
  reason: DismissReason | null;
  note: string | null;
  created_at: string;
};

export type Severity = "Critical" | "High" | "Medium" | "Low";
export type AnomalyStatus = "open" | "acknowledged" | "investigating" | "resolved";
export type AnomalyAction = "acknowledge" | "investigate" | "resolve" | "reopen";
export type Resolution = "expected_change" | "fixed" | "false_positive" | "other";

export type Anomaly = {
  id: string;
  snapshot_id?: string;
  type: "spike" | "gradual_growth" | "new_service";
  type_label: string;
  severity: Severity;
  service: string;
  month: string;
  is_current: boolean;
  current_cost: number;
  previous_cost: number | null;
  previous_month: string | null;
  current_month: string;
  mom_percent: number | null;
  change_percent: number;
  baseline: {
    method: string;
    value: number;
    spread: number | null;
    observation_window: { start: string | null; end: string | null; months: number };
  };
  deviation: {
    absolute: number;
    percent: number;
    robust_z: number | null;
    steps_percent: number[] | null;
    cumulative_percent: number | null;
  };
  summary: string;
  explanation: string;
  detected_at: string;
  dataset_id: string;
  detector_version: string;
  status: AnomalyStatus;
  lifecycle: { status: AnomalyStatus; updated_at: string | null; resolution: Resolution | null; resolution_label: string | null; note: string | null };
};

export type AnomalyDetail = Anomaly & {
  investigation: {
    timeline: { month: string; cost: number }[];
    anomaly_month: string;
    baseline_value: number;
    attribution: {
      resources: { id: string; type: string; region: string; environment: string | null; monthly_cost: number }[];
      attributed_cost: number;
      unattributed_cost: number;
      coverage_percent: number | null;
      note: string;
    };
    investigation_areas: string[];
    related_recommendations: { id: string; resource_id: string; title: string; monthly_savings: number; status: RecStatus }[];
    next_step: string;
  };
  history: { id: number; action: AnomalyAction; from_status: AnomalyStatus; to_status: AnomalyStatus; reason: Resolution | null; note: string | null; created_at: string }[];
};

export type AnomalySummary = {
  total: number;
  current: number;
  unresolved: number;
  by_status: Record<AnomalyStatus, number>;
  by_service: Record<string, number>;
  by_severity: Record<Severity, number>;
};

export type CopilotCard =
  | {
      type: "recommendation";
      id: string;
      title: string;
      resource_id: string;
      service: string;
      monthly_savings: number;
      savings_formula: string;
      risk_level: Level;
      confidence_level: Level;
      priority_score: number;
      status: RecStatus;
      why: string;
      next_step: string;
      verify: string[];
      missing_evidence: string[];
      source: string;
    }
  | {
      type: "anomaly";
      id: string;
      service: string;
      anomaly_type: string;
      severity: Severity;
      status: AnomalyStatus;
      baseline: number;
      baseline_method: string;
      deviation_percent: number;
      change_percent: number;
      previous_cost: number;
      current_cost: number;
      difference: number;
      period: string;
      note: string;
      source: string;
    };

export type CopilotAnswer = { answer: string; cards: CopilotCard[]; sources: string[]; mode?: string };

export type ActionPayload = { action: RecAction; reason?: DismissReason; note?: string; snooze_days?: number };

/*
 * Snapshot pinning. The page loads the dashboard first, then pins every other data
 * request (lists, details, Copilot, lifecycle actions) to that snapshot, so one
 * screen can never combine two snapshots even if a refresh happens in between.
 */
let pinnedSnapshot: string | null = null;

export function pinSnapshot(id: string | null) {
  pinnedSnapshot = id;
}

function withSnapshot(path: string): string {
  if (!pinnedSnapshot) return path;
  return `${path}${path.includes("?") ? "&" : "?"}snapshot_id=${encodeURIComponent(pinnedSnapshot)}`;
}

/** Snapshot that actually served a response (header first, body as fallback). */
export function servedSnapshot(res: Response): string | null {
  return res.headers.get("X-Snapshot-Id");
}

async function getJSON<T>(path: string, pinned = true): Promise<T> {
  const res = await fetch(`${API}${pinned ? withSnapshot(path) : path}`);
  if (!res.ok) throw new Error(`${path} responded with ${res.status}`);
  return res.json() as Promise<T>;
}

/** Loads the dashboard from the ACTIVE snapshot (never pinned) and reports which snapshot served it. */
export async function fetchActiveDashboard(): Promise<{ dashboard: Dashboard; snapshotId: string | null }> {
  const res = await fetch(`${API}/api/dashboard`);
  if (!res.ok) throw new Error(`/api/dashboard responded with ${res.status}`);
  const dashboard = (await res.json()) as Dashboard;
  return { dashboard, snapshotId: servedSnapshot(res) ?? dashboard.snapshot_id ?? null };
}

export const fetchDatasetMeta = () => getJSON<DatasetMeta>("/api/dataset");
export const fetchRefreshHistory = (limit = 8) => getJSON<RefreshRun[]>(`/api/dataset/refresh-history?limit=${limit}`, false);

/** Controlled refresh. Throws with the server's explanation when the refresh fails or is already running. */
export async function refreshDataset(): Promise<RefreshResult> {
  const res = await fetch(`${API}/api/dataset/refresh`, { method: "POST" });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string | { message?: string; error?: string } };
    const d = body.detail;
    throw new Error(typeof d === "string" ? d : d?.message ? `${d.message}${d.error ? ` (${d.error})` : ""}` : `Refresh failed (${res.status})`);
  }
  return res.json() as Promise<RefreshResult>;
}

export const fetchDashboard = () => getJSON<Dashboard>("/api/dashboard");
export const fetchRecommendations = () => getJSON<Recommendation[]>("/api/recommendations");
export const fetchAnomalies = () => getJSON<Anomaly[]>("/api/anomalies");
export const fetchAnomalyHistory = () =>
  getJSON<{ anomalies: Anomaly[]; summary: AnomalySummary; snapshot_id?: string }>("/api/anomalies/history");
export const fetchAnomaly = (id: string) => getJSON<AnomalyDetail>(`/api/anomalies/${id}`);

export async function askCopilot(question: string): Promise<CopilotAnswer> {
  const res = await fetch(`${API}${withSnapshot("/api/copilot")}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (res.status === 422)
    return { answer: "Please ask a slightly longer question (at least 2 characters, at most 1,000).", cards: [], sources: [] };
  if (!res.ok) throw new Error(`Copilot responded with ${res.status}`);
  const data = (await res.json()) as Partial<CopilotAnswer>;
  return { answer: data.answer || "The copilot returned an empty answer.", cards: data.cards ?? [], sources: data.sources ?? [] };
}

/** Applies a lifecycle action. Throws with the server's explanation on an invalid transition. */
export async function actOnRecommendation(id: string, payload: ActionPayload): Promise<Recommendation> {
  const res = await fetch(`${API}${withSnapshot(`/api/recommendations/${id}/actions`)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `Action failed (${res.status})`);
  }
  return res.json() as Promise<Recommendation>;
}

export async function actOnAnomaly(
  id: string,
  payload: { action: AnomalyAction; resolution?: Resolution; note?: string },
): Promise<AnomalyDetail> {
  const res = await fetch(`${API}${withSnapshot(`/api/anomalies/${id}/actions`)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `Action failed (${res.status})`);
  }
  return res.json() as Promise<AnomalyDetail>;
}
