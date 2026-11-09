"use client";

import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useInView, useReducedMotion } from "framer-motion";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipProps } from "recharts";
import { ArrowDownRight, ArrowUpRight, Layers, PiggyBank, TrendingUp } from "lucide-react";
import type { Anomaly, Dashboard, Recommendation } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { cn, money, monthLabel, SERVICE_COLORS, shortMonth } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AnimatedNumber } from "./motion";
import type { SceneItem } from "./cost-scene";

const CostScene = dynamic(() => import("./cost-scene"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-lg" />,
});

export type ServiceSlice = SceneItem;

export function useServiceSlices(dash: Dashboard): ServiceSlice[] {
  return useMemo(() => {
    const total = dash.total_spend || 1;
    return Object.entries(dash.service_breakdown)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value], i) => ({ name, value, share: value / total, color: SERVICE_COLORS[i % SERVICE_COLORS.length] }));
  }, [dash]);
}

function DeltaBadge({ percent, label }: { percent: number; label: string }) {
  const up = percent > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <Badge variant={up ? "warning" : "brand"} className="text-[12px]">
      <Icon className="h-3.5 w-3.5" />
      <span className="tnum font-semibold">
        {up ? "+" : ""}
        {percent}%
      </span>
      <span className="font-normal opacity-80">{label}</span>
    </Badge>
  );
}

/* ------------------------------------------------------------------ */
/* Hero                                                                */
/* ------------------------------------------------------------------ */

export function HeroSpend({ dash, slices }: { dash: Dashboard; slices: ServiceSlice[] }) {
  const sceneRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sceneRef, { margin: "100px" });
  const reduced = useReducedMotion() ?? false;
  const { theme } = useTheme();
  const prevMonth = dash.monthly_trend.at(-2)?.month;
  const top = slices[0];

  return (
    <Card className="overflow-hidden">
      <div className="grid md:grid-cols-[1fr_1.1fr]">
        <div className="flex flex-col p-6 sm:p-7">
          <p className="text-[12px] font-medium text-muted-foreground">
            Current period spend · <span className="text-foreground">{monthLabel(dash.month)}</span>
          </p>
          <p className="mt-3 font-display text-[52px] leading-none tracking-tight sm:text-[64px]">
            <AnimatedNumber value={dash.total_spend} format={money} />
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <DeltaBadge percent={dash.change_percent} label={prevMonth ? `vs ${shortMonth(prevMonth)}` : "vs previous"} />
            <span className="text-[12.5px] text-muted-foreground">
              from <span className="tnum">{money(dash.previous_spend)}</span>
            </span>
          </div>

          <div className="min-h-8 flex-1" />
          <dl className="grid grid-cols-2 gap-4 border-t pt-5">
            <div>
              <dt className="text-[11.5px] text-muted-foreground">Largest cost driver</dt>
              <dd className="mt-1 flex items-center gap-2 text-[14px] font-semibold">
                <span className="h-2 w-2 rounded-full" style={{ background: top?.color }} />
                {top?.name}
                <span className="tnum font-normal text-muted-foreground">{top ? Math.round(top.share * 100) : 0}%</span>
              </dd>
            </div>
            <div>
              <dt className="text-[11.5px] text-muted-foreground">Services billed</dt>
              <dd className="tnum mt-1 text-[14px] font-semibold">{slices.length}</dd>
            </div>
          </dl>
        </div>

        <div className="flex flex-col border-t bg-muted/40 md:border-l md:border-t-0">
          <div className="flex items-baseline justify-between gap-3 px-5 pt-4">
            <p className="text-[12px] font-medium">Spend by service</p>
            <p className="text-[11px] text-muted-foreground">Hover a bar to focus</p>
          </div>
          <div
            ref={sceneRef}
            role="img"
            aria-label={`3D bar chart of spend by service: ${slices.map((s) => `${s.name} ${money(s.value)}`).join(", ")}`}
            className="relative h-[250px] md:h-auto md:min-h-[280px] md:flex-1"
          >
            <CostScene items={slices} dark={theme === "dark"} active={inView} reduced={reduced} />
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Stat cards                                                          */
/* ------------------------------------------------------------------ */

function StatCard({
  icon: Icon,
  label,
  children,
  footer,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <Card className="group p-5 transition-shadow duration-200 hover:shadow-lift">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] font-medium text-muted-foreground">{label}</p>
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-muted-foreground transition-colors group-hover:bg-brand-soft group-hover:text-brand">
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>
      <div className="mt-2 text-[26px] font-semibold leading-tight tracking-tight">{children}</div>
      <div className="mt-1.5 text-[12px] text-muted-foreground">{footer}</div>
    </Card>
  );
}

