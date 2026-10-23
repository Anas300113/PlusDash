"use client";

import Link from "next/link";
import Image from "next/image";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Calculator, Check, Circle, Clock3, MessageSquareText, RefreshCw } from "lucide-react";
import { DailyRing } from "@/components/progress-indicators";
import { weekDays } from "@/lib/data";

const plan = [
  {
    title: "Maths: fractions",
    detail: "10 questions, done",
    icon: Calculator,
    href: "/learn/maths",
    status: "done",
    label: "Completed",
  },
  {
    title: "Verbal reasoning: odd one out",
    detail: "8 questions, 5 to go",
    icon: MessageSquareText,
    href: "/practice",
    status: "current",
    label: "Continue",
  },
  {
    title: "Review: 6 cards due",
    detail: "About 4 minutes",
    icon: RefreshCw,
    href: "/review",
    status: "upcoming",
    label: "Start review",
  },
] as const;

export function TodayDashboard() {
  const reduceMotion = useReducedMotion();
  return (
    <div className="page-stack today-page">
      <section className="greeting-block" aria-labelledby="greeting-title">
        <h1 id="greeting-title" className="greeting-title">Hi <span className="highlight-underline">Sam</span>,</h1>
        <p className="greeting-subtitle">ready for a quick one?</p>
      </section>

      <motion.section
        className="continue-card"
        aria-label="Daily practice progress"
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.24, ease: [0.22, 1, 0.36, 1] }}
      >
        <DailyRing value={60} label="18 of 30 minutes practised today" />
        <div className="continue-copy">
          <p className="continue-message">Nearly there. <span>12 minutes</span> to go.</p>
          <Link className="button button-primary" href="/practice">
            Continue practice <ArrowRight size={17} strokeWidth={2} aria-hidden="true" />
          </Link>
        </div>
        <Image className="owl-peek" src="/plus11-mark.svg" alt="" aria-hidden="true" width={38} height={38} />
      </motion.section>

      <section className="plan-section" aria-labelledby="plan-heading">
        <div className="section-heading-row">
          <h2 id="plan-heading" className="section-title">Today’s plan</h2>
          <span className="section-progress">1 of 3 done</span>
        </div>
        <div className="plan-list">
          {plan.map(({ title, detail, icon: Icon, href, status, label }, index) => (
            <Link className={`plan-row plan-${status}`} href={href} key={title}>
              <span className="plan-icon"><Icon size={20} strokeWidth={2} aria-hidden="true" /></span>
              <span className="plan-copy">
                <span className="plan-title">{title}</span>
                <span className="plan-detail">{detail}</span>
              </span>
              <span className={`plan-status status-${status}`} aria-label={label}>
                {status === "done" ? <Check size={17} strokeWidth={2.5} aria-hidden="true" /> : status === "current" ? <span className="status-dot" aria-hidden="true" /> : <Circle size={21} strokeWidth={1.8} aria-hidden="true" />}
              </span>
              {index === 1 ? <span className="sr-only">Current activity. Open to continue.</span> : null}
            </Link>
          ))}
        </div>
      </section>

      <section className="week-section" aria-labelledby="week-heading">
        <div className="section-heading-row week-heading-row">
          <h2 id="week-heading" className="section-title">Your week</h2>
          <span className="week-note"><Clock3 size={15} aria-hidden="true" /> Little steps add up</span>
        </div>
        <div className="week-strip" role="list" aria-label="Weekly practice streak">
          {weekDays.map(({ label, state }) => (
            <div className={`week-day day-${state}`} role="listitem" key={label} aria-label={`${label}: ${state === "complete" ? "practice complete" : state === "today" ? "today, practice in progress" : "upcoming"}`}>
              <span className="book-mark" aria-hidden="true"><i /><i /></span>
              <span className="week-day-label">{label}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
