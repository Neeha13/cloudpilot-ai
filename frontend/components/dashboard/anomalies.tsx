"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Eye,
  Loader2,
  MessageSquareText,
  RotateCcw,
  Search,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  fetchAnomaly,
  type Anomaly,
  type AnomalyAction,
  type AnomalyDetail,
  type AnomalyStatus,
  type AnomalySummary,
  type Resolution,
  type Severity,
} from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { cn, money, moneyCents, monthLabel, shortMonth } from "@/lib/utils";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export type OnAnomalyAction = (
  id: string,
  payload: { action: AnomalyAction; resolution?: Resolution; note?: string },
) => Promise<AnomalyDetail | null>;

const SEVERITY_VARIANT: Record<Severity, BadgeVariant> = { Critical: "danger", High: "danger", Medium: "warning", Low: "neutral" };

const STATUS_META: Record<AnomalyStatus, { label: string; variant: BadgeVariant }> = {
  open: { label: "Unreviewed", variant: "outline" },
  acknowledged: { label: "Acknowledged", variant: "neutral" },
  investigating: { label: "Investigating", variant: "brand" },
  resolved: { label: "Resolved", variant: "brand" },
};

const RESOLUTIONS: { value: Resolution; label: string }[] = [
  { value: "expected_change", label: "Expected change" },
  { value: "fixed", label: "Root cause fixed" },
  { value: "false_positive", label: "False positive" },
  { value: "other", label: "Other" },
];

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";

const signed = (n: number | null | undefined, suffix = "%") => (n == null ? "—" : `${n > 0 ? "+" : ""}${n}${suffix}`);

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge variant={SEVERITY_VARIANT[severity]} className={cn(severity === "Critical" && "ring-1 ring-danger/40")}>
      <AlertTriangle className="h-3 w-3" />
      {severity}
    </Badge>
  );
}

// ------------------------------------------------------------------ list ---

function AnomalyRow({ a, selected, onSelect, showMonth }: { a: Anomaly; selected: boolean; onSelect: () => void; showMonth?: boolean }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "grid w-full gap-1.5 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        selected ? "border-foreground/30 bg-muted/70" : "hover:bg-muted/40",
        a.status === "resolved" && "opacity-70",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <span className="text-[13.5px] font-semibold">{a.service}</span>
          <SeverityBadge severity={a.severity} />
        </span>
        <span className={cn("tnum text-[14px] font-semibold", a.severity === "Low" ? "text-foreground/80" : "text-warning")}>
          {signed(a.deviation.percent)}
        </span>
      </span>
      <span className="flex items-center justify-between gap-2 text-[11.5px] text-muted-foreground">
        <span>
          {a.type_label}
          {showMonth && ` · ${monthLabel(a.month)}`}
        </span>
        <span>vs baseline</span>
      </span>
      <span>
        <Badge variant={STATUS_META[a.status].variant} className="text-[10.5px]">
          {STATUS_META[a.status].label}
        </Badge>
      </span>
    </button>
  );
}

// -------------------------------------------------------------- timeline ---

