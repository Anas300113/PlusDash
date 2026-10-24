"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Clock3, LoaderCircle } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { useSession } from "@/components/session-provider";
import { apiGet } from "@/lib/client-api";
import { subjects, weekDays } from "@/lib/data";

type ProgressData = {
  overall: number;
  totalAttempts: number;
  mastery: { id: string; name: string; mastery: number; attempts: number }[];
  minutesByDay: { date: string; label: string; state: "complete" | "today" | "upcoming" | "missed"; minutes: number }[];
  practiceDays: number;
  nextStep: { subjectId: string; topicId: string; title: string; detail: string; href: string };
};

const sampleActivityMinutes = [12, 18, 9, 15, 18, 0, 0];

export function ProgressScreen() {
  const { status, csrfToken, error: sessionError, refresh: refreshSession } = useSession();
  const [progressRecord, setProgressRecord] = useState<{ key: string; data: ProgressData } | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = status === "authenticated" && csrfToken ? `${csrfToken}:${reloadKey}` : null;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let current = true;
    void apiGet<ProgressData>("/api/learner/progress").then((data) => {
      if (current) setProgressRecord({ key: `${csrfToken}:${reloadKey}`, data });
    }).catch((reason: unknown) => { if (current) setLoadError({ key: `${csrfToken}:${reloadKey}`, message: reason instanceof Error ? reason.message : "We couldn’t load your progress just now." }); });
    return () => { current = false; };
  }, [status, csrfToken, reloadKey]);

  const progress = requestKey && progressRecord?.key === requestKey ? progressRecord.data : null;
  const progressError = requestKey && loadError?.key === requestKey ? loadError.message : null;

  if (status === "loading" || (status === "authenticated" && progress === null && !progressError)) {
    return <div className="page-stack progress-page" aria-live="polite"><section className="page-intro"><h1 className="page-title">Look how far you’ve come</h1><p>Getting your saved progress ready…</p></section><div className="account-state-card"><LoaderCircle className="account-spinner" size={22} aria-hidden="true" /> Loading your progress</div></div>;
  }
  if (status === "error" || progressError) {
    return <div className="page-stack progress-page"><section className="page-intro"><h1 className="page-title">Look how far you’ve come</h1><p>We couldn’t load your progress just now.</p></section><section className="account-state-card" role="alert"><p>{status === "error" ? sessionError : progressError}</p><button className="button button-secondary" onClick={() => status === "error" ? void refreshSession() : setReloadKey((key) => key + 1)}>Try again</button></section></div>;
  }

  const signedIn = status === "authenticated" && progress !== null;
  const mastery = signedIn ? progress.mastery : subjects.map(({ id, name, mastery: value }) => ({ id, name, mastery: value, attempts: 0 }));
  const overall = signedIn ? progress.overall : Math.round(subjects.reduce((total, subject) => total + subject.mastery, 0) / subjects.length);
  const activity = signedIn ? progress.minutesByDay : weekDays.map((day, index) => ({ ...day, date: day.label, minutes: sampleActivityMinutes[index] }));
  const maxMinutes = Math.max(1, ...activity.map((day) => day.minutes));
  const practiceDays = signedIn ? progress.practiceDays : 5;
  const totalAttempts = signedIn ? progress.totalAttempts : null;
  const nextStep = signedIn ? progress.nextStep : {
    title: "Give rotations another try",
    detail: "Short practice can make tricky topics feel clearer.",
    href: "/practice?subject=non-verbal-reasoning&topic=rotations",
  };

  return (
    <div className="page-stack progress-page">
      <section className="page-intro" aria-labelledby="progress-title">
        <h1 id="progress-title" className="page-title">Look how far you’ve come</h1>
        <p>Every bit of practice helps you grow.</p>
        {!signedIn ? <span className="demo-label">Example progress</span> : null}
      </section>

      <section className="progress-overview" aria-labelledby="mastery-heading">
        <div className="progress-overview-head">
          <div>
            <h2 id="mastery-heading" className="section-title">Topics you’ve mastered</h2>
            <p>{signedIn ? `${totalAttempts} saved answer${totalAttempts === 1 ? "" : "s"} so far` : "Across the subjects you’re learning"}</p>
          </div>
          <span className="overall-stat"><strong>{overall}%</strong><span>overall</span></span>
        </div>
        <div className="progress-subject-list">
          {mastery.map(({ id, name, mastery: value, attempts }) => (
            <Link className="progress-subject-row" href={`/learn/${id}`} key={id} aria-label={`${name}: ${value}%${signedIn ? ` from ${attempts} answers` : " mastery"}`}>
              <span className="progress-subject-name">{name}</span>
              <MasteryBar value={value} label={`${name} mastery`} />
              <span className="progress-subject-value">{value}%</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="activity-section" aria-labelledby="activity-heading">
        <div className="section-heading-row">
          <h2 id="activity-heading" className="section-title">Your practice this week</h2>
          <span className="week-note"><Clock3 size={15} aria-hidden="true" /> Minutes practised</span>
        </div>
        <div className="activity-chart" role="list" aria-label="Minutes practised each day this week">
          {activity.map(({ label, state, minutes }) => (
            <div className="activity-day" role="listitem" key={label} aria-label={`${label}: ${minutes} minutes`}>
              <span className="activity-value">{minutes ? `${minutes}m` : "—"}</span>
              <span className="activity-bar-track" aria-hidden="true"><span className={`activity-bar-fill${state === "today" ? " activity-today" : ""}`} style={{ height: `${Math.max(minutes / maxMinutes * 100, 5)}%` }} /></span>
              <span className="activity-label">{label}</span>
            </div>
          ))}
        </div>
        <p className="activity-caption">{practiceDays > 0 ? <><span className="tiny-check"><Check size={13} strokeWidth={2.5} aria-hidden="true" /></span> You’ve practised on {practiceDays} day{practiceDays === 1 ? "" : "s"} this week.</> : "Your practice days will appear here as you go."}</p>
      </section>

      <Link href={nextStep.href} className="next-step-card">
        <span className="next-step-copy"><span className="next-step-label">A good next step</span><strong>{nextStep.title}</strong><span>{nextStep.detail}</span></span>
        <span className="next-step-arrow" aria-hidden="true"><ArrowRight size={20} /></span>
      </Link>
    </div>
  );
}
