"use client";

import { useId, useMemo, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  BellOff,
  Calculator,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Info,
  ListChecks,
  Loader2,
  MessageSquareText,
  RotateCcw,
  Search,
  Server,
  ShieldAlert,
  X,
} from "lucide-react";
import type { ActionPayload, DismissReason, Level, RecStatus, Recommendation, ScoreFactor } from "@/lib/api";
import { cn, money, moneyCents } from "@/lib/utils";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type OnAction = (id: string, payload: ActionPayload) => Promise<boolean>;

// ------------------------------------------------------------ vocabulary ---

const FACTOR_LABELS: Record<ScoreFactor, string> = {
  savings: "Savings",
  confidence: "Confidence",
  business_impact: "Business impact",
  ease: "Ease",
  risk_safety: "Risk safety",
};

const FACTOR_HELP: Record<ScoreFactor, string> = {
  savings: "Estimated monthly saving, log-scaled; $500/mo or more scores 100.",
  confidence: "Average of evidence completeness, freshness, observation window and signal strength.",
  business_impact: "Higher when the service has an active cost anomaly and the saving is a larger share of its spend.",
  ease: "How quickly and simply the change can be made.",
  risk_safety: "Higher is safer. Lowered for production workloads and missing safeguards.",
};

const DISMISS_REASONS: { value: DismissReason; label: string }[] = [
  { value: "business_critical", label: "Resource is business-critical" },
  { value: "incorrect", label: "Recommendation is incorrect" },
  { value: "already_optimized", label: "Already optimized" },
  { value: "insufficient_information", label: "Not enough information" },
  { value: "not_feasible", label: "Action not feasible" },
  { value: "other", label: "Other" },
];

const STATUS_META: Record<RecStatus, { label: string; variant: BadgeVariant }> = {
  open: { label: "To review", variant: "outline" },
  investigating: { label: "Investigating", variant: "brand" },
  planned: { label: "Planned", variant: "brand" },
  implemented: { label: "Implemented · unverified", variant: "brand" },
  snoozed: { label: "Snoozed", variant: "neutral" },
  dismissed: { label: "Dismissed", variant: "neutral" },
};

const FILTERS: { key: string; label: string; statuses: RecStatus[] | null }[] = [
  { key: "all", label: "All", statuses: null },
  { key: "open", label: "To review", statuses: ["open"] },
  { key: "progress", label: "In progress", statuses: ["investigating", "planned"] },
  { key: "done", label: "Implemented", statuses: ["implemented"] },
  { key: "closed", label: "Dismissed & snoozed", statuses: ["dismissed", "snoozed"] },
];

const SORTS = {
  priority: { label: "Priority score", fn: (r: Recommendation) => r.priority.score },
  savings: { label: "Est. savings", fn: (r: Recommendation) => r.savings.monthly },
  confidence: { label: "Confidence", fn: (r: Recommendation) => r.confidence.score },
  safety: { label: "Lowest risk", fn: (r: Recommendation) => r.risk.safety_score },
} as const;
type SortKey = keyof typeof SORTS;

const riskVariant = (risk: Level): BadgeVariant => (risk === "High" ? "danger" : risk === "Medium" ? "warning" : "brand");
const confidenceVariant = (c: Level): BadgeVariant => (c === "High" ? "brand" : c === "Medium" ? "neutral" : "warning");

const shortDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";

// ------------------------------------------------------------ primitives ---

function PrioritySignal({ level }: { level: Level }) {
  const filled = level === "High" ? 3 : level === "Medium" ? 2 : 1;
  return (
    <span className="inline-flex items-end gap-[2px]" aria-hidden>
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className={cn("w-[3px] rounded-sm", i <= filled ? "bg-foreground/70" : "bg-foreground/15")}
          style={{ height: 3 + i * 3 }}
        />
      ))}
    </span>
  );
}

function ScoreBar({ value, className }: { value: number; className?: string }) {
  return (
    <span className="relative h-1.5 w-full overflow-hidden rounded-full bg-foreground/10" aria-hidden>
      <span className={cn("absolute inset-y-0 left-0 rounded-full bg-brand", className)} style={{ width: `${value}%` }} />
    </span>
  );
}

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-1.5">
      <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground/80">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        {title}
      </h4>
      <div className="text-[12.5px] leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}

// --------------------------------------------------------------- details ---

