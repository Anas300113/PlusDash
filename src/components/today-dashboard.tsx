"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Calculator, Check, Circle, Clock3, LoaderCircle, MessageSquareText, RefreshCw } from "lucide-react";
import { DailyRing } from "@/components/progress-indicators";
import { useSession } from "@/components/session-provider";
import { apiGet } from "@/lib/client-api";
import { weekDays } from "@/lib/data";

const demoPlan = [
  { title: "Maths: fractions", detail: "10 questions, done", href: "/learn/maths", status: "done", label: "Completed" },
  { title: "Verbal reasoning: odd one out", detail: "8 questions, 5 to go", href: "/practice?subject=verbal-reasoning&topic=odd-one-out", status: "current", label: "Continue" },
  { title: "Review: 6 cards due", detail: "About 4 minutes", href: "/review", status: "upcoming", label: "Start review" },
] as const;

type PlanItem = { id: string; title: string; detail: string; href: string; done: boolean; inProgress: boolean };
type DashboardData = {
  displayName: string;
  streakDays: number;
  dailyMinutes: number;
  dailyTargetMinutes: number;
  plan: PlanItem[];
  completedCount: number;
  dueCount: number;
  continueHref: string;
  hasActiveSession: boolean;
  minutesByDay: { date: string; label: string; state: "complete" | "today" | "upcoming" | "missed"; minutes: number }[];
};

const planIcons = [Calculator, MessageSquareText, RefreshCw];