export function StatStack({
  dash,
  recs,
  decisions,
}: {
  dash: Dashboard;
  recs: Recommendation[];
  decisions: Record<string, string>;
}) {
  const monthly = recs.reduce((s, r) => s + r.monthly_savings_estimate, 0);
  const annual = recs.reduce((s, r) => s + r.annual_savings_estimate, 0);
  const services = new Set(recs.map((r) => r.service)).size;
  const reviewed = recs.filter((r) => decisions[r.id]).length;
  const diff = dash.total_spend - dash.previous_spend;
  const pctOfSpend = dash.total_spend ? (monthly / dash.total_spend) * 100 : 0;

  return (
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
      <StatCard icon={TrendingUp} label="Change vs. previous period" footer={<><span className="tnum">{diff >= 0 ? "+" : "−"}{money(Math.abs(diff))}</span> compared with {money(dash.previous_spend)}</>}>
        <span className={cn(dash.change_percent > 0 ? "text-warning" : "text-brand")}>
          <AnimatedNumber value={dash.change_percent} format={(n) => `${n > 0 ? "+" : ""}${n.toFixed(1)}%`} />
        </span>
      </StatCard>
      <StatCard icon={PiggyBank} label="Potential monthly savings" footer={<>≈ <span className="tnum">{money(annual)}</span>/yr · {pctOfSpend.toFixed(1)}% of spend · illustrative</>}>
        <AnimatedNumber value={monthly} format={money} />
      </StatCard>
      <StatCard
        icon={Layers}
        label="Opportunities to review"
        footer={
          <div className="flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
              <div className="h-full rounded-full bg-brand transition-[width] duration-500" style={{ width: `${recs.length ? (reviewed / recs.length) * 100 : 0}%` }} />
            </div>
            <span className="tnum whitespace-nowrap">
              {reviewed}/{recs.length} reviewed · {services} services
            </span>
          </div>
        }
      >
        <AnimatedNumber value={recs.length} format={(n) => Math.round(n).toString()} />
      </StatCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Spend trend                                                         */
/* ------------------------------------------------------------------ */

function TrendTooltip({ active, payload, label, flags }: TooltipProps<number, string> & { flags?: Map<string, Anomaly[]> }) {
  if (!active || !payload?.length) return null;
  const monthFlags = flags?.get(String(label)) ?? [];
  return (
    <div className="rounded-lg border bg-card px-3 py-2 shadow-lift">
      <p className="text-[11px] text-muted-foreground">{monthLabel(String(label))}</p>
      <p className="tnum text-[14px] font-semibold">{money(Number(payload[0].value))}</p>
      {monthFlags.map((a) => (
        <p key={a.id} className="mt-1 flex items-center gap-1.5 text-[11.5px] text-warning">
          <span className="h-1.5 w-1.5 rounded-full bg-warning" />
          {a.service}: {a.type_label.toLowerCase()} ({a.severity})
        </p>
      ))}
    </div>
  );
}

export function SpendTrend({ dash, anomalies = [] }: { dash: Dashboard; anomalies?: Anomaly[] }) {
  const { theme } = useTheme();
  const dark = theme === "dark";
  const data = dash.monthly_trend;
  const avg = data.reduce((s, d) => s + d.total, 0) / (data.length || 1);
  const peak = data.reduce((p, d) => (d.total > p.total ? d : p), data[0] ?? { month: "", total: 0 });
  const axis = dark ? "#8a93a6" : "#7a8294";
  const grid = dark ? "#1f2533" : "#ebe8e1";
  const stroke = dark ? "#5b7cf0" : "#3E63DD";
  const warn = dark ? "#f0a94a" : "#b4651a";
  // Unresolved anomalies, grouped by the month they were detected in.
  const flags = useMemo(() => {
    const m = new Map<string, Anomaly[]>();
    anomalies.filter((a) => a.status !== "resolved").forEach((a) => m.set(a.month, [...(m.get(a.month) ?? []), a]));
    return m;
  }, [anomalies]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div>
          <CardTitle>Spend trend</CardTitle>
          <CardDescription>
            Monthly total across the synthetic dataset · {data.length} months
            {flags.size > 0 && (
              <span className="ml-1 inline-flex items-center gap-1 text-warning">
                · <span className="h-1.5 w-1.5 rounded-full bg-warning" /> anomaly detected
              </span>
            )}
          </CardDescription>
        </div>
        <dl className="flex gap-6 text-right">
          <div>
            <dt className="text-[11px] text-muted-foreground">{data.length}-mo average</dt>
            <dd className="tnum text-[14px] font-semibold">{money(avg)}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-muted-foreground">Peak</dt>
            <dd className="text-[14px] font-semibold">{peak.month ? shortMonth(peak.month) : "—"}</dd>
          </div>
        </dl>
      </CardHeader>
      <CardContent className="flex-1 pt-4">
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 8, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={dark ? 0.3 : 0.18} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={grid} vertical={false} />
              <XAxis dataKey="month" tickFormatter={shortMonth} tick={{ fontSize: 11, fill: axis }} axisLine={false} tickLine={false} dy={6} />
              <YAxis
                tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
                tick={{ fontSize: 11, fill: axis }}
                axisLine={false}
                tickLine={false}
                width={52}
                domain={["dataMin - 600", "dataMax + 400"]}
              />
              <ReferenceLine
                y={avg}
                stroke={axis}
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                label={{ value: "avg", position: "insideTopLeft", fontSize: 10, fill: axis }}
              />
              <Tooltip content={<TrendTooltip flags={flags} />} cursor={{ stroke: axis, strokeOpacity: 0.3 }} />
              <Area
                type="monotone"
                dataKey="total"
                stroke={stroke}
                strokeWidth={2.25}
                fill="url(#spendFill)"
                dot={false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: dark ? "#0f131c" : "#ffffff", fill: stroke }}
                animationDuration={900}
              />
              {data
                .filter((d) => flags.has(d.month))
                .map((d) => (
                  <ReferenceDot
                    key={d.month}
                    x={d.month}
                    y={d.total}
                    r={5.5}
                    fill={warn}
                    stroke={dark ? "#0f131c" : "#ffffff"}
                    strokeWidth={2}
                    ifOverflow="extendDomain"
                  />
                ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Service breakdown                                                   */
/* ------------------------------------------------------------------ */

export function ServiceBreakdown({ dash, slices }: { dash: Dashboard; slices: ServiceSlice[] }) {
  const [activeName, setActiveName] = useState<string | null>(null);
  const active = slices.find((s) => s.name === activeName);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div>
          <CardTitle>Service cost breakdown</CardTitle>
          <CardDescription>{monthLabel(dash.month)} · share of total spend</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5 pt-4">
        <div className="relative mx-auto h-[168px] w-[168px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="value"
                nameKey="name"
                innerRadius={60}
                outerRadius={82}
                paddingAngle={2}
                cornerRadius={3}
                stroke="none"
                onMouseEnter={(_, i) => setActiveName(slices[i]?.name ?? null)}
                onMouseLeave={() => setActiveName(null)}
                animationDuration={800}
              >
                {slices.map((s) => (
                  <Cell key={s.name} fill={s.color} opacity={activeName && activeName !== s.name ? 0.35 : 1} style={{ transition: "opacity 150ms" }} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-[11px] text-muted-foreground">{active ? active.name : "Total"}</span>
            <span className="tnum text-[17px] font-semibold">{money(active ? active.value : dash.total_spend)}</span>
          </div>
        </div>

        <ul className="grid gap-1">
          {slices.map((s) => (
            <li
              key={s.name}
              onMouseEnter={() => setActiveName(s.name)}
              onMouseLeave={() => setActiveName(null)}
              className={cn(
                "grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5 rounded-md px-2 py-1.5 transition-colors",
                activeName === s.name && "bg-muted",
              )}
            >
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: s.color }} />
              <span className="text-[12.5px] font-medium">{s.name}</span>
              <span className="tnum text-right text-[12.5px]">
                {money(s.value)}
                <span className="ml-2 inline-block w-8 text-muted-foreground">{Math.round(s.share * 100)}%</span>
              </span>
              <span />
              <span className="col-span-2 h-1 overflow-hidden rounded-full bg-muted">
                <span className="block h-full rounded-full" style={{ width: `${s.share * 100}%`, background: s.color }} />
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
