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
  generated_at?: string;
};

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

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} responded with ${res.status}`);
  return res.json() as Promise<T>;
}

export const fetchDashboard = () => getJSON<Dashboard>("/api/dashboard");
export const fetchRecommendations = () => getJSON<Recommendation[]>("/api/recommendations");
export const fetchAnomalies = () => getJSON<Anomaly[]>("/api/anomalies");
export const fetchAnomalyHistory = () => getJSON<{ anomalies: Anomaly[]; summary: AnomalySummary }>("/api/anomalies/history");
export const fetchAnomaly = (id: string) => getJSON<AnomalyDetail>(`/api/anomalies/${id}`);

export async function askCopilot(question: string): Promise<CopilotAnswer> {
  const res = await fetch(`${API}/api/copilot`, {
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
  const res = await fetch(`${API}/api/recommendations/${id}/actions`, {
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
  const res = await fetch(`${API}/api/anomalies/${id}/actions`, {
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
