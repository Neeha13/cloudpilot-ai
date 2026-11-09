"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, Bot, LayoutDashboard, Menu, Moon, ShieldCheck, Sparkles, Sun, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export type ApiStatus = "loading" | "online" | "offline";

export const SECTIONS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "recommendations", label: "Recommendations", icon: Sparkles },
  { id: "anomalies", label: "Cost anomalies", icon: Activity },
] as const;

type NavProps = {
  active: string;
  onNavigate: (id: string) => void;
  counts: Partial<Record<string, number>>;
  onOpenCopilot: () => void;
};

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="hsl(var(--brand))" />
      <path
        d="M8.5 21.5 14 16l3.6 3L23.5 11.5"
        fill="none"
        stroke="hsl(var(--brand-foreground))"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="23.5" cy="11.5" r="2.3" fill="hsl(var(--brand-foreground))" />
    </svg>
  );
}

function Wordmark() {
  return (
    <a href="#overview" className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <BrandMark className="h-8 w-8" />
      <span className="text-[17px] font-semibold tracking-tight text-sidebar-foreground">
        cloudpilot<span className="text-brand">.</span>
      </span>
    </a>
  );
}

function NavLinks({ active, onNavigate, counts, layoutId, onOpenCopilot }: NavProps & { layoutId: string }) {
  return (
    <nav aria-label="Dashboard sections" className="grid gap-0.5">
      <p className="mb-2 px-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted/70">Workspace</p>
      {SECTIONS.map(({ id, label, icon: Icon }) => {
        const isActive = active === id;
        const count = counts[id];
        return (
          <a
            key={id}
            href={`#${id}`}
            onClick={() => onNavigate(id)}
            aria-current={isActive ? "location" : undefined}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand",
              isActive ? "text-sidebar-foreground" : "text-sidebar-muted hover:text-sidebar-foreground",
            )}
          >
            {isActive && (
              <motion.span
                layoutId={layoutId}
                className="absolute inset-0 rounded-lg bg-sidebar-accent ring-1 ring-inset ring-white/[0.06]"
                transition={{ type: "spring", stiffness: 420, damping: 36 }}
              />
            )}
            <Icon className={cn("relative h-4 w-4 transition-colors", isActive ? "text-brand" : "")} />
            <span className="relative flex-1">{label}</span>
            {count !== undefined && count > 0 && (
              <span className="relative rounded-md bg-white/[0.06] px-1.5 text-[11px] tabular-nums text-sidebar-muted">{count}</span>
            )}
          </a>
        );
      })}
      <p className="mb-2 mt-5 px-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted/70">Assistant</p>
      <button
        type="button"
        onClick={onOpenCopilot}
        className="group relative flex items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] font-medium text-sidebar-muted outline-none transition-colors hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span className="ai-avatar flex h-5 w-5 items-center justify-center rounded-md text-white">
          <Bot className="h-3 w-3" />
        </span>
        <span className="flex-1">Ask CloudPilot AI</span>
        <span className="rounded-md bg-brand/15 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-brand">AI</span>
      </button>
    </nav>
  );
}

function StatusLine({ status }: { status: ApiStatus }) {
  const label = status === "online" ? "API connected" : status === "offline" ? "API unreachable" : "Connecting…";
  return (
    <div className="flex items-center gap-2 text-[12px] text-sidebar-muted" role="status">
      <span className="relative flex h-2 w-2">
        {status === "online" && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/50 motion-reduce:hidden" />}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            status === "online" ? "bg-emerald-400" : status === "offline" ? "bg-red-400" : "bg-amber-400",
          )}
        />
      </span>
      {label}
    </div>
  );
}

function DemoNote() {
  return (
    <div className="rounded-xl border border-sidebar-border bg-white/[0.02] p-3.5">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-sidebar-foreground">
        <ShieldCheck className="h-3.5 w-3.5 text-brand" />
        Demo environment
      </div>
      <p className="mt-2 text-[11.5px] leading-relaxed text-sidebar-muted">
        Synthetic AWS-style data only. No live cloud account is connected and no infrastructure changes are performed.
      </p>
    </div>
  );
}

export function Sidebar(props: NavProps & { status: ApiStatus }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col gap-8 border-r border-sidebar-border bg-sidebar px-4 py-6 lg:flex">
      <div className="px-2">
        <Wordmark />
      </div>
      <NavLinks {...props} layoutId="nav-active-desktop" />
      <div className="mt-auto grid gap-4">
        <DemoNote />
        <div className="px-1">
          <StatusLine status={props.status} />
        </div>
      </div>
    </aside>
  );
}

export function MobileNav(props: NavProps & { status: ApiStatus }) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-sidebar-border bg-sidebar/95 px-4 backdrop-blur lg:hidden">
        <Wordmark />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          aria-expanded={open}
          className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          <Menu />
        </Button>
      </header>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px] lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.div
              ref={panelRef}
              tabIndex={-1}
              role="dialog"
              aria-modal="true"
              aria-label="Navigation"
              className="fixed inset-y-0 left-0 z-50 flex w-[280px] max-w-[85vw] flex-col gap-8 bg-sidebar px-4 py-5 outline-none lg:hidden"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
            >
              <div className="flex items-center justify-between px-2">
                <Wordmark />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation"
                  className="text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
                >
                  <X />
                </Button>
              </div>
              <NavLinks
                {...props}
                layoutId="nav-active-mobile"
                onNavigate={(id) => {
                  props.onNavigate(id);
                  setOpen(false);
                }}
                onOpenCopilot={() => {
                  setOpen(false);
                  props.onOpenCopilot();
                }}
              />
              <div className="mt-auto grid gap-4">
                <DemoNote />
                <div className="px-1">
                  <StatusLine status={props.status} />
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <Button variant="outline" size="icon" onClick={toggle} aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -45, opacity: 0 }}
          animate={{ rotate: 0, opacity: 1 }}
          exit={{ rotate: 45, opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="flex"
        >
          {isDark ? <Sun /> : <Moon />}
        </motion.span>
      </AnimatePresence>
    </Button>
  );
}