export function TodayDashboard() {
  const { status, csrfToken, error: sessionError, refresh: refreshSession } = useSession();
  const reduceMotion = useReducedMotion();
  const [dashboardRecord, setDashboardRecord] = useState<{ key: string; data: DashboardData } | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = status === "authenticated" && csrfToken ? `${csrfToken}:${reloadKey}` : null;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let current = true;
    void apiGet<DashboardData>("/api/learner/dashboard").then((data) => {
      if (current) setDashboardRecord({ key: `${csrfToken}:${reloadKey}`, data });
    }).catch((reason: unknown) => {
      if (current) setLoadError({ key: `${csrfToken}:${reloadKey}`, message: reason instanceof Error ? reason.message : "We couldn’t load your learning just now." });
    });
    return () => { current = false; };
  }, [status, csrfToken, reloadKey]);

  const dashboard = requestKey && dashboardRecord?.key === requestKey ? dashboardRecord.data : null;
  const dashboardError = requestKey && loadError?.key === requestKey ? loadError.message : null;

  if (status === "loading" || (status === "authenticated" && dashboard === null && !dashboardError)) {
    return <div className="page-stack today-page" aria-live="polite"><section className="page-intro"><h1 className="page-title">Your day, one step at a time</h1><p>Getting your learning ready…</p></section><div className="account-state-card"><LoaderCircle className="account-spinner" size={22} aria-hidden="true" /> Loading your learning</div></div>;
  }

  if (status === "error" || dashboardError) {
    return <div className="page-stack today-page"><section className="page-intro"><h1 className="page-title">Your day, one step at a time</h1><p>We couldn’t load your learning just now.</p></section><section className="account-state-card" role="alert"><p>{status === "error" ? sessionError : dashboardError}</p><button className="button button-secondary" onClick={() => status === "error" ? void refreshSession() : setReloadKey((key) => key + 1)}>Try again</button></section></div>;
  }

  const isLearner = status === "authenticated" && dashboard !== null;
  const minutes = isLearner ? dashboard.dailyMinutes : 18;
  const target = isLearner ? dashboard.dailyTargetMinutes : 30;
  const remaining = Math.max(0, target - minutes);
  const plan = isLearner ? dashboard.plan.map((item) => ({
    ...item,
    status: item.done ? "done" : item.inProgress ? "current" : "upcoming",
    label: item.done ? "Completed" : item.inProgress ? "Continue" : item.id === "review" && dashboard.dueCount === 0 ? "No cards due" : "Start",
  })) : demoPlan;
  const completedCount = isLearner ? dashboard.completedCount : 1;
  const days = isLearner ? dashboard.minutesByDay : weekDays.map((day) => ({ ...day, date: day.label, minutes: 0 }));
  const continueLabel = isLearner && dashboard.continueHref === "/learn"
    ? "Choose a topic"
    : isLearner && !dashboard.hasActiveSession ? "Start practice" : "Continue practice";

  return (
    <div className="page-stack today-page">
      <section className="greeting-block" aria-labelledby="greeting-title">
        <h1 id="greeting-title" className="greeting-title">Hi <span className="highlight-underline">{isLearner ? dashboard.displayName : "Sam"}</span>,</h1>
        <p className="greeting-subtitle">ready for a quick one?</p>
        {!isLearner ? <span className="demo-label">Example progress</span> : null}
      </section>

      <motion.section
        className="continue-card"
        aria-label="Daily practice progress"
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.24, ease: [0.22, 1, 0.36, 1] }}
      >
        <DailyRing value={Math.min(100, minutes / target * 100)} minutes={minutes} target={target} label={`${minutes} of ${target} minutes practised today`} />
        <div className="continue-copy">
          <p className="continue-message">{remaining > 0 ? <>Nearly there. <span>{remaining} minutes</span> to go.</> : "Daily goal reached. Nice work."}</p>
          <Link className="button button-primary" href={isLearner ? dashboard.continueHref : "/practice?subject=verbal-reasoning&topic=odd-one-out"}>
            {continueLabel} <ArrowRight size={17} strokeWidth={2} aria-hidden="true" />
          </Link>
        </div>
        <Image className="owl-peek" src="/plus11-mark.svg" alt="" aria-hidden="true" width={38} height={38} />
      </motion.section>

      <section className="plan-section" aria-labelledby="plan-heading">
        <div className="section-heading-row">
          <h2 id="plan-heading" className="section-title">Today’s plan</h2>
          <span className="section-progress">{completedCount} of {plan.length} done</span>
        </div>
        <div className="plan-list">
          {plan.map(({ title, detail, href, status: planStatus, label }, index) => {
            const Icon = planIcons[index];
            return (
              <Link className={`plan-row plan-${planStatus}`} href={href} key={title}>
                <span className="plan-icon"><Icon size={20} strokeWidth={2} aria-hidden="true" /></span>
                <span className="plan-copy"><span className="plan-title">{title}</span><span className="plan-detail">{detail}</span></span>
                <span className={`plan-status status-${planStatus}`} aria-label={label}>
                  {planStatus === "done" ? <Check size={17} strokeWidth={2.5} aria-hidden="true" /> : planStatus === "current" ? <span className="status-dot" aria-hidden="true" /> : <Circle size={21} strokeWidth={1.8} aria-hidden="true" />}
                </span>
                {index === 1 && planStatus === "current" ? <span className="sr-only">Current activity. Open to continue.</span> : null}
              </Link>
            );
          })}
        </div>
      </section>

      <section className="week-section" aria-labelledby="week-heading">
        <div className="section-heading-row week-heading-row">
          <h2 id="week-heading" className="section-title">Your week</h2>
          <span className="week-note"><Clock3 size={15} aria-hidden="true" /> Little steps add up</span>
        </div>
        <div className="week-strip" role="list" aria-label="Weekly practice streak">
          {days.map(({ label, state, minutes: dayMinutes }) => (
            <div className={`week-day day-${state}`} role="listitem" key={label} aria-label={`${label}: ${state === "complete" ? "practice complete" : state === "today" ? dayMinutes > 0 ? `today, ${dayMinutes} minutes practised` : "today, practice in progress" : state === "missed" ? "no practice recorded" : "upcoming"}`}>
              <span className="book-mark" aria-hidden="true"><i /><i /></span>
              <span className="week-day-label">{label}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
