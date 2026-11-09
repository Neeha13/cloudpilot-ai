"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, RefreshCw, ServerCrash, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Layout-matched placeholder so the page doesn't jump when data arrives. */
export function DashboardSkeleton() {
  return (
    <div className="grid gap-4" role="status" aria-label="Loading CloudPilot insights">
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card className="grid overflow-hidden md:grid-cols-[1fr_1.1fr]">
          <div className="space-y-4 p-7">
            <Skeleton className="h-3 w-44" />
            <Skeleton className="h-14 w-56" />
            <Skeleton className="h-6 w-40 rounded-full" />
            <div className="grid grid-cols-2 gap-4 pt-16">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
            </div>
          </div>
          <Skeleton className="m-4 h-[240px] rounded-lg md:h-auto" />
        </Card>
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="space-y-3 p-5">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-7 w-24" />
              <Skeleton className="h-3 w-40" />
            </Card>
          ))}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
        <Card className="space-y-4 p-6">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-[260px]" />
        </Card>
        <Card className="space-y-4 p-6">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mx-auto h-[168px] w-[168px] rounded-full" />
          <Skeleton className="h-24" />
        </Card>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-danger-soft text-danger">
        <ServerCrash className="h-5 w-5" />
      </span>
      <div className="max-w-md">
        <h2 className="text-[16px] font-semibold">Can&apos;t reach the CloudPilot API</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{message}</p>
      </div>
      <Button onClick={onRetry}>
        <RefreshCw /> Try again
      </Button>
    </Card>
  );
}

export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, 6000);
    return () => clearTimeout(t);
  }, [message, onClose]);

  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-24 z-50 flex justify-center sm:inset-x-auto sm:right-6 sm:bottom-24" aria-live="assertive">
      <AnimatePresence>
        {message && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            className="pointer-events-auto flex max-w-sm items-start gap-3 rounded-xl border bg-card p-4 shadow-lift"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
            <p className="text-[13px] leading-relaxed">{message}</p>
            <button onClick={onClose} aria-label="Dismiss" className="rounded text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
