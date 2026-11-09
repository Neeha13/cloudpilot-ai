"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowUp, Bot, Database, Minus, RotateCcw, ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import { askCopilot, type CopilotCard } from "@/lib/api";
import { cn, moneyCents } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Message = { id: number; role: "user" | "assistant"; text: string; cards?: CopilotCard[]; sources?: string[] };

export type CopilotHandle = { ask: (question: string) => void; open: () => void };

const SUGGESTIONS = [
  "Why did my cloud spend increase?",
  "What should I investigate first?",
  "Show me high-risk recommendations",
  "What is causing the EC2 anomaly?",
  "Which recommendations have I dismissed?",
];

function AnswerCard({ card }: { card: CopilotCard }) {
  if (card.type === "anomaly") {
    return (
      <div className="rounded-xl border bg-card p-3.5 text-[12.5px]">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 font-semibold">
            <TrendingUp className="h-3.5 w-3.5 text-warning" /> {card.service} · {card.anomaly_type}
          </span>
          <span className="tnum font-semibold text-warning">+{card.change_percent}% MoM</span>
        </div>
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          {card.severity} severity · {card.deviation_percent > 0 ? "+" : ""}
          {card.deviation_percent}% vs baseline {moneyCents(card.baseline)} ({card.baseline_method.toLowerCase()})
        </p>
        <dl className="tnum mt-2 grid grid-cols-3 gap-2 text-muted-foreground">
          <div>
            <dt className="text-[11px]">Previous</dt>
            <dd className="font-medium text-foreground">{moneyCents(card.previous_cost)}</dd>
          </div>
          <div>
            <dt className="text-[11px]">Current</dt>
            <dd className="font-medium text-foreground">{moneyCents(card.current_cost)}</dd>
          </div>
          <div>
            <dt className="text-[11px]">Difference</dt>
            <dd className="font-medium text-foreground">+{moneyCents(card.difference)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-[11.5px] text-muted-foreground">
          {card.period} · {card.note}
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border bg-card p-3.5 text-[12.5px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[11px] text-muted-foreground">
            {card.service} · {card.resource_id}
          </p>
          <p className="mt-0.5 font-semibold leading-snug">{card.title}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="tnum font-semibold text-brand">{moneyCents(card.monthly_savings)}</p>
          <p className="text-[10.5px] text-muted-foreground">/ month est.</p>
        </div>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground">
        <span>
          Priority <span className="tnum font-medium text-foreground">{card.priority_score}</span>
        </span>
        <span>{card.confidence_level} confidence</span>
        <span className={cn(card.risk_level === "High" && "text-danger", card.risk_level === "Medium" && "text-warning")}>
          <ShieldAlert className="mr-0.5 inline h-3 w-3" />
          {card.risk_level} risk
        </span>
      </p>
      <p className="mt-2 text-muted-foreground">
        <span className="font-medium text-foreground">Why: </span>
        {card.why}
      </p>
      <p className="mt-1 text-muted-foreground">
        <span className="font-medium text-foreground">Next step: </span>
        {card.next_step}
      </p>
      {card.missing_evidence.length > 0 && <p className="mt-1 text-warning">Missing evidence: {card.missing_evidence.join(", ")}</p>}
      <p className="mt-2 font-mono text-[11px] text-muted-foreground">{card.savings_formula}</p>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="CloudPilot is thinking">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-muted-foreground" style={{ animationDelay: `${i * 0.16}s` }} />
      ))}
    </span>
  );
}

/** Rotating gradient edge plus a soft outer glow that marks the assistant as an AI agent. */
function GlowFrame({ className, radius, children }: { className?: string; radius: string; children: React.ReactNode }) {
  return (
    <div className={cn("relative", className)}>
      <div aria-hidden className="ai-glow-gradient pointer-events-none absolute -inset-[3px] opacity-60 blur-xl" style={{ borderRadius: radius }} />
      <div aria-hidden className="ai-glow-gradient pointer-events-none absolute -inset-[1.5px]" style={{ borderRadius: radius }} />
      <div className="relative h-full overflow-hidden bg-card" style={{ borderRadius: radius }}>
        {children}
      </div>
    </div>
  );
}