function Timeline({ detail }: { detail: AnomalyDetail }) {
  const { theme } = useTheme();
  const dark = theme === "dark";
  const axis = dark ? "#8a93a6" : "#7a8294";
  const grid = dark ? "#1f2533" : "#ebe8e1";
  const normal = dark ? "#3a4256" : "#cfd4de";
  const flag = dark ? "#f0a94a" : "#b4651a";
  const { timeline, anomaly_month, baseline_value } = detail.investigation;
  return (
    <div className="h-[180px]" role="img" aria-label={`${detail.service} monthly cost with baseline ${money(baseline_value)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={timeline} margin={{ top: 14, right: 8, left: -10, bottom: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="month" tickFormatter={shortMonth} tick={{ fontSize: 11, fill: axis }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 11, fill: axis }} axisLine={false} tickLine={false} width={50} />
          <Tooltip
            cursor={{ fill: axis, fillOpacity: 0.08 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div className="rounded-lg border bg-card px-3 py-2 shadow-lift">
                  <p className="text-[11px] text-muted-foreground">{monthLabel(String(label))}</p>
                  <p className="tnum text-[13px] font-semibold">{moneyCents(Number(payload[0].value))}</p>
                </div>
              ) : null
            }
          />
          <ReferenceLine
            y={baseline_value}
            stroke={axis}
            strokeDasharray="4 4"
            label={{ value: `baseline ${money(baseline_value)}`, position: "insideTopLeft", fontSize: 10, fill: axis }}
          />
          <Bar dataKey="cost" radius={[4, 4, 0, 0]} maxBarSize={36}>
            {timeline.map((t) => (
              <Cell key={t.month} fill={t.month === anomaly_month ? flag : normal} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// --------------------------------------------------------- investigation ---

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-card px-3 py-2.5" title={hint}>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="tnum mt-0.5 text-[13.5px] font-semibold">{value}</dd>
    </div>
  );
}

function ActionBar({ detail, busy, onAction }: { detail: AnomalyDetail; busy: boolean; onAction: OnAnomalyAction }) {
  const [resolving, setResolving] = useState(false);
  const [resolution, setResolution] = useState<Resolution | null>(null);
  const [note, setNote] = useState("");
  const name = useId();
  const s = detail.status;
  const act = async (payload: Parameters<OnAnomalyAction>[1]) => {
    if (await onAction(detail.id, payload)) {
      setResolving(false);
      setResolution(null);
      setNote("");
    }
  };
  const spin = busy ? <Loader2 className="animate-spin" /> : null;

  if (resolving) {
    const needsNote = resolution === "other" && !note.trim();
    return (
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (resolution && !needsNote) act({ action: "resolve", resolution, note });
        }}
      >
        <fieldset>
          <legend className="mb-2 text-[12.5px] font-medium">How was this anomaly resolved?</legend>
          <div className="flex flex-wrap gap-1.5">
            {RESOLUTIONS.map((r) => (
              <label
                key={r.value}
                className={cn(
                  "cursor-pointer rounded-full border px-2.5 py-1 text-[12px] transition-colors focus-within:ring-2 focus-within:ring-ring",
                  resolution === r.value ? "border-foreground/50 bg-foreground/[0.06] text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <input type="radio" name={name} className="sr-only" checked={resolution === r.value} onChange={() => setResolution(r.value)} />
                {r.label}
              </label>
            ))}
          </div>
        </fieldset>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          placeholder={resolution === "other" ? "Describe the resolution (required)" : "What did you find? (optional)"}
          aria-label="Resolution note"
          className="h-8 rounded-lg border bg-background px-3 text-[12.5px] outline-none focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
        />
        <div className="flex gap-2">
          <Button size="sm" type="submit" disabled={!resolution || needsNote || busy}>
            {spin ?? <CheckCircle2 />} Resolve
          </Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setResolving(false)} disabled={busy}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={STATUS_META[s].variant} className="text-[11.5px]">
        {STATUS_META[s].label}
      </Badge>
      {s === "resolved" && detail.lifecycle.resolution_label && (
        <span className="text-[12px] text-muted-foreground">
          {detail.lifecycle.resolution_label}
          {detail.lifecycle.note && ` · “${detail.lifecycle.note}”`}
        </span>
      )}
      <span className="ml-auto flex flex-wrap gap-1">
        {s === "open" && (
          <Button size="sm" variant="ghost" onClick={() => act({ action: "acknowledge" })} disabled={busy}>
            <Eye /> Acknowledge
          </Button>
        )}
        {(s === "open" || s === "acknowledged") && (
          <Button size="sm" onClick={() => act({ action: "investigate" })} disabled={busy}>
            {spin ?? <Search />} Start investigation
          </Button>
        )}
        {s !== "resolved" && (
          <Button size="sm" variant={s === "investigating" ? "default" : "ghost"} onClick={() => setResolving(true)} disabled={busy}>
            <CheckCircle2 /> Resolve…
          </Button>
        )}
        {s !== "open" && (
          <Button size="sm" variant="ghost" onClick={() => act({ action: "reopen" })} disabled={busy}>
            <RotateCcw /> Reopen
          </Button>
        )}
      </span>
    </div>
  );
}

function Investigation({
  detail,
  busy,
  onAction,
  onAsk,
}: {
  detail: AnomalyDetail;
  busy: boolean;
  onAction: OnAnomalyAction;
  onAsk: (q: string) => void;
}) {
  const inv = detail.investigation;
  const att = inv.attribution;
  const window = detail.baseline.observation_window;
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
            <SeverityBadge severity={detail.severity} />
            {detail.type_label} · {monthLabel(detail.month)}
          </p>
          <h3 className="mt-2 text-[17px] font-semibold tracking-tight">{detail.service} spending anomaly</h3>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{detail.summary}</p>
        </div>
        <div className="text-right">
          <p className="tnum text-[24px] font-semibold leading-none text-warning">{signed(detail.deviation.percent)}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">vs {window.months}-month baseline</p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
        <Metric label="Baseline (median)" value={moneyCents(detail.baseline.value)} hint={detail.baseline.method} />
        <Metric label={`Current · ${shortMonth(detail.month)}`} value={moneyCents(detail.current_cost)} />
        <Metric label="Difference" value={`${detail.deviation.absolute >= 0 ? "+" : ""}${moneyCents(detail.deviation.absolute)}`} />
        <Metric
          label="Robust z-score"
          value={detail.deviation.robust_z == null ? "—" : String(detail.deviation.robust_z)}
          hint="How many robust standard deviations above the baseline. 3 or more is treated as unusual."
        />
        <Metric
          label="Month over month"
          value={signed(detail.mom_percent)}
          hint={detail.previous_month ? `vs ${monthLabel(detail.previous_month)}` : undefined}
        />
        <Metric
          label="Observation window"
          value={window.start && window.end ? `${shortMonth(window.start)}–${shortMonth(window.end)}` : "—"}
          hint={`${window.months} months before the anomaly month`}
        />
        <Metric label="Detected" value={fmtDate(detail.detected_at)} />
        <Metric label="Detector" value={`v${detail.detector_version}`} hint={detail.dataset_id} />
      </dl>

      <section>
        <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground/80">Monthly {detail.service} cost</h4>
        <Timeline detail={detail} />
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        <section>
          <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground/80">Resource attribution</h4>
          <div className="mb-2 flex items-center gap-2 text-[12px] text-muted-foreground">
            <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-foreground/10">
              <span className="absolute inset-y-0 left-0 rounded-full bg-brand" style={{ width: `${Math.min(att.coverage_percent ?? 0, 100)}%` }} />
            </span>
            <span className="tnum">{att.coverage_percent ?? 0}% attributed</span>
          </div>
          {att.resources.length > 0 ? (
            <ul className="divide-y overflow-hidden rounded-md border text-[12.5px]">
              {att.resources.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 px-3 py-1.5">
                  <span>
                    <span className="font-mono text-[11.5px]">{r.id}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {r.type}
                      {r.environment && ` · ${r.environment}`}
                    </span>
                  </span>
                  <span className="tnum font-medium">{moneyCents(r.monthly_cost)}</span>
                </li>
              ))}
              <li className="flex items-center justify-between gap-2 bg-muted/50 px-3 py-1.5 text-muted-foreground">
                <span>Not attributed</span>
                <span className="tnum">{moneyCents(att.unattributed_cost)}</span>
              </li>
            </ul>
          ) : (
            <p className="text-[12.5px] text-muted-foreground">No resources for this service in the inventory.</p>
          )}
          <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">{att.note}</p>
        </section>

        <section>
          <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground/80">Investigation areas</h4>
          <ul className="space-y-1 text-[12.5px] text-muted-foreground">
            {inv.investigation_areas.map((x) => (
              <li key={x} className="flex gap-2">
                <span className="mt-[3px] h-3.5 w-3.5 shrink-0 rounded-[4px] border border-foreground/30" aria-hidden />
                {x}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12.5px]">
            <span className="font-medium">Next step: </span>
            <span className="text-muted-foreground">{inv.next_step}</span>
          </p>
          {inv.related_recommendations.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground/80">Related recommendations</h4>
              <ul className="grid gap-1.5">
                {inv.related_recommendations.map((r) => (
                  <li key={r.id}>
                    <a
                      href="#recommendations"
                      className="flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-[12.5px] hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span className="font-mono text-[11.5px]">{r.resource_id}</span>
                      <span className="tnum flex items-center gap-1 text-brand">
                        {moneyCents(r.monthly_savings)}/mo <ArrowRight className="h-3 w-3" />
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      <p className="flex items-start gap-2 rounded-lg bg-muted/60 p-3 text-[12px] leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        An anomaly means unusual spend compared with the baseline. It is not proof of waste or of a specific cause.
      </p>

      <div className="grid gap-3 border-t pt-4">
        <ActionBar key={detail.id} detail={detail} busy={busy} onAction={onAction} />
        <div>
          <Button size="sm" variant="outline" onClick={() => onAsk(`What is causing the ${detail.service} anomaly?`)}>
            <MessageSquareText /> Ask CloudPilot
          </Button>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- panel ---

function FrequencyByService({ summary }: { summary: AnomalySummary }) {
  const entries = Object.entries(summary.by_service);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <div className="rounded-lg border p-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Frequency by service</p>
      <ul className="mt-2 grid gap-1.5 text-[12px]">
        {entries.map(([svc, n]) => (
          <li key={svc} className="grid grid-cols-[80px_1fr_auto] items-center gap-2">
            <span>{svc}</span>
            <span className="relative h-1.5 overflow-hidden rounded-full bg-foreground/10">
              <span className="absolute inset-y-0 left-0 rounded-full bg-warning" style={{ width: `${(n / max) * 100}%` }} />
            </span>
            <span className="tnum text-muted-foreground">{n}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11.5px] text-muted-foreground">
        {summary.unresolved} unresolved · {summary.by_status.resolved} resolved
      </p>
    </div>
  );
}

export function AnomaliesPanel({
  history,
  summary,
  pending,
  onAction,
  onAsk,
}: {
  history: Anomaly[];
  summary: AnomalySummary | null;
  pending: Record<string, boolean>;
  onAction: OnAnomalyAction;
  onAsk: (q: string) => void;
}) {
  const [tab, setTab] = useState<"current" | "history">("current");
  const current = useMemo(() => history.filter((a) => a.is_current), [history]);
  const list = tab === "current" ? current : history;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnomalyDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const reduced = useReducedMotion();

  const selected = list.find((a) => a.id === selectedId) ?? list[0] ?? null;
  // Status stamp of the selected item, so an action re-fetches its detail.
  const stamp = selected ? `${selected.id}|${selected.status}|${selected.lifecycle.updated_at}` : "";

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoadError(false);
    fetchAnomaly(selected.id)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setLoadError(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stamp]);

  const counts = { current: current.length, history: history.length };
  const active = current.filter((a) => a.status !== "resolved");

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            Cost anomalies
            {active.length > 0 && <Badge variant="warning">{active.length} active</Badge>}
          </CardTitle>
          <CardDescription>
            Each service is compared against its median spend over the prior months. Flags show unusual spend, not confirmed waste.
          </CardDescription>
        </div>
        <LayoutGroup id="anom-tabs">
          <div role="tablist" aria-label="Anomaly view" className="flex rounded-lg bg-muted p-0.5">
            {(["current", "history"] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => {
                  setTab(t);
                  setSelectedId(null);
                }}
                className={cn(
                  "relative rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  tab === t ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tab === t && (
                  <motion.span layoutId="anom-tab-pill" className="absolute inset-0 rounded-md bg-card shadow-card" transition={{ type: "spring", stiffness: 450, damping: 36 }} />
                )}
                <span className="relative">
                  {t === "current" ? "This month" : "History"} <span className="tnum text-muted-foreground">{counts[t]}</span>
                </span>
              </button>
            ))}
          </div>
        </LayoutGroup>
      </CardHeader>
      <CardContent>
        {list.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center">
            <CheckCircle2 className="h-5 w-5 text-brand" />
            <p className="text-[13px] font-medium">No anomalies detected</p>
            <p className="text-[12px] text-muted-foreground">This does not guarantee spending is normal.</p>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
            <div className="grid content-start gap-2">
              {list.map((a) => (
                <AnomalyRow key={a.id} a={a} selected={selected?.id === a.id} onSelect={() => setSelectedId(a.id)} showMonth={tab === "history"} />
              ))}
              {tab === "history" && summary && <FrequencyByService summary={summary} />}
              <p className="flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground">
                <TrendingUp className="h-3.5 w-3.5" /> Deviation is measured against the baseline median.
              </p>
            </div>
            <div className="min-w-0 rounded-xl border p-4 sm:p-5" aria-live="polite">
              <AnimatePresence mode="wait" initial={false}>
                {loadError ? (
                  <p key="err" className="text-[13px] text-muted-foreground">
                    Could not load the investigation details. Check that the backend is running.
                  </p>
                ) : detail && selected && detail.id === selected.id ? (
                  <motion.div key={detail.id} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                    <Investigation detail={detail} busy={!!pending[detail.id]} onAction={onAction} onAsk={onAsk} />
                  </motion.div>
                ) : (
                  <div key="loading" className="grid gap-3" role="status" aria-label="Loading investigation">
                    <Skeleton className="h-5 w-48" />
                    <Skeleton className="h-4 w-full max-w-md" />
                    <Skeleton className="h-24" />
                    <Skeleton className="h-[180px]" />
                  </div>
                )}
              </AnimatePresence>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
