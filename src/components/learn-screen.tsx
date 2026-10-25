"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, LoaderCircle, LockKeyhole, Shapes } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { useSession } from "@/components/session-provider";
import { apiGet } from "@/lib/client-api";
import { subjects } from "@/lib/data";

type CatalogTopic = { id: string; name: string; approvedQuestionCount: number; attempts: number; mastery: number };
type CatalogSubject = { id: string; subjectId: string; name: string; mastery: number; attempts: number; topicCount: number; topics: CatalogTopic[] };
type CatalogResponse = { subjects: CatalogSubject[] };
const EMPTY_CATALOG_SUBJECTS: CatalogSubject[] = [];

export function LearnScreen() {
  const { status, csrfToken, error: sessionError, refresh: refreshSession } = useSession();
  const [catalogRecord, setCatalogRecord] = useState<{ key: string; data: CatalogResponse } | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = status === "authenticated" && csrfToken ? `${csrfToken}:${reloadKey}` : null;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let active = true;
    void apiGet<CatalogResponse>("/api/learner/catalog").then((data) => {
      if (active) setCatalogRecord({ key: `${csrfToken}:${reloadKey}`, data });
    }).catch((reason: unknown) => {
      if (active) setLoadError({ key: `${csrfToken}:${reloadKey}`, message: reason instanceof Error ? reason.message : "We couldn’t load the reviewed question bank just now." });
    });
    return () => { active = false; };
  }, [status, csrfToken, reloadKey]);

  const catalog = requestKey && catalogRecord?.key === requestKey ? catalogRecord.data : null;
  const catalogError = requestKey && loadError?.key === requestKey ? loadError.message : null;
  const signedIn = status === "authenticated" && catalog !== null;
  const availableSubjects = catalog?.subjects ?? EMPTY_CATALOG_SUBJECTS;
  const recommendation = useMemo(() => {
    const available = availableSubjects.flatMap((subject) => subject.topics
      .filter((topic) => topic.approvedQuestionCount > 0)
      .map((topic) => ({ subject, topic })));
    return available.filter((item) => item.topic.attempts > 0)
      .sort((a, b) => a.topic.mastery - b.topic.mastery || b.topic.attempts - a.topic.attempts)[0]
      ?? available[0]
      ?? null;
  }, [availableSubjects]);

  if (status === "loading" || (status === "authenticated" && catalog === null && !catalogError)) {
    return <div className="page-stack learn-page" aria-live="polite"><section className="page-intro"><h1 className="page-title">What shall we <span className="highlight-underline">learn</span>?</h1><p>Checking the reviewed question bank…</p></section><div className="account-state-card"><LoaderCircle className="account-spinner" size={22} aria-hidden="true" /> Loading approved subjects</div></div>;
  }

  if (status === "error" || catalogError) {
    return <div className="page-stack learn-page"><section className="page-intro"><h1 className="page-title">What shall we <span className="highlight-underline">learn</span>?</h1><p>We couldn’t load the reviewed question bank just now.</p></section><section className="account-state-card" role="alert"><p>{status === "error" ? sessionError : catalogError}</p><button className="button button-secondary" onClick={() => status === "error" ? void refreshSession() : setReloadKey((key) => key + 1)}>Try again</button></section></div>;
  }

  const demoSubjects = subjects;
  const displayedSubjects = signedIn ? availableSubjects : demoSubjects;
  const iconFor = (id: string, subjectId?: string) => subjects.find((item) => item.id === id || item.id === subjectId)?.icon ?? BookOpen;

  return (
    <div className="page-stack learn-page">
      <section className="page-intro" aria-labelledby="learn-title">
        <h1 id="learn-title" className="page-title">What shall we <span className="highlight-underline">learn</span>?</h1>
        <p>Pick a subject, then a topic.</p>
        {!signedIn ? <span className="demo-label">Example subjects</span> : null}
      </section>

      {signedIn && displayedSubjects.length === 0 ? (
        <section className="account-state-card" aria-labelledby="catalog-empty-title">
          <h2 id="catalog-empty-title" className="section-title">The reviewed question bank is being prepared</h2>
          <p>Account progress will use questions approved by the learning team. You can still try a sample question without saving progress.</p>
          <Link className="button button-primary" href="/practice?subject=verbal-reasoning&topic=odd-one-out&demo=1">Try a sample question <ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      ) : (
        <section aria-label="Choose a subject">
          <div className="subject-grid">
            {displayedSubjects.map((subject) => {
              const Icon = iconFor(subject.id, "subjectId" in subject ? subject.subjectId : undefined);
              const mastery = subject.mastery;
              const topicCount = subject.topicCount;
              return (
                <Link href={`/learn/${encodeURIComponent(subject.id)}`} className="subject-card" key={subject.id}>
                  <span className="subject-icon"><Icon size={21} strokeWidth={2} aria-hidden="true" /></span>
                  <span className="subject-name">{subject.name}</span>
                  <MasteryBar value={mastery} label={`${subject.name} mastery`} />
                  <span className="subject-meta"><strong>{mastery}% mastered</strong><span>{topicCount} topics</span></span>
                  <span className="subject-card-arrow"><ArrowRight size={17} aria-hidden="true" /></span>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {signedIn ? (
        recommendation ? (
          <section className="wobbly-section" aria-labelledby="wobbly-heading">
            <div className="section-heading-row"><h2 id="wobbly-heading" className="section-title">Pick up where it’s wobbly</h2><span className="quiet-label">A little review can help</span></div>
            <Link className="wobbly-card" href={`/practice?subject=${encodeURIComponent(recommendation.subject.subjectId)}&topic=${encodeURIComponent(recommendation.topic.id)}`}>
              <span className="wobbly-icon"><Shapes size={21} strokeWidth={2} aria-hidden="true" /></span>
              <span className="wobbly-copy"><strong>{recommendation.subject.name}: {recommendation.topic.name}</strong><span>{recommendation.topic.attempts ? `${recommendation.topic.attempts} saved answer${recommendation.topic.attempts === 1 ? "" : "s"}; ${recommendation.topic.mastery}% correct so far` : "Start with a question from the reviewed bank"}</span></span>
              <span className="button button-dark button-compact">Try <ArrowRight size={16} aria-hidden="true" /></span>
            </Link>
          </section>
        ) : null
      ) : (
        <section className="wobbly-section" aria-labelledby="wobbly-heading">
          <div className="section-heading-row"><h2 id="wobbly-heading" className="section-title">Pick up where it’s wobbly</h2><span className="quiet-label">A little review can help</span></div>
          <Link className="wobbly-card" href="/practice?subject=non-verbal-reasoning&topic=rotations">
            <span className="wobbly-icon"><Shapes size={21} strokeWidth={2} aria-hidden="true" /></span>
            <span className="wobbly-copy"><strong>Non-verbal: rotations</strong><span>3 of the last 5 answers missed</span></span>
            <span className="button button-dark button-compact">Try <ArrowRight size={16} aria-hidden="true" /></span>
          </Link>
        </section>
      )}

      <section className="locked-card" aria-label="Timed mock paper locked">
        <span className="locked-icon"><LockKeyhole size={19} strokeWidth={2} aria-hidden="true" /></span>
        <span className="locked-copy"><strong>Timed mock paper</strong><span>Unlocks after 5 more topics</span></span>
        <span className="locked-status">Locked</span>
      </section>
    </div>
  );
}