function RecommendationDetails({ rec, onAsk }: { rec: Recommendation; onAsk: (q: string) => void }) {
  const factors = Object.keys(FACTOR_LABELS) as ScoreFactor[];
  return (
    <div className="mt-3 grid gap-5 rounded-lg bg-muted/60 p-4">
      <Section icon={Search} title="What was detected">
        <p>{rec.detected}</p>
        <p className="mt-1">{rec.why_it_matters}</p>
      </Section>

      <Section icon={ClipboardList} title="Evidence">
        <dl className="grid divide-y divide-border/70 overflow-hidden rounded-md border bg-card">
          {rec.evidence.map((e) => (
            <div key={e.label} className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 px-3 py-1.5">
              <dt className="text-foreground/85">{e.label}</dt>
              <dd className={cn("tnum text-right font-medium", e.value === "Not collected" ? "text-warning" : "text-foreground")}>
                {e.value}
              </dd>
              <dd className="col-span-2 text-[11px] text-muted-foreground/80">{e.source}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section icon={ListChecks} title="Suggested investigation">
        <p>{rec.suggested_action}</p>
      </Section>

      <Section icon={ShieldAlert} title={`Operational risk · ${rec.risk.level}`}>
        <p>{rec.risk.explanation}</p>
        {rec.risk.drivers.length > 0 && <p className="mt-1">Risk drivers: {rec.risk.drivers.join("; ")}.</p>}
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          {rec.risk.items.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      </Section>

      <Section icon={Calculator} title="How the estimate was calculated">
        <p className="rounded-md border bg-card px-3 py-2 font-mono text-[12px] text-foreground">{rec.savings.formula}</p>
        <p className="mt-1.5">{rec.savings.method}</p>
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          {rec.savings.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </Section>

      <Section icon={CheckCircle2} title="Verify before acting">
        <ul className="space-y-1">
          {rec.verify_before_acting.map((v) => (
            <li key={v} className="flex gap-2">
              <span className="mt-[3px] h-3.5 w-3.5 shrink-0 rounded-[4px] border border-foreground/30" aria-hidden />
              {v}
            </li>
          ))}
        </ul>
      </Section>

      <Section icon={Info} title={`Priority score · ${rec.priority.score}`}>
        <div className="grid gap-2">
          {factors.map((f) => (
            <div key={f} className="grid grid-cols-[104px_1fr_auto] items-center gap-3" title={FACTOR_HELP[f]}>
              <span className="text-foreground/85">{FACTOR_LABELS[f]}</span>
              <ScoreBar value={rec.priority.factors[f]} />
              <span className="tnum w-[72px] text-right text-[11.5px]">
                {rec.priority.factors[f]} × {rec.priority.weights[f]}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-3 font-medium text-foreground/85">Confidence {rec.confidence.score}/100 ({rec.confidence.level})</p>
        <ul className="mt-1 space-y-0.5">
          {rec.confidence.factors.map((f) => (
            <li key={f.name}>
              <span className="tnum font-medium text-foreground/80">{f.score}</span> · {f.name}: {f.note}
            </li>
          ))}
        </ul>
        {rec.confidence.capped_for_missing_evidence && (
          <p className="mt-1">Confidence is capped below High because required evidence is missing.</p>
        )}
      </Section>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-[11px] text-muted-foreground">
        <span>
          Rule {rec.rule_id} v{rec.version} · {rec.dataset_id}
        </span>
        <Button size="sm" variant="outline" onClick={() => onAsk(`Why was ${rec.resource_id} flagged?`)}>
          <MessageSquareText /> Ask CloudPilot
        </Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- actions ---

function DismissForm({ busy, onCancel, onSubmit }: { busy: boolean; onCancel: () => void; onSubmit: (r: DismissReason, note: string) => void }) {
  const [reason, setReason] = useState<DismissReason | null>(null);
  const [note, setNote] = useState("");
  const name = useId();
  const needsNote = reason === "other" && !note.trim();
  return (
    <motion.form
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      className="grid w-full gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason && !needsNote) onSubmit(reason, note);
      }}
    >
      <fieldset>
        <legend className="mb-2 text-[12.5px] font-medium">Why are you dismissing this?</legend>
        <div className="flex flex-wrap gap-1.5">
          {DISMISS_REASONS.map((r) => (
            <label
              key={r.value}
              className={cn(
                "cursor-pointer rounded-full border px-2.5 py-1 text-[12px] transition-colors focus-within:ring-2 focus-within:ring-ring",
                reason === r.value ? "border-foreground/50 bg-foreground/[0.06] text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <input type="radio" name={name} value={r.value} className="sr-only" checked={reason === r.value} onChange={() => setReason(r.value)} />
              {r.label}
            </label>
          ))}
        </div>
      </fieldset>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={500}
        placeholder={reason === "other" ? "Describe the reason (required)" : "Optional note for your team"}
        aria-label="Dismissal note"
        className="h-8 rounded-lg border bg-background px-3 text-[12.5px] outline-none focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
      />
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={!reason || needsNote || busy}>
          {busy ? <Loader2 className="animate-spin" /> : <X />} Dismiss
        </Button>
        <Button size="sm" type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </motion.form>
  );
}

function ActionBar({ rec, busy, onAction }: { rec: Recommendation; busy: boolean; onAction: OnAction }) {
  const [mode, setMode] = useState<"idle" | "dismiss" | "snooze">("idle");
  const act = async (payload: ActionPayload) => {
    if (await onAction(rec.id, payload)) setMode("idle");
  };
  const spin = busy ? <Loader2 className="animate-spin" /> : null;
  const s = rec.status;

  if (mode === "dismiss") {
    return <DismissForm busy={busy} onCancel={() => setMode("idle")} onSubmit={(reason, note) => act({ action: "dismiss", reason, note })} />;
  }
  if (mode === "snooze") {
    return (
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        <span className="text-muted-foreground">Snooze for</span>
        {[7, 30, 90].map((d) => (
          <Button key={d} size="sm" variant="outline" disabled={busy} onClick={() => act({ action: "snooze", snooze_days: d })}>
            {d} days
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={() => setMode("idle")} disabled={busy}>
          Cancel
        </Button>
      </div>
    );
  }

  const status = (
    <span className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground" role="status">
      <Badge variant={STATUS_META[s].variant} className="text-[11.5px]">
        {s === "dismissed" ? <X className="h-3 w-3" /> : s === "snoozed" ? <BellOff className="h-3 w-3" /> : <Check className="h-3 w-3" />}
        {STATUS_META[s].label}
      </Badge>
      {s === "dismissed" && rec.lifecycle.reason_label && <span>{rec.lifecycle.reason_label}</span>}
      {s === "snoozed" && rec.lifecycle.snooze_until && <span>until {shortDate(rec.lifecycle.snooze_until)}</span>}
      {rec.lifecycle.updated_at && s !== "snoozed" && <span>· {shortDate(rec.lifecycle.updated_at)}</span>}
    </span>
  );

  const reopen = (
    <Button size="sm" variant="ghost" onClick={() => act({ action: "reopen" })} disabled={busy}>
      <RotateCcw /> Reopen
    </Button>
  );

  return (
    <div className="flex w-full flex-wrap items-center gap-2">
      {s === "open" && (
        <>
          <Button size="sm" onClick={() => act({ action: "investigate" })} disabled={busy}>
            {spin ?? <Search />} Start investigation
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("snooze")} disabled={busy}>
            Snooze
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("dismiss")} disabled={busy}>
            Dismiss…
          </Button>
        </>
      )}
      {s === "investigating" && (
        <>
          {status}
          <span className="ml-auto flex flex-wrap gap-1">
            <Button size="sm" onClick={() => act({ action: "plan" })} disabled={busy}>
              {spin} Mark planned
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("dismiss")} disabled={busy}>
              Dismiss…
            </Button>
            {reopen}
          </span>
        </>
      )}
      {s === "planned" && (
        <>
          {status}
          <span className="ml-auto flex flex-wrap gap-1">
            <Button size="sm" onClick={() => act({ action: "implement" })} disabled={busy}>
              {spin} Mark implemented
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("dismiss")} disabled={busy}>
              Dismiss…
            </Button>
            {reopen}
          </span>
        </>
      )}
      {(s === "implemented" || s === "snoozed" || s === "dismissed") && (
        <>
          {status}
          <span className="ml-auto">{reopen}</span>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ card ---

function RecommendationCard({
  rec,
  rank,
  pending,
  onAction,
  onAsk,
}: {
  rec: Recommendation;
  rank: number;
  pending: boolean;
  onAction: OnAction;
  onAsk: (q: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const reduced = useReducedMotion();
  const closed = rec.status === "dismissed" || rec.status === "snoozed";
  const active = rec.status === "investigating" || rec.status === "planned" || rec.status === "implemented";

  return (
    <motion.article
      layout={!reduced}
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: closed ? 0.66 : 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "group flex flex-col rounded-xl border bg-card p-5 transition-[box-shadow,border-color] duration-200 hover:shadow-lift",
        active && "border-brand/40 ring-1 ring-brand/15",
      )}
      aria-label={`#${rank} ${rec.title} for ${rec.resource_id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
            <span className="tnum font-semibold text-foreground/60">#{rank}</span>
            <Badge variant="outline" className="font-semibold text-foreground">
              {rec.service}
            </Badge>
            <span className="inline-flex items-center gap-1 font-mono text-[11px]">
              <Server className="h-3 w-3" />
              {rec.resource_id}
            </span>
            <span>
              {rec.region}
              {rec.environment && ` · ${rec.environment}`}
            </span>
          </div>
          <h3 className="mt-2.5 text-[14.5px] font-semibold leading-snug tracking-tight">{rec.title}</h3>
        </div>
        <div className="shrink-0 text-right">
          <p className="tnum text-[18px] font-semibold leading-none text-brand">{moneyCents(rec.savings.monthly)}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">/ month est.</p>
          <p className="tnum text-[11px] text-muted-foreground">{money(rec.savings.annual)} / yr</p>
        </div>
      </div>

      <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{rec.summary}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="neutral" className="text-foreground/80" title="Weighted score of savings, confidence, business impact, ease and risk safety">
          <PrioritySignal level={rec.priority.level} />
          Priority <span className="tnum font-semibold">{rec.priority.score}</span>
        </Badge>
        <Badge variant={confidenceVariant(rec.confidence.level)} title={`Confidence ${rec.confidence.score}/100`}>
          <CheckCircle2 className="h-3 w-3" />
          {rec.confidence.level} confidence
        </Badge>
        <Badge variant={riskVariant(rec.risk.level)} title={rec.risk.explanation}>
          <ShieldAlert className="h-3 w-3" />
          {rec.risk.level} risk
        </Badge>
        <Badge variant="outline" title={rec.effort.explanation}>
          {rec.effort.level} effort
        </Badge>
      </div>

      {rec.confidence.missing_evidence.length > 0 && (
        <p className="mt-2.5 flex items-start gap-1.5 text-[12px] text-warning">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Missing evidence: {rec.confidence.missing_evidence.join(", ")}
        </p>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={detailsId}
        className="mt-4 flex items-center gap-1.5 self-start rounded text-[12.5px] font-medium text-foreground/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", open && "rotate-180")} />
        Evidence, calculation &amp; risks
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={detailsId}
            initial={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
            animate={reduced ? { opacity: 1 } : { height: "auto", opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <RecommendationDetails rec={rec} onAsk={onAsk} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-auto pt-4">
        <div className="flex min-h-9 items-center gap-2 border-t pt-4">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={rec.status} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="w-full">
              <ActionBar rec={rec} busy={pending} onAction={onAction} />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </motion.article>
  );
}

// ------------------------------------------------------------- pipeline ---

function DecisionPipeline({ recs }: { recs: Recommendation[] }) {
  const sum = (statuses: RecStatus[]) =>
    recs.filter((r) => statuses.includes(r.status)).reduce((s, r) => s + r.savings.monthly, 0);
  const count = (statuses: RecStatus[]) => recs.filter((r) => statuses.includes(r.status)).length;
  const decided = recs.length - count(["open"]);
  const stages = [
    { label: "To review", value: sum(["open"]), n: count(["open"]) },
    { label: "In progress", value: sum(["investigating", "planned"]), n: count(["investigating", "planned"]) },
    { label: "Implemented · unverified", value: sum(["implemented"]), n: count(["implemented"]) },
    { label: "Dismissed / snoozed", value: sum(["dismissed", "snoozed"]), n: count(["dismissed", "snoozed"]) },
  ];
  return (
    <div className="mb-5 grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
      {stages.map((s) => (
        <div key={s.label} className="bg-card px-4 py-3">
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{s.label}</p>
          <p className="tnum mt-1 text-[16px] font-semibold">
            {money(s.value)}
            <span className="text-[12px] font-normal text-muted-foreground">/mo · {s.n}</span>
          </p>
        </div>
      ))}
      <p className="col-span-full bg-card px-4 py-2 text-[11.5px] text-muted-foreground">
        {decided} of {recs.length} recommendations have a recorded decision. All amounts are estimates; implemented savings are not
        verified against billing data yet.
      </p>
    </div>
  );
}

function ScoringExplainer() {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="mb-4">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded text-[12px] font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info className="h-3.5 w-3.5" /> How is priority scored?
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div id={id} className="mt-2 rounded-lg bg-muted/60 p-4 text-[12.5px] leading-relaxed text-muted-foreground">
          <p className="font-mono text-[12px] text-foreground">Priority = 0.35·Savings + 0.25·Confidence + 0.20·Business impact + 0.10·Ease + 0.10·Risk safety</p>
          <ul className="mt-2 grid gap-1 sm:grid-cols-2">
            {(Object.keys(FACTOR_LABELS) as ScoreFactor[]).map((f) => (
              <li key={f}>
                <span className="font-medium text-foreground/85">{FACTOR_LABELS[f]}:</span> {FACTOR_HELP[f]}
              </li>
            ))}
          </ul>
          <p className="mt-2">
            Each factor is scored 0–100. These weights are an initial product hypothesis, not an industry standard, and have not yet been
            validated with users.
          </p>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- section ---

export function RecommendationsSection({
  recs,
  pending,
  onAction,
  onAsk,
}: {
  recs: Recommendation[];
  pending: Record<string, boolean>;
  onAction: OnAction;
  onAsk: (q: string) => void;
}) {
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<SortKey>("priority");

  const ranks = useMemo(() => new Map(recs.map((r, i) => [r.id, i + 1])), [recs]);
  const visible = useMemo(() => {
    const statuses = FILTERS.find((f) => f.key === filter)?.statuses;
    const list = statuses ? recs.filter((r) => statuses.includes(r.status)) : recs;
    return [...list].sort((a, b) => SORTS[sort].fn(b) - SORTS[sort].fn(a));
  }, [recs, filter, sort]);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>AI optimization opportunities</CardTitle>
          <CardDescription>
            Evidence-backed rules ranked by priority score. Estimated savings are illustrative, not guaranteed.
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <LayoutGroup id="rec-filter">
            <div role="group" aria-label="Filter by status" className="flex flex-wrap rounded-lg bg-muted p-0.5">
              {FILTERS.map((f) => {
                const count = f.statuses ? recs.filter((r) => f.statuses!.includes(r.status)).length : recs.length;
                const selected = filter === f.key;
                return (
                  <button
                    key={f.key}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setFilter(f.key)}
                    className={cn(
                      "relative rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selected ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {selected && (
                      <motion.span
                        layoutId="rec-filter-pill"
                        className="absolute inset-0 rounded-md bg-card shadow-card"
                        transition={{ type: "spring", stiffness: 450, damping: 36 }}
                      />
                    )}
                    <span className="relative">
                      {f.label} <span className="tnum text-muted-foreground">{count}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </LayoutGroup>
          <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="h-8 rounded-lg border bg-card px-2 text-[12px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {(Object.keys(SORTS) as SortKey[]).map((k) => (
                <option key={k} value={k}>
                  {SORTS[k].label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </CardHeader>
      <CardContent>
        {recs.length === 0 ? (
          <p className="rounded-lg border border-dashed p-8 text-center text-[13px] text-muted-foreground">
            No recommendations were generated from the current demo inventory.
          </p>
        ) : (
          <>
            <DecisionPipeline recs={recs} />
            <ScoringExplainer />
            {visible.length === 0 ? (
              <p className="rounded-lg border border-dashed p-8 text-center text-[13px] text-muted-foreground">
                No recommendations in this view.
              </p>
            ) : (
              <motion.div layout className="grid items-start gap-4 md:grid-cols-2">
                <AnimatePresence initial={false}>
                  {visible.map((r) => (
                    <RecommendationCard
                      key={r.id}
                      rec={r}
                      rank={ranks.get(r.id) ?? 0}
                      pending={!!pending[r.id]}
                      onAction={onAction}
                      onAsk={onAsk}
                    />
                  ))}
                </AnimatePresence>
              </motion.div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
