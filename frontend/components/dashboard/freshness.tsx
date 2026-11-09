"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, ChevronDown, CircleSlash, Database, Loader2, XCircle } from "lucide-react";
import type { DatasetMeta, RefreshRun, RefreshStatus } from "@/lib/api";
import { cn, monthLabel } from "@/lib/utils";

export function formatTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const RUN_STYLE: Record<RefreshStatus, { label: string; icon: typeof CheckCircle2; className: string }> = {
  created: { label: "New snapshot", icon: CheckCircle2, className: "text-brand" },
  unchanged: { label: "No change", icon: CircleSlash, className: "text-muted-foreground" },
  failed: { label: "Failed", icon: XCircle, className: "text-danger" },
  running: { label: "Running", icon: Loader2, className: "text-muted-foreground" },
};

/**
 * Header pill showing which snapshot the page is reading and how fresh it is.
 * Opens a panel with snapshot details and the recent refresh history.
 */
export function DataFreshness({ meta, runs, refreshing }: { meta: DatasetMeta | null; runs: RefreshRun[]; refreshing: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!meta) return null;
  const stale = meta.freshness.status === "stale";

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="inline-flex h-9 items-center gap-2 rounded-lg border bg-card px-3 text-[12px] transition-colors hover:bg-muted"
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", refreshing ? "animate-pulse bg-muted-foreground" : stale ? "bg-warning" : "bg-brand")} />
        <span className="hidden font-medium sm:inline">{meta.data_source_label}</span>
        <span className="text-muted-foreground">
          <span className="hidden sm:inline">· </span>
          {refreshing ? "Refreshing…" : stale ? "New month available" : `Updated ${formatTime(meta.created_at)}`}
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Data snapshot details"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 z-40 mt-2 w-[min(360px,calc(100vw-32px))] rounded-xl border bg-card p-4 text-[12.5px] shadow-lift"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-muted-foreground" />
                <p className="font-semibold">Data snapshot</p>
              </div>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[11px] font-medium",
                  stale ? "bg-warning-soft text-warning" : "bg-brand-soft text-brand",
                )}
              >
                {stale ? "Stale" : "Current"}
              </span>
            </div>
            <p className="mt-2 leading-relaxed text-muted-foreground">{meta.freshness.message}</p>

            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted-foreground">Billing period</dt>
              <dd className="text-right">
                {monthLabel(meta.billing_period.start)} – {monthLabel(meta.billing_period.end)}
              </dd>
              <dt className="text-muted-foreground">Data generated</dt>
              <dd className="text-right tnum">{formatTime(meta.created_at)}</dd>
              <dt className="text-muted-foreground">Last checked</dt>
              <dd className="text-right tnum">{formatTime(meta.last_refresh?.finished_at ?? meta.activated_at)}</dd>
              <dt className="text-muted-foreground">Records</dt>
              <dd className="text-right tnum">
                {meta.spend_rows} billing · {meta.resource_count} resources
              </dd>
              <dt className="text-muted-foreground">Snapshot</dt>
              <dd className="truncate text-right font-mono text-[11px]" title={meta.snapshot_id}>{meta.snapshot_id}</dd>
              <dt className="text-muted-foreground">Dataset</dt>
              <dd className="truncate text-right font-mono text-[11px]" title={meta.dataset_id}>{meta.dataset_id}</dd>
            </dl>

            <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Refresh history</p>
            <ul className="mt-2 max-h-[180px] space-y-1.5 overflow-y-auto scroll-thin pr-1">
              {runs.length === 0 && <li className="text-muted-foreground">No refreshes recorded yet.</li>}
              {runs.map((r) => {
                const s = RUN_STYLE[r.status] ?? RUN_STYLE.running;
                const Icon = s.icon;
                return (
                  <li key={r.id} className="rounded-lg border px-2.5 py-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn("inline-flex items-center gap-1.5 font-medium", s.className)}>
                        <Icon className={cn("h-3.5 w-3.5", r.status === "running" && "animate-spin")} />
                        {s.label}
                      </span>
                      <span className="tnum text-muted-foreground">
                        {formatTime(r.finished_at ?? r.started_at)} · {r.trigger}
                      </span>
                    </div>
                    {r.status === "failed" && r.error && (
                      <p className="mt-1 line-clamp-2 text-[11.5px] text-muted-foreground" title={r.error}>
                        {r.error}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
              Refresh regenerates the synthetic dataset. Identical data keeps the current snapshot, and a failed refresh never
              replaces it. Every figure on this page comes from the snapshot above.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