function BotAvatar({ size = "sm" }: { size?: "sm" | "lg" }) {
  return (
    <span
      className={cn(
        "ai-avatar relative flex shrink-0 items-center justify-center text-white",
        size === "lg" ? "h-10 w-10 rounded-xl" : "h-7 w-7 rounded-lg",
      )}
    >
      <Bot className={size === "lg" ? "h-5 w-5" : "h-3.5 w-3.5"} />
    </span>
  );
}

/** Floating AI assistant: a glowing launcher in the corner that opens a chat panel over the page. */
export const CopilotWidget = forwardRef<CopilotHandle>(function CopilotWidget(_, ref) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const nextId = useRef(0);
  const reduced = useReducedMotion();

  const ask = useCallback(
    async (raw: string) => {
      const q = raw.trim();
      if (!q || loading) return;
      setOpen(true);
      setQuestion("");
      setLoading(true);
      setMessages((m) => [...m, { id: nextId.current++, role: "user", text: q }]);
      let reply: Omit<Message, "id" | "role">;
      try {
        const res = await askCopilot(q);
        reply = { text: res.answer, cards: res.cards, sources: res.sources };
      } catch {
        reply = { text: "The copilot API is unavailable. Check that the backend is running." };
      }
      setMessages((m) => [...m, { id: nextId.current++, role: "assistant", ...reply }]);
      setLoading(false);
    },
    [loading],
  );

  useImperativeHandle(ref, () => ({ ask, open: () => setOpen(true) }), [ask]);

  const close = useCallback(() => {
    setOpen(false);
    launcherRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 120);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [messages, loading, reduced, open]);

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="CloudPilot AI assistant"
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
            style={{ transformOrigin: "bottom right" }}
            className="fixed inset-x-3 bottom-[88px] top-[72px] z-50 sm:inset-x-auto sm:right-6 sm:top-auto sm:h-[min(660px,calc(100vh-130px))] sm:w-[420px]"
          >
            <GlowFrame radius="20px" className="h-full shadow-lift">
              <div className="flex h-full flex-col">
                <header className="flex items-center gap-3 border-b px-4 py-3">
                  <span className="relative">
                    <BotAvatar size="lg" />
                    <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card bg-emerald-400" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-[14.5px] font-semibold leading-tight">
                      CloudPilot AI
                      <span className="rounded-md bg-brand-soft px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-brand">Agent</span>
                    </p>
                    <p className="mt-0.5 text-[11.5px] text-muted-foreground">Your cloud cost assistant · grounded in this dataset</p>
                  </div>
                  {messages.length > 0 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setMessages([])}
                      disabled={loading}
                      aria-label="Start a new conversation"
                      title="New conversation"
                    >
                      <RotateCcw />
                    </Button>
                  )}
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={close} aria-label="Minimize assistant" title="Minimize">
                    <Minus />
                  </Button>
                </header>

                <div ref={scroller} className="scroll-thin flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
                  {messages.length === 0 ? (
                    <div className="flex min-h-full flex-col justify-end gap-4">
                      <div className="flex gap-2.5">
                        <BotAvatar />
                        <div className="rounded-2xl rounded-tl-md bg-muted px-3.5 py-2.5 text-[13px] leading-relaxed">
                          <p className="font-medium">Hi, I&apos;m CloudPilot.</p>
                          <p className="mt-1 text-muted-foreground">
                            I can explain your spend, investigate anomalies and tell you which recommendation to look at first. Every figure I show
                            comes from the scoring engine, never made up.
                          </p>
                        </div>
                      </div>
                      <div className="grid gap-1.5 pl-[38px]">
                        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Try asking</p>
                        {SUGGESTIONS.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => ask(s)}
                            className="flex items-center gap-2 rounded-xl border bg-card px-3 py-2 text-left text-[12.5px] text-foreground/85 transition-colors hover:border-brand/40 hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <Sparkles className="h-3.5 w-3.5 shrink-0 text-brand" />
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <ol className="grid gap-4">
                      <AnimatePresence initial={false}>
                        {messages.map((m) => (
                          <motion.li
                            key={m.id}
                            initial={reduced ? false : { opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.25 }}
                            className={cn("flex gap-2.5", m.role === "user" && "justify-end")}
                          >
                            {m.role === "assistant" && <BotAvatar />}
                            <div className={cn("grid max-w-[88%] gap-2", m.role === "assistant" && "w-full")}>
                              <div
                                className={cn(
                                  "whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
                                  m.role === "user" ? "rounded-br-md bg-primary text-primary-foreground" : "rounded-tl-md bg-muted text-foreground",
                                )}
                              >
                                {m.text}
                              </div>
                              {m.cards?.map((c, i) => <AnswerCard key={i} card={c} />)}
                              {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                                <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                                  <Database className="mt-0.5 h-3 w-3 shrink-0" />
                                  Source: {m.sources.join("; ")}
                                </p>
                              )}
                            </div>
                          </motion.li>
                        ))}
                        {loading && (
                          <motion.li key="typing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex gap-2.5">
                            <BotAvatar />
                            <div className="rounded-2xl rounded-tl-md bg-muted px-4 py-3">
                              <TypingDots />
                            </div>
                          </motion.li>
                        )}
                      </AnimatePresence>
                    </ol>
                  )}
                </div>

                <form
                  className="border-t p-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    ask(question);
                  }}
                >
                  <div className="flex items-center gap-2 rounded-xl border bg-background p-1.5 pl-3.5 transition-[border-color,box-shadow] focus-within:border-brand/50 focus-within:ring-4 focus-within:ring-brand/10">
                    <label htmlFor="copilot-input" className="sr-only">
                      Ask CloudPilot a question
                    </label>
                    <input
                      id="copilot-input"
                      ref={inputRef}
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Ask about spend, anomalies or savings…"
                      maxLength={1000}
                      autoComplete="off"
                      className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted-foreground/70"
                    />
                    <Button
                      type="submit"
                      variant="brand"
                      size="icon"
                      className="h-8 w-8 rounded-lg"
                      disabled={loading || !question.trim()}
                      aria-label="Send question"
                    >
                      <ArrowUp />
                    </Button>
                  </div>
                  <p className="mt-2 text-center text-[10.5px] text-muted-foreground">Advisory answers on synthetic demo data. Verify before acting.</p>
                </form>
              </div>
            </GlowFrame>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Launcher */}
      <motion.div
        className="fixed bottom-5 right-5 z-50 sm:bottom-6 sm:right-6"
        initial={reduced ? false : { opacity: 0, scale: 0.8, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ delay: 0.4, type: "spring", stiffness: 320, damping: 24 }}
      >
        <GlowFrame radius="999px">
          <button
            ref={launcherRef}
            type="button"
            onClick={() => (open ? close() : setOpen(true))}
            aria-expanded={open}
            aria-label={open ? "Minimize CloudPilot AI assistant" : "Open CloudPilot AI assistant"}
            className="group flex h-14 items-center gap-2.5 rounded-full pl-2 pr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:pr-5"
          >
            <span className="ai-avatar flex h-10 w-10 items-center justify-center rounded-full text-white transition-transform group-hover:scale-105">
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={open ? "close" : "bot"}
                  initial={{ rotate: -60, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={{ rotate: 60, opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="flex"
                >
                  {open ? <Minus className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                </motion.span>
              </AnimatePresence>
            </span>
            <span className="hidden text-left sm:block">
              <span className="block text-[13px] font-semibold leading-tight">Ask CloudPilot AI</span>
              <span className="block text-[11px] leading-tight text-muted-foreground">{loading ? "Thinking…" : "Your cost assistant"}</span>
            </span>
          </button>
        </GlowFrame>
      </motion.div>
    </>
  );
});
