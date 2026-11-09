"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";
import {
  actOnAnomaly,
  actOnRecommendation,
  fetchAnomalyHistory,
  fetchDashboard,
  fetchRecommendations,
  type ActionPayload,
  type Anomaly,
  type AnomalySummary,
  type Dashboard,
  type Recommendation,
} from "@/lib/api";
import { useScrollSpy } from "@/lib/hooks";
import { cn, monthLabel } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AnomaliesPanel, type OnAnomalyAction } from "@/components/dashboard/anomalies";
import { CopilotWidget, type CopilotHandle } from "@/components/dashboard/copilot";
import { Reveal } from "@/components/dashboard/motion";
import { HeroSpend, ServiceBreakdown, SpendTrend, StatStack, useServiceSlices } from "@/components/dashboard/overview";
import { RecommendationsSection } from "@/components/dashboard/recommendations";
import { MobileNav, SECTIONS, Sidebar, ThemeToggle, type ApiStatus } from "@/components/dashboard/shell";
import { DashboardSkeleton, ErrorState, Toast } from "@/components/dashboard/states";

const SECTION_IDS = SECTIONS.map((s) => s.id);

export default function Home() {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [anoms, setAnoms] = useState<Anomaly[]>([]);
  const [anomSummary, setAnomSummary] = useState<AnomalySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const copilot = useRef<CopilotHandle>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [d, r, a] = await Promise.all([fetchDashboard(), fetchRecommendations(), fetchAnomalyHistory()]);
      // Guard against an older backend still running: its responses lack the v2 fields this UI renders.
      if (!d.dataset_id || r.some((x) => !x.savings || !x.priority?.factors) || !Array.isArray(a?.anomalies)) {
        setError("The API on port 8000 is an older version. Stop it and restart the backend (uvicorn app.main:app --reload), then try again.");
        return;
      }
      setDash(d);
      setRecs(r);
      setAnoms(a.anomalies);
      setAnomSummary(a.summary);
    } catch {
      setError("Start the FastAPI backend on port 8000, then try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Lifecycle status lives on the server; "decided" means anything other than open.
  const decisions = useMemo(
    () => Object.fromEntries(recs.filter((r) => r.status !== "open").map((r) => [r.id, r.status])),
    [recs],
  );

  const act = useCallback(async (id: string, payload: ActionPayload) => {
    setPending((p) => ({ ...p, [id]: true }));
    try {
      const updated = await actOnRecommendation(id, payload);
      setRecs((prev) => prev.map((r) => (r.id === id ? updated : r)));
      return true;
    } catch (e) {
      const detail = e instanceof Error && !e.message.startsWith("Failed to fetch") ? ` ${e.message}.` : "";
      setToast(`Could not update the recommendation.${detail} Check that the backend is running and try again.`);
      return false;
    } finally {
      setPending((p) => ({ ...p, [id]: false }));
    }
  }, []);

  const actAnomaly: OnAnomalyAction = useCallback(async (id, payload) => {
    setPending((p) => ({ ...p, [id]: true }));
    try {
      const updated = await actOnAnomaly(id, payload);
      // Refresh the list so statuses and the history summary stay in sync with the server.
      const fresh = await fetchAnomalyHistory();
      setAnoms(fresh.anomalies);
      setAnomSummary(fresh.summary);
      return updated;
    } catch (e) {
      const detail = e instanceof Error && !e.message.startsWith("Failed to fetch") ? ` ${e.message}.` : "";
      setToast(`Could not update the anomaly.${detail} Check that the backend is running and try again.`);
      return null;
    } finally {
      setPending((p) => ({ ...p, [id]: false }));
    }
  }, []);

  const activeAnomalies = anoms.filter((a) => a.is_current && a.status !== "resolved").length;

  function askAbout(question: string) {
    copilot.current?.ask(question);
  }

  const ready = !!dash && !error;
  const [active, setActive] = useScrollSpy(SECTION_IDS, ready);
  const status: ApiStatus = loading && !dash ? "loading" : error ? "offline" : "online";
  const navProps = { active, onNavigate: setActive, onOpenCopilot: () => copilot.current?.open(), status, counts: { recommendations: recs.length, anomalies: activeAnomalies } };
  const clearToast = useCallback(() => setToast(""), []);

  return (
    <div className="min-h-screen">
      <Sidebar {...navProps} />
      <MobileNav {...navProps} />

      <div className="relative isolate lg:pl-[248px]">
        {/* A single faint wash keeps the canvas from feeling flat without decorating it */}
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[420px] bg-[radial-gradient(60%_100%_at_70%_0%,hsl(var(--brand)/0.07),transparent)]" />

        <main className="mx-auto w-full max-w-[1360px] px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pt-10">
          <header id="overview" className="mb-7 flex scroll-mt-24 flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11.5px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Cloud financial intelligence
                {dash && <span className="font-medium normal-case tracking-normal"> · {monthLabel(dash.month)}</span>}
              </p>
              <h1 className="mt-2 font-display text-[38px] leading-none tracking-tight sm:text-[44px]">Cost overview</h1>
              <p className="mt-2 text-[13.5px] text-muted-foreground">Understand spend. Find opportunities. Make informed decisions.</p>
            </div>
            <div className="flex items-center gap-2">
              {dash && (
                <Badge variant="outline" className="hidden h-9 rounded-lg px-3 text-[12px] sm:inline-flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand" />
                  {dash.data_mode}
                </Badge>
              )}
              <ThemeToggle />
              <Button variant="outline" onClick={load} disabled={loading}>
                <RefreshCw className={cn(loading && "animate-spin")} />
                {loading && dash ? "Refreshing…" : "Refresh data"}
              </Button>
            </div>
          </header>

          {loading && !dash ? (
            <DashboardSkeleton />
          ) : error ? (
            <ErrorState message={error} onRetry={load} />
          ) : (
            dash && (
              <DashboardBody
                dash={dash}
                recs={recs}
                anoms={anoms}
                anomSummary={anomSummary}
                decisions={decisions}
                pending={pending}
                onAction={act}
                onAnomalyAction={actAnomaly}
                onAsk={askAbout}
                refreshing={loading}
              />
            )
          )}

          <p className="mt-10 flex items-start gap-2 text-[11.5px] leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Advisory demo only. Validate utilization, workload requirements, pricing and operational risk before acting. No cloud resources are modified.
          </p>
        </main>
      </div>

      <CopilotWidget ref={copilot} />
      <Toast message={toast} onClose={clearToast} />
    </div>
  );
}

function DashboardBody({
  dash,
  recs,
  anoms,
  anomSummary,
  decisions,
  pending,
  onAction,
  onAnomalyAction,
  onAsk,
  refreshing,
}: {
  dash: Dashboard;
  recs: Recommendation[];
  anoms: Anomaly[];
  anomSummary: AnomalySummary | null;
  decisions: Record<string, string>;
  pending: Record<string, boolean>;
  onAction: (id: string, payload: ActionPayload) => Promise<boolean>;
  onAnomalyAction: OnAnomalyAction;
  onAsk: (q: string) => void;
  refreshing: boolean;
}) {
  const slices = useServiceSlices(dash);

  return (
    <div className={cn("grid gap-4 transition-opacity duration-300", refreshing && "opacity-60")} aria-busy={refreshing}>
      <Reveal className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <HeroSpend dash={dash} slices={slices} />
        <StatStack dash={dash} recs={recs} decisions={decisions} />
      </Reveal>

      <Reveal className="grid gap-4 lg:grid-cols-[1.7fr_1fr]" delay={0.05}>
        <SpendTrend dash={dash} anomalies={anoms} />
        <ServiceBreakdown dash={dash} slices={slices} />
      </Reveal>

      <Reveal>
        <section id="recommendations" className="scroll-mt-24 pt-4" aria-label="Recommendations">
          <RecommendationsSection recs={recs} pending={pending} onAction={onAction} onAsk={onAsk} />
        </section>
      </Reveal>

      <Reveal>
        <section id="anomalies" className="scroll-mt-24 pt-4" aria-label="Cost anomalies">
          <AnomaliesPanel history={anoms} summary={anomSummary} pending={pending} onAction={onAnomalyAction} onAsk={onAsk} />
        </section>
      </Reveal>

    </div>
  );
}
